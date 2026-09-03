"""VPN detection/status for ReyOS Connect's Remote Access page.

Two real backends are detected, never bundled/auto-installed:

- Tailscale: found live on the user's own host during Phase 0 audit
  (`tailscale status --json`, already authenticated, a real tailnet
  including an iPhone entry). Never calls `tailscale login` -- toggling
  is only offered once `tailscale status --json` already reports the
  node as authenticated, and goes through `pkexec` (a real graphical
  auth prompt) rather than bare `sudo`, since ReyOS's sudoers only grants
  NOPASSWD for a fixed set of ReyOS-shipped commands (see
  `shellprocess_sudoers_reyos_menu.conf`) and Tailscale isn't one of
  them -- a bare `sudo tailscale up` from this GUI would hang with no
  controlling terminal, the same class of bug documented in that file
  for unlisted pacman/systemctl calls.

- WireGuard: ReyOS Control Center already has two independent, real
  mechanisms for this (see docs/connect.md's v2 audit) -- raw
  `wg-quick@<name>.service` units driven from `/etc/wireguard/*.conf`
  (VpnPage.qml), and NetworkManager-imported connections (NetworkPage.qml).
  This module detects both and merges them into one interface list
  rather than picking one as canonical. `/etc/wireguard` is root-only
  (0700, confirmed live) -- Control Center's own `Path(...).glob(...)`
  silently returns an empty list for a normal user there (PermissionError
  swallowed by its bare `except Exception`), which means its "Profiles"
  list is quietly broken for imported-but-never-started profiles. This
  module works around that by reading `systemctl list-units` for
  `wg-quick@*` instead (always readable, no root needed, and also
  reports live active state in the same call) as the primary source,
  falling back to the `/etc/wireguard` glob only to catch profiles that
  have been imported but never started -- and reports `profilesReadable`
  honestly rather than pretending "empty" means "none configured."
"""
import json
import shutil
import socket
import subprocess
from pathlib import Path

WIREGUARD_DIR = Path("/etc/wireguard")


def _run(cmd, timeout=6):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def tcp_reachable(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# -- Tailscale ---------------------------------------------------------

def tailscale_installed():
    return shutil.which("tailscale") is not None


def tailscale_status():
    empty = {
        "installed": False, "running": False, "authenticated": False,
        "connected": False, "backendState": "", "selfIp": "", "peers": [],
    }
    if not tailscale_installed():
        return empty
    result = _run(["tailscale", "status", "--json"])
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return {**empty, "installed": True}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {**empty, "installed": True, "error": "Could not parse tailscale status."}

    backend_state = data.get("BackendState", "")
    running = backend_state == "Running"
    authenticated = bool(data.get("HaveNodeKey")) and backend_state != "NeedsLogin"
    self_ips = data.get("TailscaleIPs") or []
    peers = []
    for peer in (data.get("Peer") or {}).values():
        ips = peer.get("TailscaleIPs") or []
        # DNSName (the tailnet-registered device name) is preferred over
        # HostName -- confirmed live that Tailscale's iOS client reports
        # HostName as the literal string "localhost" for every iPhone,
        # which would otherwise silently mismatch against a "contains
        # iphone" name search below.
        dns_name = (peer.get("DNSName") or "").split(".")[0]
        peers.append({
            "name": dns_name or peer.get("HostName") or "unknown",
            "ip": ips[0] if ips else "",
            "online": bool(peer.get("Online")),
            "os": peer.get("OS", ""),
        })
    return {
        "installed": True,
        "running": running,
        "authenticated": authenticated,
        "connected": running and authenticated,
        "backendState": backend_state,
        "selfIp": self_ips[0] if self_ips else "",
        "peers": peers,
    }


def tailscale_set_connected(connect):
    status = tailscale_status()
    if not status["authenticated"]:
        return False, ("Tailscale isn't logged in yet. Authenticate it once from a terminal "
                        "(`tailscale up`) or Control Center -- ReyOS Connect never starts a login flow.")
    if not shutil.which("pkexec"):
        return False, "pkexec is required to change Tailscale's connection state."
    result = _run(["pkexec", "tailscale", "up" if connect else "down"], timeout=20)
    if result is None:
        return False, "Timed out talking to tailscaled."
    ok = result.returncode == 0
    if ok:
        return True, "Connected." if connect else "Disconnected."
    return False, (result.stderr.strip() or "Failed.")


# -- WireGuard -----------------------------------------------------------

def _wg_quick_units():
    result = _run(["systemctl", "list-units", "--all", "--type=service", "--plain", "--no-legend", "wg-quick@*"])
    units = {}
    if result is None:
        return units
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("wg-quick@"):
            continue
        unit = parts[0]
        name = unit[len("wg-quick@"):]
        if name.endswith(".service"):
            name = name[: -len(".service")]
        active = len(parts) >= 3 and parts[2] == "active"  # UNIT LOAD ACTIVE SUB ...
        units[name] = {"name": name, "active": active, "source": "wg-quick"}
    return units


def _wg_quick_conf_profiles():
    try:
        return sorted(p.stem for p in WIREGUARD_DIR.glob("*.conf"))
    except PermissionError:
        return None
    except OSError:
        return []


def _nmcli_wireguard():
    result = _run(["nmcli", "-t", "-f", "NAME,TYPE,ACTIVE", "connection", "show"])
    conns = []
    if result is None:
        return conns
    for line in result.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] == "wireguard":
            conns.append({"name": parts[0], "active": parts[2] == "yes", "source": "networkmanager"})
    return conns


def wireguard_status():
    units = _wg_quick_units()
    conf_profiles = _wg_quick_conf_profiles()
    if conf_profiles:
        for name in conf_profiles:
            units.setdefault(name, {"name": name, "active": False, "source": "wg-quick"})
    interfaces = list(units.values()) + _nmcli_wireguard()
    active = next((i["name"] for i in interfaces if i["active"]), "")
    return {
        "installed": shutil.which("wg") is not None or shutil.which("nmcli") is not None,
        "interfaces": interfaces,
        "active": active,
        "profilesReadable": conf_profiles is not None,
    }


def wireguard_connect(name, source):
    if source == "networkmanager":
        result = _run(["nmcli", "connection", "up", name], timeout=15)
    else:
        result = _run(["sudo", "systemctl", "start", f"wg-quick@{name}"], timeout=15)
    if result is None:
        return False, "Timed out."
    ok = result.returncode == 0
    return ok, (f"Connected: {name}" if ok else (result.stderr.strip() or "Failed to connect."))


def wireguard_disconnect(name, source):
    if source == "networkmanager":
        result = _run(["nmcli", "connection", "down", name], timeout=15)
    else:
        result = _run(["sudo", "systemctl", "stop", f"wg-quick@{name}"], timeout=15)
    if result is None:
        return False, "Timed out."
    ok = result.returncode == 0
    return ok, ("Disconnected." if ok else (result.stderr.strip() or "Failed to disconnect."))


def detect_backends():
    return {"tailscale": tailscale_installed(), "wireguard": shutil.which("wg") is not None}


# -- Remote Connection Test ----------------------------------------------

def test_remote_connection(backend, peer_ip=None, peer_name_hint="iphone", check_ssh=False):
    """Every check here is a real attempt made now, never inferred from
    whether the backend is merely installed."""
    checks = []

    if backend == "tailscale":
        status = tailscale_status()
        checks.append({"check": "VPN", "passed": status["connected"],
                        "detail": "Tailscale is connected." if status["connected"] else "Tailscale is not connected."})
        checks.append({"check": "Private VPN address", "passed": bool(status["selfIp"]),
                        "detail": status["selfIp"] or "No Tailscale IP assigned yet."})
        peer = None
        if peer_ip:
            peer = next((p for p in status["peers"] if p["ip"] == peer_ip), None)
        if peer is None:
            # OS is a more reliable signal than name -- Tailscale's iOS
            # client's own HostName field is unreliable (see tailscale_status).
            peer = next((p for p in status["peers"] if p.get("os") == "iOS"), None)
        if peer is None:
            peer = next((p for p in status["peers"] if peer_name_hint in p["name"].lower()), None)
        if peer:
            checks.append({"check": "iPhone reachable", "passed": peer["online"],
                            "detail": (f"{peer['name']} is online on the tailnet." if peer["online"]
                                       else f"{peer['name']} is offline -- check the phone's Tailscale app is connected.")})
            peer_ip = peer["ip"]
        else:
            checks.append({"check": "iPhone reachable", "passed": False, "detail": "No iPhone found in the tailnet yet."})
    else:
        wg = wireguard_status()
        checks.append({"check": "VPN", "passed": bool(wg["active"]),
                        "detail": (f"WireGuard interface active: {wg['active']}" if wg["active"]
                                   else "No active WireGuard interface.")})
        checks.append({"check": "Private VPN address", "passed": bool(wg["active"]),
                        "detail": "WireGuard doesn't report a plain address the way Tailscale does -- checked via interface state instead."})
        peer_ok = bool(peer_ip) and tcp_reachable(peer_ip, 443, 3)
        checks.append({"check": "iPhone reachable", "passed": peer_ok,
                        "detail": ("Reachable." if peer_ok else
                                   "No reachability signal -- WireGuard has no per-peer online state; provide the phone's VPN IP to test directly.")})

    if peer_ip and all(c["passed"] for c in checks):
        kdeconnect_ok = tcp_reachable(peer_ip, 1716, timeout=3)
        checks.append({"check": "KDE Connect", "passed": kdeconnect_ok,
                        "detail": ("KDE Connect's port (1716) is reachable over VPN." if kdeconnect_ok
                                   else "KDE Connect isn't reachable yet -- open the KDE Connect app on the phone.")})
    else:
        checks.append({"check": "KDE Connect", "passed": False, "detail": "Skipped -- VPN/peer checks failed first."})

    if check_ssh:
        from providers.remote_provider import ssh_status
        sshd = ssh_status()
        checks.append({"check": "SSH", "passed": sshd["active"],
                        "detail": ("SSH server is running -- reachable over VPN once connected." if sshd["active"]
                                   else "SSH server is not enabled on this device.")})

    return {"checks": checks, "ready": all(c["passed"] for c in checks)}
