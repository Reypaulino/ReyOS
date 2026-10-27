"""Remote Play: stream this PC's games to a TV, phone or another PC with
Moonlight. Sunshine (from ReyOS's own repo) does the streaming; this module
sets it up the ReyOS way and talks to it. Qt-free, shared by Control Center
(Gaming page) and ReyOS Games ("Play on another device").

Off unless the user turns it on: nothing is installed, started at login or let
through the firewall without their say. Sunshine's web settings only answer on
this PC, UPnP stays off, and a device can only connect after the user types the
PIN Moonlight shows."""
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path

SUNSHINE = "/usr/bin/sunshine"
SERVICE = "app-dev.lizardbyte.app.Sunshine.service"
CONF_DIR = Path.home() / ".config" / "sunshine"
CONF = CONF_DIR / "sunshine.conf"
APPS = CONF_DIR / "apps.json"
LOG = CONF_DIR / "sunshine.log"
COVER = CONF_DIR / "covers" / "reyos-games.png"
# ReyOS's own settings and the web settings login it made (0600).
SETTINGS = Path.home() / ".config" / "reyos" / "remote-play.json"
API = "https://localhost:47990"
USERNAME = "reyos"
GAMES_ICON = "/usr/share/icons/hicolor/scalable/apps/reyos-games.svg"
GAMES_CMD = "setsid /usr/share/reyos/control-center/games.py"

# Moonlight's ports (Sunshine's default port 47989 and the ones next to it).
# 47990, the web settings, is never opened.
TCP_PORTS = "47984,47989,48010"
UDP_PORTS = "47998:48000,48002"

# Always set: the web settings only answer on this PC; no UPnP (no holes in
# the router); at most 15 Mbps, which an older laptop can encode.
FORCED = {"origin_web_ui_allowed": "pc", "upnp": "disabled"}
DEFAULTS = {"max_bitrate": "15000"}


def packages():
    """What Install installs: Sunshine and vainfo, plus Intel's video driver
    on an Intel GPU (the encoder on most laptops)."""
    pkgs = ["sunshine", "libva-utils"]
    if any(gpu["vendor"] == "intel" for gpu in render_nodes()):
        pkgs.append("intel-media-driver")
    return pkgs


def installed():
    return Path(SUNSHINE).exists()


def _systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def running():
    return _systemctl("is-active", "--quiet", SERVICE).returncode == 0


def starts_at_login():
    return _systemctl("is-enabled", "--quiet", SERVICE).returncode == 0


# ---- ReyOS's own settings ----------------------------------------------------

def load_settings():
    try:
        data = json.loads(SETTINGS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(changes):
    data = dict(load_settings(), **changes)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out, indent=1)
    os.replace(tmp, SETTINGS)
    return data


def show_in_games():
    """ReyOS Games shows "Play on another device" only when Remote Play is
    installed and this is on (Control Center → Gaming → Remote Play)."""
    return installed() and load_settings().get("show_in_games", True) is True


# ---- Sunshine's config ---------------------------------------------------------

def read_conf(path=CONF):
    values = {}
    try:
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                values[m.group(1)] = m.group(2)
    except OSError:
        pass
    return values


def write_conf(forced, defaults, path=CONF):
    """Sets forced keys always and default keys only when the user hasn't set
    them (in the file or in Sunshine's web settings, which write the same
    file). Every other line is kept as it was."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        lines = []
    current = {}
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*=", line)
        if m and not line.lstrip().startswith("#"):
            current[m.group(1)] = i
    wanted = dict(forced)
    wanted.update({k: v for k, v in defaults.items() if k not in current})
    changed = False
    for key, value in wanted.items():
        line = f"{key} = {value}"
        if key in current:
            if lines[current[key]].strip() != line:
                lines[current[key]] = line
                changed = True
        else:
            lines.append(line)
            changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
    return changed


def kde_wayland():
    return (os.environ.get("XDG_SESSION_TYPE") == "wayland"
            and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper())


def wanted_defaults():
    """KWin's own screen capture on Plasma (no extra privileges, and it
    keeps working when KWin draws through overlays); VA-API on the GPU that
    can encode H.264. Sunshine would try NVENC and Vulkan first, which a
    laptop's GeForce MX/9x0M often can't do."""
    defaults = dict(DEFAULTS)
    if kde_wayland():
        defaults["capture"] = "kwin"
    node = encode_node()
    if node:
        defaults["encoder"] = "vaapi"
        defaults["adapter_name"] = node["path"]
    return defaults


# ---- GPUs and video encoders -------------------------------------------------

VENDORS = {"0x8086": "intel", "0x10de": "nvidia", "0x1002": "amd"}


def render_nodes():
    nodes = []
    for node in sorted(Path("/dev/dri").glob("renderD*")):
        dev = Path("/sys/class/drm") / node.name / "device"
        try:
            vendor = (dev / "vendor").read_text().strip()
        except OSError:
            vendor = ""
        try:
            driver = (dev / "driver").resolve().name
        except OSError:
            driver = ""
        nodes.append({"path": str(node), "vendor": VENDORS.get(vendor, "other"), "driver": driver,
                      "name": _gpu_name(dev)})
    return nodes


def _gpu_name(dev):
    try:
        slot = dev.resolve().name
        out = subprocess.run(["lspci", "-s", slot], capture_output=True, text=True, timeout=5).stdout
        return out.split(": ", 1)[1].strip() if ": " in out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def vaapi_encoders(node):
    """The codecs VA-API can encode on one GPU: [] when it can't (no driver,
    or a GPU without a video encoder)."""
    if not shutil.which("vainfo"):
        return []
    try:
        out = subprocess.run(["vainfo", "--display", "drm", "--device", node], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    codecs = []
    for name, profile in (("H.264", "VAProfileH264(High|Main)"), ("HEVC", "VAProfileHEVCMain\\b"),
                          ("AV1", "VAProfileAV1Profile0")):
        if re.search(profile + r"\s*:\s*VAEntrypointEncSlice", out):
            codecs.append(name)
    return codecs


def encode_node():
    """The first GPU whose VA-API driver encodes H.264 (Sunshine's minimum)."""
    for node in render_nodes():
        if node["vendor"] != "nvidia" and "H.264" in vaapi_encoders(node["path"]):
            return node
    return None


def encoder_report():
    """What this PC can encode with, for the status line and the
    diagnostics: each GPU from VA-API, plus what Sunshine itself picked at
    its last start (from its log)."""
    gpus = []
    for node in render_nodes():
        codecs = vaapi_encoders(node["path"]) if node["vendor"] != "nvidia" else []
        gpus.append(dict(node, codecs=codecs))
    found, failed = [], []
    try:
        log = LOG.read_text(errors="replace")
    except OSError:
        log = ""
    for m in re.finditer(r"Found (\S+) encoder: (\S+) \[(\w+)\]", log):
        found.append(f"{m.group(1)} with {m.group(2)}")
    for m in re.finditer(r"Encoder \[(\w+)\] failed", log):
        failed.append(m.group(1))
    in_use = ""
    if found:
        in_use = found[0]
    software = "software" in in_use or "libx264" in in_use
    return {"gpus": gpus, "found": found, "failed": sorted(set(failed)), "inUse": in_use, "software": software}


# ---- addresses -----------------------------------------------------------------

def local_addresses():
    """This PC's home-network IPv4 addresses (not VPNs or VM bridges)."""
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True,
                             text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    addrs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        iface, addr = parts[1], parts[3].split("/")[0]
        if re.match(r"(tailscale|wg|tun|docker|virbr|br-|veth|zt)", iface):
            continue
        addrs.append({"interface": iface, "address": addr})
    return addrs


def tailscale_status():
    """{} when Tailscale isn't installed or isn't signed in; else this PC's
    Tailscale address and how each online device is reached: "direct" or
    "relayed" (through Tailscale's servers, slower)."""
    if not shutil.which("tailscale"):
        return {}
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=8)
        data = json.loads(out.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    if data.get("BackendState") != "Running":
        return {"state": data.get("BackendState", "")}
    ips = [ip for ip in (data.get("Self") or {}).get("TailscaleIPs") or [] if ":" not in ip]
    peers = []
    for peer in (data.get("Peer") or {}).values():
        if not peer.get("Online"):
            continue
        path = "direct" if peer.get("CurAddr") else ("relayed" if peer.get("Relay") else "unknown")
        peers.append({"name": peer.get("HostName") or peer.get("DNSName", ""), "path": path,
                      "relay": peer.get("Relay", "")})
    return {"state": "Running", "address": ips[0] if ips else "", "peers": peers}


# ---- the web settings login ---------------------------------------------------

def credentials():
    data = load_settings()
    return data.get("username", ""), data.get("password", "")


def _state_has_login():
    try:
        return bool(json.loads((CONF_DIR / "sunshine_state.json").read_text()).get("username"))
    except (OSError, ValueError):
        return False


def ensure_credentials():
    """Sunshine's web settings need a login. ReyOS makes one (user "reyos",
    a random password kept in remote-play.json, readable only by you) so
    Control Center can list pairing requests; Copy password shows it for
    the web settings. Returns True when it set a new one (Sunshine must be
    restarted to use it)."""
    username, password = credentials()
    if username and password and _state_has_login():
        return False
    password = secrets.token_urlsafe(18)
    result = subprocess.run([SUNSHINE, "--creds", USERNAME, password], capture_output=True, text=True,
                            timeout=60, cwd=str(Path.home()))
    if result.returncode != 0 or not _state_has_login():
        raise RuntimeError("Sunshine didn't accept the new login: " + (result.stdout + result.stderr)[-300:])
    save_settings({"username": USERNAME, "password": password})
    return True


# ---- Moonlight's app list -------------------------------------------------------

def _games_cover():
    if COVER.exists() or not shutil.which("rsvg-convert") or not Path(GAMES_ICON).exists():
        return str(COVER) if COVER.exists() else ""
    COVER.parent.mkdir(parents=True, exist_ok=True)
    # Moonlight's tiles are 600×800 box art: the icon on a dark card.
    rc = subprocess.run(["rsvg-convert", "-w", "360", "-h", "360", "-a", "--page-width", "600",
                         "--page-height", "800", "--left", "120", "--top", "220",
                         "--background-color", "#1b1e24", "-o", str(COVER), GAMES_ICON],
                        capture_output=True).returncode
    return str(COVER) if rc == 0 and COVER.exists() else ""


def ensure_games_app():
    """Adds "ReyOS Games" to what Moonlight lists (next to Desktop), and
    drops Sunshine's sample "Low Res Desktop" (it runs xrandr, which does
    nothing on Wayland). Other entries are left alone."""
    try:
        data = json.loads(APPS.read_text())
    except (OSError, ValueError):
        data = {"env": {"PATH": "$(PATH):$(HOME)/.local/bin"}, "apps": [{"name": "Desktop", "image-path": "desktop.png"}]}
    apps = data.setdefault("apps", [])
    before = json.dumps(data, sort_keys=True)
    apps[:] = [a for a in apps if not (a.get("name") == "Low Res Desktop" and "xrandr" in json.dumps(a.get("prep-cmd", [])))]
    for a in apps:  # written by a test build with a command that doesn't exist
        if a.get("name") == "ReyOS Games" and a.get("detached") == ["setsid reyos-games"]:
            a["detached"] = [GAMES_CMD]
    if not any(a.get("name") == "ReyOS Games" for a in apps):
        entry = {"name": "ReyOS Games", "detached": [GAMES_CMD]}
        cover = _games_cover()
        if cover:
            entry["image-path"] = cover
        desktop = next((i for i, a in enumerate(apps) if a.get("name") == "Desktop"), -1)
        apps.insert(desktop + 1, entry)
    if json.dumps(data, sort_keys=True) == before:
        return False
    APPS.parent.mkdir(parents=True, exist_ok=True)
    APPS.write_text(json.dumps(data, indent=2) + "\n")
    return True


# ---- setup, start, stop -------------------------------------------------------

def set_up():
    """Writes ReyOS's settings into Sunshine's files. Safe to run again (each
    start does): only missing or wrong values change. Returns True when
    something changed that a running Sunshine must restart for."""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    changed = write_conf(FORCED, wanted_defaults())
    changed = ensure_credentials() or changed
    changed = ensure_games_app() or changed
    return changed


def start():
    changed = set_up()
    if running() and not changed:
        return True, "Remote Play is already on."
    result = _systemctl("restart" if running() else "start", SERVICE)
    if result.returncode != 0:
        return False, "Sunshine didn't start: " + (result.stderr.strip() or "see the diagnostics")
    return True, "Remote Play is on. Open Moonlight on your TV or phone and pick this PC."


def stop():
    result = _systemctl("stop", SERVICE)
    if result.returncode != 0:
        return False, "Couldn't stop Sunshine: " + result.stderr.strip()
    return True, "Remote Play is off. Nothing can stream from this PC now."


def set_starts_at_login(on):
    result = _systemctl("enable" if on else "disable", SERVICE)
    if result.returncode != 0:
        return False, result.stderr.strip() or "systemctl failed"
    return True, ("Remote Play starts when you log in." if on
                  else "Remote Play no longer starts by itself.")


# ---- Sunshine's API (this PC only) -----------------------------------------------

class ApiError(Exception):
    pass


def api(method, path, body=None, timeout=10):
    username, password = credentials()
    if not password:
        raise ApiError("Remote Play isn't set up yet: press Turn on.")
    # Sunshine's certificate is its own self-signed one, and the address is
    # this PC: there's nothing to verify against.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, method=method)
    request.add_header("Authorization", "Basic " + b64encode(f"{username}:{password}".encode()).decode())
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, context=ctx, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error", "")
        except ValueError:
            detail = ""
        if e.code == 401:
            raise ApiError("Sunshine didn't accept ReyOS's login. Turn Remote Play off and on again to reset it.")
        raise ApiError(detail or f"Sunshine answered {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ApiError("Sunshine isn't answering (is Remote Play on?)") from e


def pending_pairings():
    """Devices waiting for their PIN: [{id, name, address}]."""
    return [p for p in api("GET", "/api/pin").get("pairings", []) if re.fullmatch(r"[0-9a-f]{32}", p.get("id", ""))]


def pair(pairing_id, pin, name):
    if not re.fullmatch(r"[0-9a-f]{32}", pairing_id):
        return False, "That pairing request isn't valid any more."
    if not re.fullmatch(r"[0-9]{4}", pin):
        return False, "The PIN is the 4 digits Moonlight shows."
    name = (name or "").strip()[:64] or "Moonlight"
    # Sunshine answers when Moonlight finishes the handshake (or gives up).
    ok = api("POST", "/api/pin", {"pairing_id": pairing_id, "pin": pin, "name": name}, timeout=40).get("status") is True
    return ok, (f"{name} is paired. It can stream from this PC now." if ok
                else "Pairing didn't finish: check the PIN and try again from Moonlight.")


def decline(pairing_id):
    if not re.fullmatch(r"[0-9a-f]{32}", pairing_id):
        return False
    return api("DELETE", "/api/pin", {"pairing_id": pairing_id}).get("status") is True


def paired_devices():
    return [{"name": c.get("name", ""), "uuid": c.get("uuid", ""), "enabled": c.get("enabled", True)}
            for c in api("GET", "/api/clients/list").get("named_certs", [])]


def unpair(uuid):
    if not re.fullmatch(r"[0-9A-Za-z-]{1,64}", uuid or ""):
        return False, "Unknown device."
    ok = api("POST", "/api/clients/unpair", {"uuid": uuid}).get("status") is True
    return ok, ("Removed. That device has to pair again to stream." if ok else "Couldn't remove that device.")


# ---- status and diagnostics -----------------------------------------------------

def firewall_open(ufw_status):
    """From `ufw status` text: whether ReyOS's Remote Play rules are there."""
    return "ReyOS Remote Play" in (ufw_status or "")


def input_ready():
    """Moonlight's mouse, keyboard and controllers need /dev/uinput and
    /dev/uhid (Sunshine's udev rule gives them to the logged-in user)."""
    return all(os.access(dev, os.R_OK | os.W_OK) for dev in ("/dev/uinput", "/dev/uhid"))


def status(ufw_status=""):
    st = {"installed": installed(), "running": False, "atLogin": False, "showInGames": show_in_games(),
          "local": local_addresses(), "tailscale": {}, "firewallOpen": firewall_open(ufw_status),
          "inputReady": input_ready(), "kdeWayland": kde_wayland()}
    if not st["installed"]:
        return st
    st["running"] = running()
    st["atLogin"] = starts_at_login()
    st["tailscale"] = tailscale_status()
    st["encoder"] = encoder_report()
    return st


def _last_errors(limit=12):
    try:
        lines = LOG.read_text(errors="replace").splitlines()
    except OSError:
        return []
    noise = ("CAP_SYS_ADMIN", "Gamepad ", "CUDA", "Vulkan @", "Couldn't initialize cuda")
    keep = [l for l in lines if re.search(r"\]: (Error|Fatal|Warning):", l) and not any(n in l for n in noise)]
    return keep[-limit:]


def diagnostics(ufw_status=""):
    """A plain-text report to copy into a bug report. Addresses inside
    Tailscale and the home network are shown as they are (they're private);
    the web settings password is never included."""
    st = status(ufw_status)
    out = ["ReyOS Remote Play diagnostics"]
    version = ""
    if st["installed"]:
        try:
            version = subprocess.run(["pacman", "-Q", "sunshine"], capture_output=True, text=True).stdout.strip()
        except OSError:
            pass
    out.append(f"Sunshine: {version or ('installed' if st['installed'] else 'not installed')}")
    out.append(f"Session: {os.environ.get('XDG_SESSION_TYPE', '?')} / {os.environ.get('XDG_CURRENT_DESKTOP', '?')}")
    out.append(f"Running: {st['running']}  Starts at login: {st['atLogin']}")
    out.append(f"Firewall lets Moonlight in: {st['firewallOpen']}")
    out.append(f"Mouse/keyboard/controller access (/dev/uinput, /dev/uhid): {st['inputReady']}")
    conf = read_conf()
    out.append("Settings: " + ", ".join(f"{k}={conf[k]}" for k in
                                        ("capture", "encoder", "adapter_name", "max_bitrate", "origin_web_ui_allowed", "upnp")
                                        if k in conf))
    enc = st.get("encoder") or encoder_report()
    for gpu in enc["gpus"]:
        what = ", ".join(gpu["codecs"]) if gpu["codecs"] else ("not checked (NVIDIA: Sunshine tries NVENC itself)"
                                                               if gpu["vendor"] == "nvidia" else "none")
        out.append(f"GPU {gpu['path']} ({gpu['driver']}) {gpu['name']}: VA-API encode: {what}")
    out.append("Sunshine's encoder: " + (enc["inUse"] or "not started yet")
               + (f"  (failed: {', '.join(enc['failed'])})" if enc["failed"] else ""))
    for a in st["local"]:
        out.append(f"Home network: {a['address']} ({a['interface']})")
    ts = st["tailscale"]
    if ts.get("state") == "Running":
        out.append(f"Tailscale: {ts.get('address', '?')}")
        for p in ts.get("peers", []):
            out.append(f"  {p['name']}: {p['path']}" + (f" via {p['relay']}" if p["path"] == "relayed" else ""))
    else:
        out.append("Tailscale: " + (ts.get("state") or "not installed"))
    try:
        listening = subprocess.run(["ss", "-ltnup"], capture_output=True, text=True, timeout=5).stdout
        ports = sorted({m.group(1) for m in re.finditer(r":(4798\d|4799\d|4800\d|48010)\s", listening)})
        out.append("Listening on: " + (", ".join(ports) or "nothing"))
    except (OSError, subprocess.SubprocessError):
        pass
    errors = _last_errors()
    if errors:
        out.append("Last warnings/errors in ~/.config/sunshine/sunshine.log:")
        out.extend("  " + e for e in errors)
    return "\n".join(out)
