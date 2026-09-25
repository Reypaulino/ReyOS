"""Sync & Migration backend -- wraps Syncthing's REST API.

Architecture note (see docs/connect.md "Sync & Migration" section): every
other provider in this app (vpn_provider, bluetooth_provider, remote_provider)
is either pure D-Bus (signal-driven, no polling) or a thin CLI wrapper over
structured output (tailscale --json, nmcli). Syncthing exposes neither a
D-Bus interface nor a scriptable status CLI worth trusting -- its real,
stable interface is a local REST API (default https://127.0.0.1:8384/rest/*,
X-API-Key auth) plus a long-poll /rest/events endpoint for near-real-time
updates. That's a genuinely different integration shape from the rest of
this app, by necessity, not by choice -- documented here rather than papered
over.

Never talks to Syncthing's global discovery/relay servers by policy: this
module explicitly disables `globalAnnounceEnabled`/`relaysEnabled` in
Syncthing's own config on first-run setup (see ensure_local_only()), per the
ReyOS Connect spec's "never expose sync ports publicly" rule. LAN-only
discovery; remote sync happens over the existing VPN providers' tailnet/
WireGuard addresses (added as explicit static device addresses), never via
Syncthing's own public relay/discovery infrastructure.
"""
import json
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger("reyos-connect.sync")

CONFIG_PATH = Path.home() / ".config" / "syncthing" / "config.xml"
API_TIMEOUT = 10


class SyncApiError(Exception):
    pass


# -- installation / daemon state -----------------------------------------

def is_installed():
    return shutil.which("syncthing") is not None


def is_running():
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "syncthing.service"],
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip() == "active"


def start():
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", "syncthing.service"],
        capture_output=True, text=True, timeout=15,
    )
    return result.returncode == 0, (result.stderr.strip() or "Started.")


def stop():
    result = subprocess.run(
        ["systemctl", "--user", "disable", "--now", "syncthing.service"],
        capture_output=True, text=True, timeout=15,
    )
    return result.returncode == 0, (result.stderr.strip() or "Stopped.")


# -- REST plumbing --------------------------------------------------------

def _read_config_xml():
    """Parses Syncthing's own config.xml for the GUI address + API key.
    Read directly rather than via the REST API, since we need the API key
    *to* call the REST API -- this is the documented Syncthing bootstrap
    sequence (the API key lives in the config file it writes on first run,
    same file a user would open to find it manually)."""
    if not CONFIG_PATH.exists():
        raise SyncApiError(f"Syncthing config not found at {CONFIG_PATH} -- has it run once yet?")
    tree = ET.parse(CONFIG_PATH)
    gui = tree.getroot().find("gui")
    if gui is None:
        raise SyncApiError("No <gui> section in Syncthing config.")
    api_key = gui.findtext("apikey", "")
    address = gui.findtext("address", "127.0.0.1:8384")
    use_tls = (gui.get("tls") or "false").lower() == "true"
    if not api_key:
        raise SyncApiError("Syncthing has no API key configured yet.")
    return api_key, address, use_tls


def _base_url():
    _, address, use_tls = _read_config_xml()
    scheme = "https" if use_tls else "http"
    # Syncthing's default GUI address is "127.0.0.1:8384"; a bare "0.0.0.0:8384"
    # (listen-on-all-interfaces) is still reached fine via localhost.
    host = address.split(":")[-2] if address.count(":") > 1 else "127.0.0.1"
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    port = address.rsplit(":", 1)[-1]
    return f"{scheme}://127.0.0.1:{port}" if host == "127.0.0.1" else f"{scheme}://{host}:{port}"


def _request(method, path, data=None):
    api_key, _, _ = _read_config_xml()
    url = _base_url() + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.URLError as e:
        raise SyncApiError(f"Could not reach Syncthing at {url}: {e}") from e
    except json.JSONDecodeError as e:
        raise SyncApiError(f"Syncthing returned invalid JSON from {path}: {e}") from e


def _get(path):
    return _request("GET", path)


def _post(path, data=None):
    return _request("POST", path, data)


def _put(path, data):
    return _request("PUT", path, data)


# -- first-run policy: LAN-only, no public exposure ----------------------

def ensure_local_only():
    """Disables Syncthing's global discovery + relay servers, per the ReyOS
    Connect spec's 'never expose sync ports publicly' rule. Idempotent --
    safe to call on every app start. Returns True if a change was made."""
    cfg = _get("/rest/config")
    opts = cfg.setdefault("options", {})
    changed = False
    if opts.get("globalAnnounceEnabled", True):
        opts["globalAnnounceEnabled"] = False
        changed = True
    if opts.get("relaysEnabled", True):
        opts["relaysEnabled"] = False
        changed = True
    if not opts.get("localAnnounceEnabled", True):
        # local (LAN) discovery is what we *do* want on
        opts["localAnnounceEnabled"] = True
        changed = True
    if changed:
        _put("/rest/config/options", opts)
    return changed


# -- status ----------------------------------------------------------------

def my_device_id():
    return _get("/rest/system/status").get("myID", "")


def system_status():
    """High-level daemon health: installed / running / reachable / own device ID."""
    if not is_installed():
        return {"installed": False, "running": False, "reachable": False, "myId": ""}
    running = is_running()
    if not running:
        return {"installed": True, "running": False, "reachable": False, "myId": ""}
    try:
        status = _get("/rest/system/status")
        return {
            "installed": True, "running": True, "reachable": True,
            "myId": status.get("myID", ""),
            "uptime": status.get("uptime", 0),
        }
    except SyncApiError as e:
        return {"installed": True, "running": True, "reachable": False, "myId": "", "error": str(e)}


def list_devices():
    """Configured (already-paired) devices, with live connection state merged
    in from /rest/system/connections -- config alone can't tell you if a
    device is actually online right now."""
    cfg = _get("/rest/config")
    try:
        conns = _get("/rest/system/connections").get("connections", {})
    except SyncApiError:
        conns = {}
    my_id = my_device_id()
    devices = []
    for dev in cfg.get("devices", []):
        if dev.get("deviceID") == my_id:
            continue
        conn = conns.get(dev["deviceID"], {})
        devices.append({
            "id": dev["deviceID"],
            "name": dev.get("name") or dev["deviceID"][:7],
            "paused": dev.get("paused", False),
            "connected": conn.get("connected", False),
            "address": conn.get("address", ""),
        })
    return devices


def pending_devices():
    """Devices that tried to connect but aren't configured/authorized yet --
    this is the real backing data for the 'X wants to connect' pairing
    prompt the spec requires (never auto-trust a discovered device)."""
    try:
        pending = _get("/rest/cluster/pending/devices")
    except SyncApiError:
        return []
    return [
        {"id": dev_id, "name": info.get("name", ""), "address": info.get("address", "")}
        for dev_id, info in pending.items()
    ]


def add_device(device_id, name):
    """Explicit user-authorized pairing action -- never called automatically."""
    _put(f"/rest/config/devices/{device_id}", {
        "deviceID": device_id,
        "name": name,
        "addresses": ["dynamic"],
    })


def remove_device(device_id):
    _request("DELETE", f"/rest/config/devices/{device_id}")


def list_folders():
    """Configured sync folders, with live status (state/completion) merged
    in per folder."""
    cfg = _get("/rest/config")
    folders = []
    for f in cfg.get("folders", []):
        folder_id = f["id"]
        try:
            db_status = _get(f"/rest/db/status?folder={folder_id}")
        except SyncApiError:
            db_status = {}
        folders.append({
            "id": folder_id,
            "label": f.get("label") or folder_id,
            "path": f.get("path", ""),
            "type": f.get("type", "sendreceive"),  # sendreceive | sendonly | receiveonly
            "paused": f.get("paused", False),
            "devices": [d["deviceID"] for d in f.get("devices", [])],
            "state": db_status.get("state", "unknown"),
            "needFiles": db_status.get("needFiles", 0),
            "needBytes": db_status.get("needBytes", 0),
            "globalBytes": db_status.get("globalBytes", 0),
            "errors": db_status.get("errors", 0),
        })
    return folders


def pending_folders():
    """Folders a connected device has offered that aren't shared locally yet
    -- the other half of explicit-consent pairing (a device you already
    trust can still offer a *folder* you haven't agreed to receive)."""
    try:
        pending = _get("/rest/cluster/pending/folders")
    except SyncApiError:
        return []
    result = []
    for folder_id, info in pending.items():
        for dev_id, offer in info.get("offeredBy", {}).items():
            result.append({
                "folderId": folder_id,
                "label": offer.get("label") or folder_id,
                "deviceId": dev_id,
            })
    return result


FOLDER_TYPES = {
    "sendreceive": "Two-way -- changes on either machine synchronize both ways.",
    "sendonly": "Send only -- this machine is authoritative; the remote never pushes changes back.",
    "receiveonly": "Receive only -- the remote machine is authoritative; local changes are not sent.",
}


def add_folder(folder_id, label, local_path, device_ids, folder_type="sendreceive"):
    """Adds a new synced folder. folder_id must match across both machines
    (Syncthing's own folder identity, distinct from the local path, which
    is exactly what lets ~/Documents/Work on one box map to
    /home/other/Documents/Work on another)."""
    if folder_type not in FOLDER_TYPES:
        raise ValueError(f"Unknown folder type: {folder_type}")
    Path(local_path).mkdir(parents=True, exist_ok=True)
    _put(f"/rest/config/folders/{folder_id}", {
        "id": folder_id,
        "label": label,
        "path": local_path,
        "type": folder_type,
        "devices": [{"deviceID": d} for d in device_ids],
        # .git is intentionally left syncable (spec: don't auto-exclude
        # git repos) -- only genuinely reproducible/generated dirs are
        # pre-suggested, and only ever shown to the user before applying,
        # never silently written here.
    })


def remove_folder(folder_id):
    _request("DELETE", f"/rest/config/folders/{folder_id}")


def set_folder_paused(folder_id, paused):
    cfg = _get(f"/rest/config/folders/{folder_id}")
    cfg["paused"] = paused
    _put(f"/rest/config/folders/{folder_id}", cfg)


SUGGESTED_EXCLUSIONS = [
    "node_modules", ".cache", "__pycache__", "build", "dist",
    "*.iso", "*.qcow2", "target",
]


def write_ignore_patterns(local_path, patterns):
    """Writes a folder's .stignore file. Shown to and confirmed by the user
    before being applied -- never silently excludes user data (spec:
    'show exclusions before applying them')."""
    ignore_file = Path(local_path) / ".stignore"
    ignore_file.write_text("\n".join(patterns) + "\n")


def folder_completion(folder_id, device_id):
    """0-100 sync completion percentage for one folder against one remote
    device -- the real number behind a 'Syncing -- 72%' row."""
    try:
        result = _get(f"/rest/db/completion?folder={folder_id}&device={device_id}")
        return result.get("completion", 0)
    except SyncApiError:
        return None
