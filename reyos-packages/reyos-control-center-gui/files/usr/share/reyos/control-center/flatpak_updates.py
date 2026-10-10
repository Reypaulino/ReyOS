"""Qt-free Flatpak update helpers: which installed apps have a newer version
on their remote (what Discover shows), and a readable reason when
`flatpak update` fails."""
import platform
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

SCOPES = {
    "user": Path.home() / ".local" / "share" / "flatpak",
    "system": Path("/var/lib/flatpak"),
}
LOW_SPACE_BYTES = 1024 ** 3


def _columns(cmd, timeout=90):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.split("\t") for line in out.splitlines() if line.strip()]


def installed_apps():
    """{app_id: {"name", "version", "scope"}} for user and system installs."""
    apps = {}
    for scope in SCOPES:
        for row in _columns(["flatpak", "list", "--" + scope, "--app", "--columns=application,name,version"]):
            apps.setdefault(row[0], {
                "name": row[1] if len(row) > 1 else row[0],
                "version": row[2] if len(row) > 2 else "",
                "scope": scope,
            })
    return apps


def _appstream_version(scope, origin, app_id):
    # `remote-ls --version` is empty when a remote's summary doesn't carry it
    # (the Reyva repo); Discover reads the remote's AppStream catalog instead,
    # whose first <release> is the newest.
    path = SCOPES[scope] / "appstream" / origin / platform.machine() / "active" / "appstream.xml"
    if not path.is_file():
        return ""
    try:
        for _, elem in ET.iterparse(path):
            if elem.tag == "component":
                if elem.findtext("id") in (app_id, app_id + ".desktop"):
                    release = elem.find("releases/release")
                    return release.get("version", "") if release is not None else ""
                elem.clear()
    except (OSError, ET.ParseError):
        pass
    return ""


def available_updates():
    """Apps with a newer commit on their remote, user and system installs:
    [{"appId", "name", "installed", "version", "scope"}]."""
    installed = installed_apps()
    found = []
    for scope in SCOPES:
        rows = _columns(["flatpak", "remote-ls", "--" + scope, "--updates", "--app",
                         "--columns=application,version,origin"])
        if not rows:
            continue
        if any(len(r) < 2 or not r[1] for r in rows) and scope == "user":
            # Refreshes the user remotes' catalogs (no root needed), so the
            # fallback below sees the new release.
            _columns(["flatpak", "update", "--user", "--appstream", "--noninteractive"])
        for row in rows:
            app_id = row[0]
            version = row[1] if len(row) > 1 else ""
            if not version and len(row) > 2 and row[2]:
                version = _appstream_version(scope, row[2], app_id)
            info = installed.get(app_id, {})
            if version and version == info.get("version"):
                version = ""  # same release, rebuilt: don't show "1.0 → 1.0"
            found.append({
                "appId": app_id,
                "name": info.get("name", app_id),
                "installed": info.get("version", ""),
                "version": version,
                "scope": scope,
            })
    return found


def describe(update):
    old, new = update["installed"], update["version"]
    if old and new:
        return f"{update['name']} {old} → {new}"
    if new:
        return f"{update['name']} → {new}"
    return f"{update['name']} (new build)"


def free_space():
    try:
        return shutil.disk_usage(SCOPES["user"] if SCOPES["user"].exists() else Path.home()).free
    except OSError:
        return None


def human(n):
    return f"{n / 1024 ** 3:.1f} GB" if n >= 1024 ** 3 else f"{n // 1024 ** 2} MB"


def low_space_warning():
    free = free_space()
    if free is not None and free < LOW_SPACE_BYTES:
        return f"Only {human(free)} free on your disk -- Flatpak updates may not fit. Free some space first."
    return ""


def explain_failure(output_lines):
    """One-line reason for a failed `flatpak update`, from its output."""
    text = "\n".join(output_lines)
    if re.search(r"not enough disk space|no space left on device", text, re.I):
        free = free_space()
        where = f" (only {human(free)} free)" if free is not None else ""
        return f"Flatpak update failed: not enough disk space{where}. Free some space and try again."
    for line in reversed(output_lines):
        m = re.match(r"\s*(?:error|Error):\s*(.+)", line)
        if m:
            return "Flatpak update failed: " + m.group(1).strip()
    return "Flatpak update failed -- see the log."
