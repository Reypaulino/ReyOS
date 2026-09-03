"""SSH/Remote Desktop detection and the safe Remote Commands registry.

Remote Commands is a fixed, ReyOS-curated list -- there is no free-text
command field anywhere in this module or its QML. Each entry maps to one
real, fixed local command (no phone-supplied text ever reaches a shell).
Written into the same on-disk format KDE Connect's own runcommand plugin
reads (confirmed against the real installed daemon + v26.08.0 source, see
docs/connect.md's v2 audit) via PySide6's own QSettings, matching Qt's own
serialization instead of hand-rolling INI escaping.
"""
import getpass
import shutil
import socket
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QSettings

REMOTE_COMMANDS = {
    "lock": {"name": "Lock ReyOS", "command": "loginctl lock-session"},
    "browser": {"name": "Open Browser", "command": "reyos-browser"},
    "reader": {"name": "Open Reader", "command": "reyos-reader"},
    "control-center": {"name": "Open Control Center", "command": "/usr/share/reyos/control-center/main.py"},
    "screenshot": {"name": "Take Screenshot", "command": "spectacle -b -n"},
    "mute": {"name": "Mute Audio", "command": "pactl set-sink-mute @DEFAULT_SINK@ toggle"},
    "pause-media": {
        "name": "Pause Media",
        "command": "bash -c 'for s in $(qdbus6 | grep org.mpris.MediaPlayer2.); "
                   "do qdbus6 $s /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause; done'",
    },
}


def _run(cmd, timeout=6):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


# -- SSH -------------------------------------------------------------------

def ssh_status():
    installed = shutil.which("sshd") is not None
    enabled_r = _run(["systemctl", "is-enabled", "sshd"])
    active_r = _run(["systemctl", "is-active", "sshd"])
    enabled = bool(enabled_r and enabled_r.stdout.strip() == "enabled")
    active = bool(active_r and active_r.stdout.strip() == "active")
    return {"installed": installed, "enabled": enabled, "active": active}


def ssh_connection_info():
    """Real local addresses to show the user "ssh <user>@<address>" for --
    not a static/guessed hostname. Uses `ip addr` (iproute2, always present
    -- unlike the `hostname` binary, which this Arch-based system does not
    ship by default; confirmed live: `hostname -I` fails outright with
    "command not found") to list every global-scope IPv4 address currently
    assigned across all interfaces (LAN, VPN, etc)."""
    addresses = []
    result = _run(["ip", "-4", "-o", "addr", "show", "scope", "global"])
    if result and result.stdout.strip():
        for line in result.stdout.splitlines():
            parts = line.split()
            for i, tok in enumerate(parts):
                if tok == "inet" and i + 1 < len(parts):
                    addresses.append(parts[i + 1].split("/")[0])
                    break
    return {"user": getpass.getuser(), "hostname": socket.gethostname(), "addresses": addresses}


# -- Remote Desktop ----------------------------------------------------------
#
# Real backend, confirmed live on the Dev VM (2026-09-02): `krdp` (package
# `krdp`, in the official `extra` repo -- part of Plasma 6 itself, not a
# third-party add-on) provides `/usr/bin/krdpserver`, a user-session RDP
# server built on the standard XDG `org.freedesktop.portal.RemoteDesktop`/
# `ScreenCast` portals (confirmed from its own binary symbols: `PortalSession`,
# `zkde_screencast_unstable_v1`) -- the maintained, Wayland-native mechanism
# the spec asks for, not anything reimplemented here. Its real systemd
# --user unit is `app-org.kde.krdpserver.service` (the "krdp" unit name
# `remote_desktop_status()` guessed before this was ever installed and
# checked was wrong -- corrected here against the real package). KDE's own
# shipped preset (`00-krdp.preset`) explicitly disables it by default
# ("This service should never be enabled by default, irrespective of distro
# policy") -- ReyOS Connect never overrides that.
#
# Credentials are handled entirely by KDE's own System Settings module
# (`kcm_krdpserver`, KWallet/QtKeychain-backed -- confirmed via the binary's
# own `QKeychain::ReadPasswordJob` symbols and its
# "No users configured for login... configure users using kcm_krdp" error
# string) -- ReyOS Connect never stores or reads a password itself, it only
# opens that real settings page (`systemsettings kcm_krdpserver`, the exact
# `Exec=` line from the real `kcm_krdpserver.desktop`) for the user to set
# credentials through KDE's own secure flow, the same pattern already used
# for "VPN Settings" opening Control Center.

KRDP_UNIT = "app-org.kde.krdpserver.service"

_REMOTE_DESKTOP_BACKENDS = [
    {"id": "krdp", "label": "KDE Plasma Remote Desktop (KRDP)", "binary": "krdpserver", "unit": KRDP_UNIT, "user_unit": True},
    {"id": "xrdp", "label": "xrdp", "binary": "xrdp", "unit": "xrdp", "user_unit": False},
    {"id": "vnc", "label": "TigerVNC", "binary": "Xtigervnc", "unit": None, "user_unit": False},
]


def remote_desktop_status():
    for backend in _REMOTE_DESKTOP_BACKENDS:
        if shutil.which(backend["binary"]):
            enabled = False
            active = False
            if backend["unit"]:
                base = ["systemctl", "--user"] if backend["user_unit"] else ["systemctl"]
                enabled_r = _run(base + ["is-enabled", backend["unit"]])
                active_r = _run(base + ["is-active", backend["unit"]])
                enabled = bool(enabled_r and enabled_r.stdout.strip() == "enabled")
                active = bool(active_r and active_r.stdout.strip() == "active")
            return {
                "available": True,
                "backendId": backend["id"],
                "backend": backend["label"],
                "enabled": enabled,
                "active": active,
            }
    return {"available": False, "backendId": "", "backend": "", "enabled": False, "active": False}


def open_remote_desktop_settings():
    """Opens KDE's real "Remote Desktop" System Settings page -- the actual
    `Exec=` line from `kcm_krdpserver.desktop` -- rather than reimplementing
    user/password configuration."""
    from PySide6.QtCore import QProcess
    return QProcess.startDetached("systemsettings", ["kcm_krdpserver"])


def start_remote_desktop():
    """Starts the already-configured krdpserver session unit. Never called
    automatically -- only from an explicit user click.

    Real gotcha found by actually running this against the Dev VM's real
    krdpserver (not inferred): `systemctl --user start` returns success the
    instant `krdpserver`'s exec() call succeeds (`Type=exec`), *not* once
    it's actually up -- with no username/password configured yet, the
    process starts, logs "No users configured for login...", and exits
    (status 255) well under a second later. A start call that only checked
    the initial `systemctl` exit code would have reported this as a
    success. Fixed by re-checking `is-active` after a short settle delay
    and, if it already died, pulling the real reason from the unit's own
    status output rather than claiming PASS on the initial exit code alone."""
    r = _run(["systemctl", "--user", "start", KRDP_UNIT], timeout=10)
    if not r or r.returncode != 0:
        return False, (r.stderr.strip() if r and r.stderr else "systemctl start failed")
    time.sleep(1)
    active_r = _run(["systemctl", "--user", "is-active", KRDP_UNIT])
    if active_r and active_r.stdout.strip() == "active":
        return True, ""
    status_r = _run(["systemctl", "--user", "status", KRDP_UNIT, "--no-pager", "-n", "5"])
    detail = status_r.stdout.strip() if status_r and status_r.stdout else "krdpserver exited immediately after starting."
    for line in detail.splitlines():
        if "krdpserver[" in line and "]: " in line:
            detail = line.split("]: ", 1)[-1].strip()
            break
    return False, f"{detail} (set a username/password via Remote Desktop Settings first.)"


def stop_remote_desktop():
    r = _run(["systemctl", "--user", "stop", KRDP_UNIT], timeout=10)
    ok = bool(r and r.returncode == 0)
    return ok, ("" if ok else (r.stderr.strip() if r else "systemctl call failed"))


# -- Remote Commands registry ------------------------------------------------

def _runcommand_config_path(device_id):
    return Path.home() / ".config" / "kdeconnect" / device_id / "kdeconnect_runcommand" / "config"


def read_enabled_commands(device_id):
    """Which of REMOTE_COMMANDS keys are currently written into the
    device's runcommand config, keyed by our own fixed ids (matched back
    by command string, since the on-disk id is whatever we wrote)."""
    path = _runcommand_config_path(device_id)
    if not path.exists():
        return []
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    raw = settings.value("commands", "{}")
    import json
    try:
        stored = json.loads(raw) if isinstance(raw, str) else {}
    except (json.JSONDecodeError, TypeError):
        return []
    stored_commands = {entry.get("command") for entry in stored.values() if isinstance(entry, dict)}
    return [cmd_id for cmd_id, spec in REMOTE_COMMANDS.items() if spec["command"] in stored_commands]


def write_enabled_commands(device_id, enabled_ids):
    """Overwrites the device's runcommand config with exactly the enabled
    subset of REMOTE_COMMANDS -- no other id is ever accepted, so nothing
    outside this fixed registry can end up in the file this function writes."""
    path = _runcommand_config_path(device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        cmd_id: {"name": REMOTE_COMMANDS[cmd_id]["name"], "command": REMOTE_COMMANDS[cmd_id]["command"]}
        for cmd_id in enabled_ids if cmd_id in REMOTE_COMMANDS
    }
    import json
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setValue("commands", json.dumps(payload))
    settings.sync()
    return settings.status() == QSettings.Status.NoError
