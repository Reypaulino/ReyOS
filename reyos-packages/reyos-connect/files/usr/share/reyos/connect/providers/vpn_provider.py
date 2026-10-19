"""VPN detection/status for ReyOS Connect's Remote Access page.

Two real backends are detected, never bundled/auto-installed:

- Tailscale: ships with reyos-connect but stays off until the user turns
  it on from the VPN page. "Set up Tailscale" runs the root helper
  `reyos-connect-tailscale setup` through pkexec (one password prompt):
  it starts tailscaled and makes the user Tailscale's operator, so sign-in,
  connect and disconnect then run as the user, without a password.
  Every `tailscale up` repeats `--operator=<user>`: a plain `tailscale up`
  resets prefs not mentioned and silently drops the operator (confirmed
  live), after which every command says "Access denied". If the user set
  other options by hand (e.g. --hostname), tailscale refuses and prints
  the command that restates them; that command is used instead of
  --reset, so nothing the user chose is lost.

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
import getpass
import json
import re
import shlex
import shutil
import socket
import subprocess
from pathlib import Path

WIREGUARD_DIR = Path("/etc/wireguard")
TAILSCALE_HELPER = "/usr/share/reyos/connect/reyos-connect-tailscale"
LOGIN_URL = re.compile(r"https://login\.tailscale\.com/\S+")


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
        "serviceActive": False, "canControl": False, "authUrl": "",
    }
    if not tailscale_installed():
        return empty
    active = _run(["systemctl", "is-active", "tailscaled"])
    empty = {**empty, "installed": True,
             "serviceActive": bool(active and active.stdout.strip() == "active")}
    if not empty["serviceActive"]:
        return empty
    empty["canControl"] = tailscale_operator() == getpass.getuser()
    result = _run(["tailscale", "status", "--json"])
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return empty
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
        **empty,
        "authUrl": data.get("AuthURL") or "",
        "running": running,
        "authenticated": authenticated,
        "connected": running and authenticated,
        "backendState": backend_state,
        "selfIp": self_ips[0] if self_ips else "",
        "peers": peers,
    }


def _tailscale_prefs():
    result = _run(["tailscale", "debug", "prefs"])
    if result is None or result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def tailscale_operator():
    """The account allowed to control Tailscale without root ("" if none)."""
    return _tailscale_prefs().get("OperatorUser", "")


def tailscale_up_command():
    # Before the first sign-in tailscale doesn't refuse an `up` that leaves
    # out a hand-set device name, it just drops it, so keep it explicitly.
    cmd = ["tailscale", "up", f"--operator={getpass.getuser()}"]
    hostname = _tailscale_prefs().get("Hostname", "")
    if hostname:
        cmd.append(f"--hostname={hostname}")
    return cmd


def suggested_up_command(output):
    """tailscale's own "re-run with all non-default flags" command, if it
    printed one (only a plain `tailscale up --flag=value ...`)."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("tailscale up "):
            try:
                cmd = shlex.split(line)
            except ValueError:
                return None
            if all(a.startswith("--") for a in cmd[2:]):
                return cmd
    return None


def tailscale_setup():
    """Starts tailscaled and makes this user its operator (password prompt)."""
    if not shutil.which("pkexec"):
        return False, "pkexec is missing, so Tailscale can't be set up from here."
    result = _run(["pkexec", TAILSCALE_HELPER, "setup"], timeout=90)
    if result is None:
        return False, "Setting up Tailscale took too long."
    if result.returncode == 126:
        return False, "Not set up: the password prompt was cancelled."
    if result.returncode == 127:
        return False, "Not set up: the password wasn't accepted, or no password prompt could be shown."
    if result.returncode != 0:
        return False, (result.stderr.strip().splitlines() or ["Couldn't set up Tailscale."])[-1]
    return True, "Tailscale is on. Sign in to add this computer to your Tailscale network."


def tailscale_off():
    if not shutil.which("pkexec"):
        return False, "pkexec is missing, so Tailscale can't be turned off from here."
    result = _run(["pkexec", TAILSCALE_HELPER, "off"], timeout=60)
    if result is None:
        return False, "Turning Tailscale off took too long."
    if result.returncode == 126:
        return False, "Not turned off: the password prompt was cancelled."
    if result.returncode == 127:
        return False, "Not turned off: the password wasn't accepted, or no password prompt could be shown."
    if result.returncode != 0:
        return False, (result.stderr.strip().splitlines() or ["Couldn't turn Tailscale off."])[-1]
    return True, "Tailscale is off."


def tailscale_set_connected(connect):
    status = tailscale_status()
    if not status["authenticated"]:
        return False, "Sign in to Tailscale first."
    if not status["canControl"]:
        return False, "Press \"Set up Tailscale\" once so ReyOS Connect may control it."
    if not connect:
        result = _run(["tailscale", "down"], timeout=20)
        if result is None:
            return False, "Timed out talking to Tailscale."
        return (True, "Disconnected.") if result.returncode == 0 else (False, result.stderr.strip() or "Failed.")
    cmd = tailscale_up_command()
    for _ in range(2):
        result = _run(cmd, timeout=30)
        if result is None:
            return False, "Timed out talking to Tailscale."
        if result.returncode == 0:
            return True, "Connected."
        suggested = suggested_up_command(result.stderr + result.stdout)
        if not suggested or suggested == cmd:
            break
        cmd = suggested
    return False, (result.stderr.strip().splitlines() or ["Failed."])[-1]


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
        result = _run(["sudo", "-n", "/usr/share/reyos/bin/reyos-admin", "vpn", "up", name], timeout=15)
    if result is None:
        return False, "Timed out."
    ok = result.returncode == 0
    return ok, (f"Connected: {name}" if ok else (result.stderr.strip() or "Failed to connect."))


def wireguard_disconnect(name, source):
    if source == "networkmanager":
        result = _run(["nmcli", "connection", "down", name], timeout=15)
    else:
        result = _run(["sudo", "-n", "/usr/share/reyos/bin/reyos-admin", "vpn", "down", name], timeout=15)
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
