"""Qt-free check for the "Updates are ready" dialog Control Center shows when
it opens: ReyOS's own packages with a newer version in the reyos-local repo,
plus Flatpak apps (Reyva, emulators) with a newer version on their remote.
Reads the repo database over HTTPS like reyos-check-updates (the login
notifier) does, so it needs no password and doesn't touch pacman's own sync
databases."""
import io
import re
import subprocess
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

import flatpak_updates

PACMAN_CONF = Path("/etc/pacman.conf")
DEFAULT_SERVER = "https://reypaulino.github.io/ReyOS/"
FRIENDLY = {
    "reyos-control-center-gui": "Control Center",
    "reyos-control-center": "Control Center tools",
    "reyos-browser": "Reyva launcher",
    "reyos-reader": "ReyOS Reader",
    "reyos-welcome": "Welcome",
    "reyos-calamares": "Installer settings",
    "reyos-connect": "ReyOS Connect",
    "reyos-update-channel": "Stable update channel",
}


def _repo_db_url():
    try:
        text = PACMAN_CONF.read_text()
    except OSError:
        text = ""
    m = re.search(r"^\[reyos-local\][^\[]*?^Server\s*=\s*(\S+)", text, re.M | re.S)
    server = m.group(1) if m else DEFAULT_SERVER
    if not server.startswith("https://"):
        return None
    return server.rstrip("/") + "/reyos-local.db.tar.gz"


def _repo_versions():
    url = _repo_db_url()
    if not url:
        return {}
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError):
        return {}
    versions = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.name.endswith("/desc"):
                    continue
                lines = tar.extractfile(member).read().decode(errors="ignore").splitlines()
                fields = {lines[i]: lines[i + 1] for i in range(len(lines) - 1) if lines[i].startswith("%")}
                if "%NAME%" in fields and "%VERSION%" in fields:
                    versions[fields["%NAME%"]] = fields["%VERSION%"]
    except (tarfile.TarError, OSError):
        return {}
    return versions


def _newer(remote, local):
    out = subprocess.run(["vercmp", remote, local], capture_output=True, text=True).stdout.strip()
    try:
        return int(out) > 0
    except ValueError:
        return False


def reyos_updates():
    """[{"package", "name", "installed", "version"}] for installed reyos-*
    packages the repo has a newer version of."""
    remote = _repo_versions()
    if not remote:
        return []
    out = subprocess.run(["pacman", "-Q", *remote], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and _newer(remote[parts[0]], parts[1]):
            found.append({"package": parts[0], "name": FRIENDLY.get(parts[0], parts[0]),
                          "installed": parts[1], "version": remote[parts[0]]})
    return found


def check():
    """What the dialog lists: {"reyos": [...], "flatpaks": [...]}, each item
    with a "text" line ready to show."""
    reyos = reyos_updates()
    for u in reyos:
        u["text"] = f"{u['name']} {u['installed']} → {u['version']}"
    flatpaks = flatpak_updates.available_updates()
    for u in flatpaks:
        u["text"] = flatpak_updates.describe(u)
    return {"reyos": reyos, "flatpaks": flatpaks}
