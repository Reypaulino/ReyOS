#!/usr/bin/env python3
import colorsys
import configparser
import glob
import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import setproctitle
except ModuleNotFoundError:
    setproctitle = None

from PySide6.QtCore import QObject, Signal, Slot, QThread, QUrl, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

APP_DIR = Path(__file__).resolve().parent
from looks import (  # Qt-free Look / Light-Dark helpers, also run at login
    LOOKS_DIR, LIGHT_LOOKANDFEEL, PANEL_OPACITY_DEFAULT, _LIGHT_BASE_SCHEME,
    _kread, _kwrite, _look_parser, _is_light_mode, _current_look_id,
    _look_accent_rgb, _scheme_for, _panel_opacity, _write_panel_theme,
    _recolor_look_assets,
)
import emulation  # Qt-free emulation helpers (systems, settings, BIOS, controllers)
from emulation import EMU_SYSTEMS, GAMES_DIR, RETROARCH_REYOS_CFG


def _reyos_accent_color():
    # ReyOSStyle.qml's accent used to be hardcoded to the copper default, so
    # switching Looks here never actually updated Control Center's own chrome
    # until the next unrelated relaunch. kdeglobals only carries real
    # Colors:Selection values after plasma-apply-colorscheme has run at least
    # once; the copper default covers the pre-branding case.
    try:
        out = subprocess.run(
            ["kreadconfig6", "--file", "kdeglobals", "--group", "Colors:Selection", "--key", "DecorationFocus"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        r, g, b = (int(x) for x in out.split(","))
        return QColor(r, g, b)
    except Exception:
        return QColor("#C97932")

# reyos-* packages "Update ReyOS Apps" should always backfill onto an
# already-installed system if missing -- installed alongside whatever's
# already-installed-and-upgradable, not just upgraded. Two cases: apps
# dropped from the base ISO (kept optional to stay lean) that a user may
# have skipped/unchecked in Welcome's first-login picker (reyos-reader),
# and new reyos-* packages.x86_64 additions that existing installs never
# had a chance to install at all, since the package didn't exist yet at
# their install time (reyos-shortcuts-cheatsheet, added 2026-09-15).
REYOS_DEFAULT_APPS = ["reyos-reader", "reyos-shortcuts-cheatsheet"]

# Emulation (Gaming page). One frontend -- RetroArch -- with one official-repo
# libretro core per system, installed on demand by reyos-install-emulators.sh
# (its case list must match these ids). ReyOS never ships games or BIOS files;
# users add their own under ~/Games/ROMs/<id>/ and ~/Games/BIOS/.


PKG_ACTIONS = {
    "check":   (["sudo", "-n", "pacman", "-Sy"], None),
    "upgrade": (["sudo", "-n", "pacman", "-Syu", "--noconfirm"], None),
    # "full" and "clean" are handled specially in PkgWorker (multiple commands).
    "full":    (None, None),
    "clean":   (None, None),
}


DEFAULT_APP_CATEGORIES = [
    {"key": "documents", "label": "Documents / PDF", "mimetypes": ["application/pdf"]},
    {"key": "browser", "label": "Web Browser", "mimetypes": ["x-scheme-handler/http", "x-scheme-handler/https", "text/html"]},
    {"key": "images", "label": "Image Viewer", "mimetypes": ["image/png", "image/jpeg", "image/gif", "image/bmp", "image/svg+xml", "image/webp"]},
    {"key": "text", "label": "Text Editor", "mimetypes": ["text/plain"]},
    {"key": "video", "label": "Video Player", "mimetypes": ["video/mp4", "video/x-matroska", "video/webm", "video/mpeg"]},
    {"key": "music", "label": "Music Player", "mimetypes": ["audio/mpeg", "audio/x-wav", "audio/flac", "audio/ogg"]},
    {"key": "filemanager", "label": "File Manager", "mimetypes": ["inode/directory"]},
]


def _desktop_entries():
    # ~/.local/share/applications second so a user-level override of a
    # same-named .desktop file (e.g. a user's own launcher tweak) wins over
    # the system one, matching normal XDG precedence.
    dirs = ["/usr/share/applications", str(Path.home() / ".local/share/applications")]
    entries = {}
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.desktop")):
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            display = f.name
            mimetypes = set()
            no_display = False
            for line in text.splitlines():
                if line.startswith("Name=") and display == f.name:
                    display = line[len("Name="):].strip()
                elif line.startswith("MimeType="):
                    mimetypes |= {m for m in line[len("MimeType="):].split(";") if m}
                elif line.startswith("NoDisplay=true"):
                    no_display = True
            if not no_display:
                entries[f.name] = {"name": display, "desktopId": f.name, "mimetypes": mimetypes}
    return entries


_AUTOSTART_USER_DIR = Path.home() / ".config" / "autostart"
_APPLICATION_DIRS = [
    Path("/usr/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path.home() / ".local/share/applications",
]
# Desktop plumbing that also starts through autostart; switching any of these
# off breaks the panel, sign-in prompts, tray or accessibility.
_SESSION_PLUMBING = {
    "org.kde.plasmashell.desktop", "polkit-kde-authentication-agent-1.desktop", "kglobalacceld.desktop",
    "powerdevil.desktop", "at-spi-dbus-bus.desktop", "xembedsniproxy.desktop", "gmenudbusmenuproxy.desktop",
    "xapp-sn-watcher.desktop", "org.kde.plasma-fallback-session-restore.desktop", "kaccess.desktop",
    "xdg-user-dirs.desktop", "reyos-top-panel-update.desktop", "reyos-installer.desktop",
}


def _autostart_system_dirs():
    dirs = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    return [Path(d) / "autostart" for d in dirs.split(":") if d and (Path(d) / "autostart").is_dir()]


def _valid_desktop_id(entry_id):
    return bool(re.fullmatch(r"[A-Za-z0-9_.+-]+\.desktop", entry_id or "")) and ".." not in entry_id


def _read_desktop_entry(path):
    fields, in_entry = {}, False
    try:
        lines = Path(path).read_text(errors="ignore").splitlines()
    except OSError:
        return fields
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            in_entry = s == "[Desktop Entry]"
            continue
        if in_entry and "=" in s and not s.startswith("#"):
            key, value = s.split("=", 1)
            fields.setdefault(key.strip(), value.strip())
    return fields


def _set_desktop_keys(path, updates):
    # Keys go inside [Desktop Entry]; appending at the end of the file would
    # land them in a [Desktop Action ...] group and be ignored.
    lines = Path(path).read_text(errors="ignore").splitlines()
    out, in_entry, written = [], False, False
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            if in_entry and not written:
                out.extend(f"{k}={v}" for k, v in updates.items())
                written = True
            in_entry = s == "[Desktop Entry]"
        elif in_entry and "=" in s and s.split("=", 1)[0].strip() in updates:
            continue
        out.append(line)
    if not written:
        out.extend(f"{k}={v}" for k, v in updates.items())
    Path(path).write_text("\n".join(out) + "\n")


def _shown_in_kde(fields):
    only = [x for x in fields.get("OnlyShowIn", "").split(";") if x]
    never = [x for x in fields.get("NotShowIn", "").split(";") if x]
    return (not only or "KDE" in only) and "KDE" not in never


def _is_session_plumbing(file_name, fields):
    return (file_name in _SESSION_PLUMBING
            or fields.get("X-KDE-autostart-phase", "") in ("PreInitialization", "0"))


def _autostart_item(entry_id, fields, system, enabled):
    return {
        "id": entry_id,
        "name": fields.get("Name", entry_id.removesuffix(".desktop")),
        "comment": fields.get("Comment", ""),
        "icon": fields.get("Icon", ""),
        "system": system,
        "builtin": entry_id.startswith("reyos-"),
        "isEnabled": enabled,
    }


def _is_live_session():
    # /run/archiso/airootfs (the old check here) no longer exists on current
    # archiso builds -- confirmed live on a genuine live boot (2026-08-31,
    # ls /run/archiso: "No such file or directory"), which silently broke
    # this function into always returning False. That disabled two real
    # safety guards (blocking package updates and Steam installs on the live
    # session) with no visible symptom, since a False-negative here just lets
    # the disabled action run instead of erroring. The kernel command line's
    # archiso parameters are the actual stable, version-independent marker
    # mkarchiso sets for a live boot -- confirmed absent on a real installed
    # system's cmdline the same session.
    try:
        cmdline = Path("/proc/cmdline").read_text()
    except OSError:
        return False
    return "archisobasedir=" in cmdline or "archisolabel=" in cmdline


def _record_successful_update(progress_emit=None):
    """Reset the login reminder after a successful system update."""
    try:
        (Path.home() / ".last_pkg_update").touch()
    except OSError as exc:
        # The package transaction already succeeded, so a reminder-state
        # write failure should be visible without misreporting the update as
        # failed.
        if progress_emit:
            progress_emit(f"Warning: could not reset the update reminder: {exc}")


def _run(cmd, progress_emit=None):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    for line in proc.stdout:
        if progress_emit:
            progress_emit(line.rstrip())
    return proc.wait()


# For tools whose output is parsed (lpstat, scanimage translate theirs).
_C_LOCALE = dict(os.environ, LC_ALL="C")


def _nmcli_fields(line):
    # `nmcli -t` separates fields with ':' and escapes a ':' or '\' inside a
    # value as '\:' / '\\' -- a plain split(":") cut SSIDs and connection
    # names containing ':' (e.g. "ADC-V723 (24:CE:A4)") into wrong columns.
    fields, cur, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if c == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    fields.append("".join(cur))
    return fields


def _restart_plasmashell_and_wait(timeout=30):
    # kquitapp6 sends a graceful quit request and returns immediately --
    # it does NOT block until the old process actually releases its D-Bus
    # name/rendering surfaces. Firing kstart right after it (as this code
    # used to, in both applyLook() and applyLookAndFeel()) is a real race:
    # if the old process hasn't finished tearing down yet, the new kstart
    # can silently lose to it and no fresh process ever actually takes
    # over, leaving the still-dying old one to just keep running with its
    # already-cached (pre-switch) icon state. That matches a real report:
    # a Look's icon looking stale until Apply is clicked a second time,
    # which just gives the race another, independently-timed shot at
    # succeeding. reyos-apply-branding.sh's restart_plasmashell_for_icons()
    # already solved this the same way for the branding-apply path -- poll
    # for the new process to actually reappear before moving on, instead
    # of firing both commands back-to-back and hoping.
    subprocess.run(["kquitapp6", "plasmashell"], capture_output=True)
    subprocess.Popen(
        ["kstart", "plasmashell"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(timeout):
        if subprocess.run(["pgrep", "-x", "plasmashell"], capture_output=True).returncode == 0:
            break
        time.sleep(1)
    time.sleep(2)


def _wait_for_pacman_lock(progress_emit=None, timeout=60):
    """pacman's db lock (/var/lib/pacman/db.lck) is exclusive -- a second
    concurrent pacman invocation (this app's own Full Update still running
    while a manual `pacman -S` happens in a terminal, or two Control Center
    actions overlapping) fails outright with a raw "unable to lock database"
    error instead of queueing. Wait for the lock to clear rather than
    failing immediately; still give up after `timeout` so a genuinely stuck
    lock (a crashed pacman) doesn't hang this app forever."""
    lock_path = Path("/var/lib/pacman/db.lck")
    if not lock_path.exists():
        return True
    if progress_emit:
        progress_emit("Waiting for another package operation to finish...")
    waited = 0
    while lock_path.exists() and waited < timeout:
        time.sleep(1)
        waited += 1
    if lock_path.exists() and progress_emit:
        progress_emit(f"Still locked after {timeout}s -- proceeding anyway.")
    return not lock_path.exists()


# Per-user diagnostics: failed actions (the same one-line message the UI
# shows -- never a password or other input) and the full output of the last
# package operation. Kept small: the failure log is cut back when it grows.
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "reyos"
FAILURE_LOG = STATE_DIR / "control-center.log"
PKG_LOG = STATE_DIR / "last-package-operation.log"


def _log_failure(kind, ok, message):
    if ok:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if FAILURE_LOG.is_file() and FAILURE_LOG.stat().st_size > 512 * 1024:
            FAILURE_LOG.write_text(FAILURE_LOG.read_text(errors="replace")[-256 * 1024:])
        with FAILURE_LOG.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {kind} FAILED: {message}\n")
    except OSError:
        pass


class _ThreadKeeper(QObject):
    # Dropping the last reference to a running QThread aborts the whole app
    # (qFatal), and every page replaces its worker attribute when reopened.
    # Hold each started worker here until its thread has really finished.
    def __init__(self):
        super().__init__()
        self._live = set()

    def keep(self, thread):
        self._live.add(thread)
        thread.finished.connect(self._release)

    @Slot()
    def _release(self):
        thread = self.sender()
        if thread in self._live:
            thread.wait()
            self._live.discard(thread)

    def wait_all(self):
        for thread in list(self._live):
            thread.wait()


_THREADS = _ThreadKeeper()


class _Worker(QThread):
    def start(self, *args):
        _THREADS.keep(self)
        super().start(*args)


def _meminfo():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0])
    return info


def _pretty_uptime(seconds):
    # Same wording as procps' `uptime -p`, e.g. "2 days, 1 hour, 5 minutes".
    minutes = int(seconds) // 60
    parts = []
    for name, size in (("week", 7 * 24 * 60), ("day", 24 * 60), ("hour", 60), ("minute", 1)):
        n, minutes = divmod(minutes, size)
        if n or (name == "minute" and not parts):
            parts.append(f"{n} {name}{'' if n == 1 else 's'}")
    return ", ".join(parts)


class StatsWorker(QThread):
    statsReady = Signal("QVariantMap")

    def __init__(self):
        super().__init__()
        self._stop = False
        # Only sample while a page that shows these numbers is open.
        self._wanted = threading.Event()

    def stop(self):
        self._stop = True
        self._wanted.set()

    def set_active(self, active):
        if active:
            self._wanted.set()
        else:
            self._wanted.clear()

    def _cpu_times(self):
        with open("/proc/stat") as f:
            parts = f.readline().split()
        return list(map(int, parts[1:8]))

    def run(self):
        while not self._stop:
            self._wanted.wait()
            if self._stop:
                break
            t1 = self._cpu_times()
            time.sleep(0.2)
            if self._stop:
                break
            t2 = self._cpu_times()
            total1, total2 = sum(t1), sum(t2)
            idle1, idle2 = t1[3], t2[3]
            denom = (total2 - total1) or 1
            cpu_pct = round((1 - (idle2 - idle1) / denom) * 100, 1)

            # Read straight from procfs: the same numbers `free -m` prints
            # (procps-ng 4: used = total - available), without starting three
            # helper processes every two seconds.
            mem_total = mem_used = swap_total = swap_used = 0
            try:
                mem = _meminfo()
                mem_total = mem["MemTotal"] // 1024
                mem_used = (mem["MemTotal"] - mem.get("MemAvailable", mem["MemFree"])) // 1024
                swap_total = mem.get("SwapTotal", 0) // 1024
                swap_used = (mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) // 1024
            except (OSError, KeyError, ValueError):
                pass
            mem_pct = round((mem_used / mem_total) * 100) if mem_total else 0

            gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
            governor = "N/A"
            if Path(gov_path).exists():
                governor = Path(gov_path).read_text().strip()

            try:
                swappiness = int(Path("/proc/sys/vm/swappiness").read_text().strip())
            except Exception:
                swappiness = 0

            try:
                swap_status = "ON" if len(Path("/proc/swaps").read_text().splitlines()) > 1 else "OFF"
            except OSError:
                swap_status = "OFF"

            try:
                uptime = _pretty_uptime(float(Path("/proc/uptime").read_text().split()[0]))
            except (OSError, ValueError, IndexError):
                uptime = "N/A"

            self.statsReady.emit({
                "cpu": cpu_pct,
                "memUsed": mem_used, "memTotal": mem_total, "memPct": mem_pct,
                "swapUsed": swap_used, "swapTotal": swap_total, "swapStatus": swap_status,
                "governor": governor, "swappiness": swappiness, "uptime": uptime,
            })

            for _ in range(9):
                if self._stop or not self._wanted.is_set():
                    break
                time.sleep(0.2)


# pacman's per-package transaction lines, e.g. "upgrading foo..." or
# "(2/5) installing bar" -- seeing one means the system actually changed.
_PKG_CHANGED_RE = re.compile(r"^(?:\(\s*\d+/\d+\)\s*)?(?:upgrading|installing|reinstalling) \S")


REYOS_CHANNEL = "/usr/bin/reyos-channel"
REYOS_ADMIN = "/usr/share/reyos/bin/reyos-admin"
PKEXEC_DISMISSED = (126, 127)  # dialog cancelled (the KDE agent reports 127 "Not authorized")


def _upgrade_cmd():
    # reyos-update-channel installs updates from the chosen channel (and
    # re-syncs when the update itself moved the stable snapshot forward).
    if Path(REYOS_CHANNEL).exists():
        return [REYOS_CHANNEL, "upgrade", "--yes"]
    return ["pacman", "-Syu", "--noconfirm"]


def _update_channel():
    try:
        out = subprocess.run([REYOS_CHANNEL, "status"], capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "channel": "", "snapshot": ""}
    if not out:
        return {"available": False, "channel": "", "snapshot": ""}
    snapshot = out[1].replace("/", "-") if len(out) > 1 else ""
    return {"available": True, "channel": out[0], "snapshot": snapshot}


class PkgWorker(_Worker):
    progress = Signal(str)
    finished_ok = Signal(bool, str)

    def __init__(self, action):
        super().__init__()
        self.action = action
        # Set once pacman reports it upgraded/installed anything, so the page
        # can ask for a restart (running apps, plasmashell and the kernel
        # keep using the old versions until then) only when it matters.
        self.changed = False
        self._log = None

    def _emit(self, line):
        if not self.changed and _PKG_CHANGED_RE.match(line):
            self.changed = True
        if self._log is not None:
            self._log.write(line + "\n")
            self._log.flush()
        self.progress.emit(line)

    def run(self):
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            self._log = PKG_LOG.open("w")
            self._log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {self.action}\n")
        except OSError:
            self._log = None
        try:
            self._run_action()
        finally:
            if self._log is not None:
                self._log.close()

    def _run_action(self):
        try:
            emit = self._emit
            if self.action in ("upgrade", "full", "clean", "reyos", "channel-stable", "channel-rolling") and _is_live_session():
                self.finished_ok.emit(False, "Updates and cleanup are disabled in the live session. Install ReyOS first, then update the installed system.")
                return
            if self.action == "check":
                emit("$ checkupdates")
                rc = _run(["checkupdates"], emit)
                if rc == 0:
                    self.finished_ok.emit(True, "Updates are available.")
                elif rc == 2:
                    self.finished_ok.emit(True, "Your packages are up to date.")
                else:
                    self.finished_ok.emit(False, "Could not check updates. Verify your network connection.")
            elif self.action == "upgrade":
                _wait_for_pacman_lock(emit)
                emit("$ sudo " + " ".join(_upgrade_cmd()))
                rc = _run(["sudo", "-n"] + _upgrade_cmd(), emit)
                if rc == 0:
                    _record_successful_update(emit)
                self.finished_ok.emit(rc == 0, "Updates installed." if rc == 0 else "Update failed.")
            elif self.action == "full":
                _wait_for_pacman_lock(emit)
                emit("[1/3] Syncing + upgrading...")
                rc = _run(["sudo", "-n"] + _upgrade_cmd(), emit)
                if rc != 0:
                    self.finished_ok.emit(False, "Full update failed.")
                    return
                _record_successful_update(emit)
                # The system itself is updated now; the clean-up steps below
                # can fail without undoing that, so name them instead of
                # reporting a plain success.
                failed = []
                emit("[2/3] Removing orphaned packages...")
                orphans = subprocess.run(
                    ["pacman", "-Qtdq"], capture_output=True, text=True
                ).stdout.split()
                if orphans:
                    _wait_for_pacman_lock(emit)
                    if _run(["sudo", "-n", REYOS_ADMIN, "remove-orphans"], emit) != 0:
                        failed.append("removing orphaned packages")
                _wait_for_pacman_lock(emit)
                if _run(["sudo", "-n", REYOS_ADMIN, "clean-cache"], emit) != 0:
                    failed.append("cleaning the package cache")
                emit("[3/3] Flatpak update...")
                if _run(["flatpak", "update", "-y"], emit) != 0:
                    failed.append("updating Flatpak apps")
                if failed:
                    self.finished_ok.emit(True, "System updated, but " + " and ".join(failed) + " failed -- see the log.")
                else:
                    self.finished_ok.emit(True, "Full update complete.")
            elif self.action == "reyos":
                _wait_for_pacman_lock(emit)
                emit("$ sudo pacman -Sy")
                rc = _run(["sudo", "-n", "pacman", "-Sy"], emit)
                if rc != 0:
                    self.finished_ok.emit(False, "Could not sync package databases.")
                    return
                emit("Checking for ReyOS app updates...")
                repo_out = subprocess.run(["pacman", "-Sl", "reyos-local"], capture_output=True, text=True).stdout
                reyos_pkgs = {line.split()[1] for line in repo_out.splitlines() if len(line.split()) >= 2}
                upgradable_out = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True).stdout
                to_upgrade = [line.split()[0] for line in upgradable_out.splitlines() if line.split() and line.split()[0] in reyos_pkgs]

                installed_out = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True).stdout
                installed = set(installed_out.split())
                to_backfill = [p for p in REYOS_DEFAULT_APPS if p in reyos_pkgs and p not in installed]

                to_install = to_upgrade + to_backfill
                if not to_install:
                    self.finished_ok.emit(True, "ReyOS apps are already up to date.")
                    return
                emit("Updating: " + ", ".join(to_install))
                _wait_for_pacman_lock(emit)
                rc = _run(["sudo", "-n", REYOS_ADMIN, "install-reyos"] + to_install, emit)
                self.finished_ok.emit(rc == 0, f"Updated {len(to_install)} ReyOS app(s)." if rc == 0 else "Update failed.")
            elif self.action in ("channel-stable", "channel-rolling"):
                target = self.action.split("-", 1)[1]
                _wait_for_pacman_lock(emit)
                emit(f"$ sudo {REYOS_CHANNEL} {target} --yes")
                rc = _run(["sudo", "-n", REYOS_CHANNEL, target, "--yes"], emit)
                if rc == 0:
                    _record_successful_update(emit)
                label = "Stable" if target == "stable" else "Rolling"
                self.finished_ok.emit(rc == 0, f"Switched to the {label} channel." if rc == 0 else f"Switching to the {label} channel failed.")
            elif self.action == "clean":
                orphans = subprocess.run(
                    ["pacman", "-Qtdq"], capture_output=True, text=True
                ).stdout.split()
                if orphans:
                    emit("Removing: " + " ".join(orphans))
                    _wait_for_pacman_lock(emit)
                    _run(["sudo", "-n", REYOS_ADMIN, "remove-orphans"], emit)
                else:
                    emit("No orphaned packages.")
                _wait_for_pacman_lock(emit)
                _run(["sudo", "-n", REYOS_ADMIN, "clean-cache"], emit)
                self.finished_ok.emit(True, "Cache cleaned.")
        except Exception as e:
            self.finished_ok.emit(False, str(e))


def _die_with_parent():
    # PR_SET_PDEATHSIG: the kernel sends SIGTERM to the child when the
    # Control Center exits for any reason (closed, killed, crashed), so a
    # Bluetooth scan it started never outlives it.
    import ctypes
    import signal
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)


class ActionWorker(_Worker):
    progress = Signal(str)
    finished_ok = Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            ok, message = self.fn(self.progress.emit)
            self.finished_ok.emit(ok, message)
        except Exception as e:
            self.finished_ok.emit(False, str(e))


class ControllerSetupWorker(_Worker):
    """Walks CONTROLLER_STEPS on one pad, then writes the RetroArch profile."""
    step = Signal(int, int, str, str, str, str)
    done = Signal(bool, str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.skip = False
        self.cancelled = False

    def run(self):
        try:
            reader = emulation.ControllerReader(self.path)
        except OSError as e:
            self.done.emit(False, f"Couldn't read the controller ({e.strerror}). Unplug it, plug it back in and try again.")
            return
        name = reader.info["name"]
        brand = emulation.controller_brand(reader.info["vendor"])
        binds = {}
        steps = emulation.CONTROLLER_STEPS
        try:
            for i, (key, title, hint) in enumerate(steps):
                self.skip = False
                title, hint = emulation.step_text(key, title, hint, brand)
                self.step.emit(i, len(steps), key, brand, title, hint)
                bind = reader.wait_bind(lambda: self.skip or self.cancelled)
                if self.cancelled:
                    self.done.emit(False, "Controller setup cancelled -- nothing was changed.")
                    return
                if bind:
                    binds[key] = bind
            if not binds:
                self.done.emit(False, "Every step was skipped, so nothing was saved.")
                return
            emulation.write_profile(reader.info, binds)
            self.done.emit(True, f"{name} is set up. Start + Select opens the emulator menu in a game.")
        except OSError:
            self.done.emit(False, f"{name} was disconnected during setup -- nothing was saved.")
        finally:
            reader.close()


class InfoWorker(_Worker):
    ready = Signal("QVariantMap")

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.ready.emit(self.fn())


class ListWorker(_Worker):
    ready = Signal("QVariantList")

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.ready.emit(self.fn())


def _expand(path):
    return str(Path(path.strip()).expanduser())


class Backend(QObject):
    statsUpdated = Signal("QVariantMap")
    pkgProgress = Signal(str)
    pkgFinished = Signal(bool, str)
    restartRecommended = Signal()
    # Emitted when any background action starts, so Main.qml can show one
    # app-wide "Working..." message instead of every page needing its own.
    actionStarted = Signal()
    orphansListed = Signal("QVariantList")
    actionFinished = Signal(bool, str)
    controllerSetupStep = Signal(int, int, str, str, str, str)
    controllerSetupDone = Signal(bool, str)
    imageSelected = Signal(str)
    biosChanged = Signal()
    pathBrowsed = Signal(str, str)
    networkInfoReady = Signal("QVariantMap")
    diskInfoReady = Signal("QVariantMap")
    aboutInfoReady = Signal("QVariantMap")
    driverStatusReady = Signal("QVariantMap")
    screenSleepReady = Signal("QVariantMap")
    firewallStatusReady = Signal("QVariantMap")
    vpnStatusReady = Signal("QVariantMap")
    vpnConfigSelected = Signal(str)
    securityOverviewReady = Signal("QVariantMap")
    usbGuardStatusReady = Signal("QVariantMap")
    securityUpdatesReady = Signal("QVariantList")
    usersListed = Signal("QVariantList")
    packagesFound = Signal("QVariantList")
    packageInfoReady = Signal(str, str)
    flatpaksListed = Signal("QVariantList")
    servicesFound = Signal("QVariantList")
    autostartListed = Signal("QVariantList")
    startupCandidatesListed = Signal("QVariantList")
    audioInfoReady = Signal("QVariantMap")
    bluetoothStatusReady = Signal("QVariantMap")
    wifiStatusReady = Signal("QVariantMap")
    wireguardListed = Signal("QVariantList")
    datetimeInfoReady = Signal("QVariantMap")
    timezonesListed = Signal("QVariantList")
    keyboardInfoReady = Signal("QVariantMap")
    mouseInfoReady = Signal("QVariantMap")
    customShortcutsListed = Signal("QVariantList")
    pageRequested = Signal(str)
    gamingProgress = Signal(str)
    gamingFinished = Signal(bool, str)
    printersListed = Signal("QVariantList")
    printerDevicesFound = Signal("QVariantList")
    scannersListed = Signal("QVariantList")

    def __init__(self):
        super().__init__()
        self._pkg_worker = None
        self._action_worker = None
        self._picker_worker = None
        self._browse_worker = None
        self._network_worker = None
        self._disk_worker = None
        self._about_worker = None
        self._driver_worker = None
        self._firewall_worker = None
        self._users_worker = None
        self._pkgsearch_worker = None
        self._flatpak_worker = None
        self._services_worker = None
        self._autostart_worker = None
        self._audio_worker = None
        self._bluetooth_worker = None
        self._wifi_worker = None
        self._datetime_worker = None
        self._timezones_worker = None
        self._keyboard_worker = None
        self._mouse_worker = None
        self._gaming_worker = None
        self._controller_worker = None
        self._stats_worker = StatsWorker()
        self._stats_worker.statsReady.connect(self.statsUpdated.emit)
        self._stats_worker.start()

    @Slot(str)
    def openPage(self, page):
        self.pageRequested.emit(page)

    @Slot()
    def openTerminalToolbox(self):
        # Keep the terminal open after the menu exits so its result remains visible.
        subprocess.Popen(["konsole", "--hold", "-e", "reyos-tools"])
        self.actionFinished.emit(True, "Opening ReyOS System Tools...")

    @Slot()
    def openTimeshift(self):
        try:
            subprocess.Popen(["timeshift-launcher"])
            # Timeshift asks for the admin password first and takes a few
            # seconds to appear -- say something so the click isn't silent.
            self.actionFinished.emit(True, "Opening Timeshift -- it will ask for your password.")
        except FileNotFoundError:
            self.actionFinished.emit(False, "Timeshift is not installed yet. Reboot into the next ReyOS ISO build.")

    @Slot(bool)
    def setStatsActive(self, active):
        # Counted, not a flag: when one stats page replaces another, the new
        # page's onCompleted runs before the old page's onDestruction.
        self._stats_users = max(0, getattr(self, "_stats_users", 0) + (1 if active else -1))
        self._stats_worker.set_active(self._stats_users > 0)

    def stopStatsWorker(self):
        self._stats_worker.stop()
        self._stats_worker.wait(1000)

    @Slot(result="QVariantMap")
    def updateChannel(self):
        return _update_channel()

    @Slot(result=bool)
    def pkgActionRunning(self):
        return self._pkg_worker is not None and self._pkg_worker.isRunning()

    @Slot(str)
    def runPkgAction(self, action):
        # The Updates page forgets its own busy state when it is reopened, so
        # refuse here rather than start a second pacman next to the first.
        if self.pkgActionRunning():
            self.pkgFinished.emit(False, "A package operation is still running -- wait for it to finish.")
            return
        worker = PkgWorker(action)
        self._pkg_worker = worker
        worker.progress.connect(self.pkgProgress.emit)
        worker.finished_ok.connect(self.pkgFinished.emit)
        worker.finished_ok.connect(
            lambda ok, _msg: ok and worker.changed and action != "clean" and self.restartRecommended.emit()
        )
        worker.start()

    @Slot()
    def refreshDesktop(self):
        # The panel, launcher and taskbar keep the icons they loaded at login.
        def task(emit):
            _restart_plasmashell_and_wait()
            return True, "Desktop refreshed."
        self._run_action(task)

    @Slot()
    def restartNow(self):
        # Plasma's own logout-and-reboot path: apps get the normal session
        # close (unsaved-work prompts), unlike a bare systemctl reboot, which
        # stays as the fallback if the Plasma D-Bus service isn't there.
        rc = subprocess.run(
            ["qdbus6", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logoutAndReboot"],
            capture_output=True,
        ).returncode
        if rc != 0:
            subprocess.Popen(["systemctl", "reboot"])

    @Slot(result="QVariantList")
    def defaultAppsInfo(self):
        entries = _desktop_entries()
        result = []
        for cat in DEFAULT_APP_CATEGORIES:
            primary_mime = cat["mimetypes"][0]
            current_id = subprocess.run(
                ["xdg-mime", "query", "default", primary_mime], capture_output=True, text=True
            ).stdout.strip()
            options = [e for e in entries.values() if e["mimetypes"] & set(cat["mimetypes"])]
            options.sort(key=lambda e: e["name"].lower())
            current_name = next((o["name"] for o in options if o["desktopId"] == current_id), current_id or "Not set")
            result.append({
                "key": cat["key"],
                "label": cat["label"],
                "mimetypesCsv": ",".join(cat["mimetypes"]),
                "currentId": current_id,
                "currentName": current_name,
                "options": [{"name": o["name"], "desktopId": o["desktopId"]} for o in options],
            })
        return result

    @Slot(str, str)
    def setDefaultApp(self, mimetypes_csv, desktop_id):
        mimetypes = mimetypes_csv.split(",")
        rc = subprocess.run(["xdg-mime", "default", desktop_id] + mimetypes).returncode
        self.actionFinished.emit(rc == 0, f"Default set to {desktop_id}." if rc == 0 else "Could not set default app.")

    @Slot()
    def listOrphans(self):
        orphans = subprocess.run(
            ["pacman", "-Qtdq"], capture_output=True, text=True
        ).stdout.split()
        self.orphansListed.emit(orphans)

    def _run_action(self, fn):
        # Replacing a still-running QThread aborts the whole app.
        running = getattr(self, "_action_worker", None)
        if running is not None and running.isRunning():
            self.actionFinished.emit(False, "Still working on the previous action -- please wait for it to finish.")
            return
        self._action_worker = ActionWorker(fn)
        self._action_worker.finished_ok.connect(self.actionFinished.emit)
        self.actionStarted.emit()
        self._action_worker.start()

    @Slot(result="QVariantMap")
    def gamingStatus(self):
        def installed(pkg):
            return subprocess.run(["pacman", "-Q", pkg], capture_output=True).returncode == 0
        return {"steamInstalled": installed("steam"), "gamemodeInstalled": installed("gamemode")}

    @Slot()
    def installGaming(self):
        if _is_live_session():
            self.gamingFinished.emit(False, "Installing Steam is disabled in the live session -- install ReyOS first.")
            return

        def task(emit):
            # steam and lib32-gamemode are multilib-only packages, and
            # multilib ships disabled in ReyOS's own pacman.conf -- without
            # this the install always fails with "target not found: steam".
            # Reuses reyos-welcome's exact helper/NOPASSWD rule (same
            # precedent: a hand-escaped sudo sed for `[multilib]` risks
            # breaking visudo -c for the whole sudoers file).
            if "#[multilib]" in Path("/etc/pacman.conf").read_text():
                emit("Enabling multilib repository...")
                _run(["sudo", "-n", "/usr/share/reyos/welcome/enable-multilib.sh"], emit)

            emit("$ sudo pacman -Sy --noconfirm")
            rc = _run(["sudo", "-n", "pacman", "-Sy", "--noconfirm"], emit)
            if rc != 0:
                return False, "Could not sync package databases -- check your network connection."

            # One `pacman -S` call per fixed package group, not combined --
            # each call's argv must match one of the fixed, individually
            # listed NOPASSWD sudoers lines Calamares writes for this user
            # (see shellprocess_sudoers_reyos_menu.conf), same reasoning as
            # reyos-welcome's InstallWorker. A combined "steam gamemode
            # lib32-gamemode" argv matches neither fixed line and silently
            # fails with "a password is required" (no controlling terminal
            # to prompt on from a GUI subprocess).
            # Steam needs a 32-bit Vulkan driver. With none installed, pacman picks
            # a provider on its own and has pulled in nvidia-utils on non-NVIDIA
            # machines, so install the one matching this GPU first.
            groups = [["steam"], ["gamemode", "lib32-gamemode", "mangohud", "lib32-mangohud"]]
            vk = subprocess.run(["/usr/share/reyos/bin/reyos-gpu-detect", "--lib32-vulkan"],
                                capture_output=True, text=True).stdout.strip()
            if vk:
                groups.insert(0, [vk])
            for group in groups:
                emit("$ sudo pacman -S --needed --noconfirm " + " ".join(group))
                rc = _run(["sudo", "-n", "pacman", "-S", "--needed", "--noconfirm"] + group, emit)
                if rc != 0:
                    return False, f"Install failed ({' '.join(group)}) -- check your network connection and try again."

            return True, "Steam, GameMode, and MangoHud installed."
        self._gaming_worker = ActionWorker(task)
        self._gaming_worker.progress.connect(self.gamingProgress.emit)
        self._gaming_worker.finished_ok.connect(self.gamingFinished.emit)
        self._gaming_worker.start()

    # ---- Emulation -------------------------------------------------------
    @staticmethod
    def _emu_core_path(system):
        return emulation.core_path(system)

    @staticmethod
    def _emu_prepare_folders():
        emulation.prepare_folders()

    @Slot(result="QVariantList")
    def emulationSystems(self):
        result = []
        for system in EMU_SYSTEMS:
            result.append({
                "id": system["id"], "name": system["name"], "short": system["short"],
                "flatpak": "flatpak" in system, "app": system.get("app", ""),
                "installed": emulation.system_installed(system),
                "games": sum(1 for _ in emulation.scan_games(system)),
            })
        return result

    @Slot("QVariantList")
    def installEmulation(self, system_ids):
        valid = {s["id"] for s in EMU_SYSTEMS}
        ids = [i for i in system_ids if i in valid]
        if not ids:
            self.gamingFinished.emit(False, "Choose at least one system to install.")
            return
        if _is_live_session():
            self.gamingFinished.emit(False, "Installing emulators is disabled in the live session -- install ReyOS first.")
            return

        by_id = {s["id"]: s for s in EMU_SYSTEMS}
        core_ids = [i for i in ids if "flatpak" not in by_id[i]]
        flatpaks = [by_id[i] for i in ids if "flatpak" in by_id[i]]

        def task(emit):
            self._emu_prepare_folders()
            if core_ids:
                emit("Installing RetroArch and emulators for: " + ", ".join(by_id[i]["name"] for i in core_ids))
                emit("(ReyOS will ask for your password.)")
                rc = _run(["pkexec", str(APP_DIR / "reyos-install-emulators.sh"), *core_ids], emit)
                if rc in (126, 127):
                    return False, "Install cancelled -- the password prompt was closed."
                if rc != 0:
                    return False, "Install failed -- check your network connection and try again."
                emulation.link_system_files()
            if flatpaks:
                # Per-user, like ReyOS Welcome: no password, and a fresh
                # account has no --user flathub remote until it's added.
                emit("Downloading " + " and ".join(s["app"] for s in flatpaks) + " from Flathub (this can take a few minutes)...")
                _run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", emulation.FLATHUB_URL], emit)
                rc = _run(["flatpak", "install", "-y", "--user", "--noninteractive", "flathub",
                           *[s["flatpak"] for s in flatpaks]], emit)
                if rc != 0:
                    return False, "Flathub download failed -- check your network connection and try again."
                for s in flatpaks:
                    emulation.prepare_flatpak(s)
            return True, f"Emulation ready. Put your games in {GAMES_DIR / 'ROMs'}/<system>/ and they'll show up here."
        self._gaming_worker = ActionWorker(task)
        self._gaming_worker.progress.connect(self.gamingProgress.emit)
        self._gaming_worker.finished_ok.connect(self.gamingFinished.emit)
        self._gaming_worker.start()

    @Slot(str, str)
    def launchGame(self, system_id, path):
        self.actionFinished.emit(*emulation.launch_game(system_id, path))

    @Slot()
    def openGameLibrary(self):
        subprocess.Popen([str(APP_DIR / "games.py")], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot(str)
    def openGamesFolder(self, system_id):
        self._emu_prepare_folders()
        if system_id == "bios":
            folder = emulation.BIOS_DIR
        else:
            folder = GAMES_DIR / "ROMs" / system_id if system_id else GAMES_DIR / "ROMs"
            folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(folder)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot(str)
    def openEmulatorApp(self, system_id):
        """Opens PCSX2 / Azahar on their own, for their own settings."""
        system = next((s for s in EMU_SYSTEMS if s["id"] == system_id and "flatpak" in s), None)
        if system is None or not emulation.system_installed(system):
            self.actionFinished.emit(False, "That emulator isn't installed yet.")
            return
        emulation.prepare_flatpak(system)
        subprocess.Popen(["flatpak", "run", system["flatpak"]], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.actionFinished.emit(True, f"Opening {system['app']}...")

    @Slot(bool)
    def setEmulationExpanded(self, expanded):
        try:
            emulation.save_settings({"expanded": bool(expanded)})
        except OSError:
            pass

    @Slot(bool)
    def setBiosExpanded(self, expanded):
        try:
            emulation.save_settings({"bios_expanded": bool(expanded)})
        except OSError:
            pass

    @Slot(result="QVariantMap")
    def emulationSettings(self):
        return emulation.load_settings()

    @Slot("QVariantMap")
    def setEmulationSettings(self, settings):
        try:
            emulation.save_settings(dict(settings))
        except OSError as e:
            self.actionFinished.emit(False, f"Couldn't save game settings: {e}")
            return
        self.actionFinished.emit(True, "Game settings saved -- they apply the next time you start a game.")

    @Slot(result="QVariantList")
    def biosReport(self):
        # GameCube listed even without its data files; PS2 is a Flatpak, not a core
        installed = {s["id"] for s in EMU_SYSTEMS
                     if emulation.core_path(s).is_file() or emulation.system_installed(s)}
        return emulation.bios_report(installed)

    @Slot(str, str)
    def biosFixName(self, source, name):
        if emulation.bios_fix_name(source, name):
            self.actionFinished.emit(True, f"Copied {source} to {name}.")
        else:
            self.actionFinished.emit(False, f"Couldn't copy {source} to {name}.")

    @Slot()
    def importBios(self):
        def task(emit):
            result = subprocess.run(
                ["kdialog", "--title", "Import BIOS Files", "--getopenfilename", str(Path.home()),
                 "BIOS files (*.bin *.BIN *.rom *.ROM *.rom0 *.ROM0);;All files (*)",
                 "--multiple", "--separate-output"],
                capture_output=True, text=True,
            )
            paths = [p for p in result.stdout.splitlines() if p.strip()]
            if not paths:  # Cancel
                return True, ""
            imported, messages = emulation.bios_import(paths)
            return imported > 0 or all("already there" in m for m in messages), " ".join(messages)
        self._bios_worker = ActionWorker(task)
        self._bios_worker.finished_ok.connect(self._bios_imported)
        self._bios_worker.start()

    def _bios_imported(self, ok, message):
        if message:
            self.actionFinished.emit(ok, message)
        self.biosChanged.emit()

    @Slot(result="QVariantList")
    def gameControllers(self):
        return emulation.list_controllers()

    @Slot(result=str)
    def savedControllerBrand(self):
        return emulation.saved_brand()

    @Slot(str, result="QVariantList")
    def systemControls(self, brand):
        return emulation.system_controls(brand)

    @Slot(str)
    def startControllerSetup(self, path):
        if self._controller_worker is not None and self._controller_worker.isRunning():
            return
        self._controller_worker = ControllerSetupWorker(path)
        self._controller_worker.step.connect(self.controllerSetupStep.emit)
        self._controller_worker.done.connect(self._controller_setup_done)
        self._controller_worker.start()

    def _controller_setup_done(self, ok, message):
        self.controllerSetupDone.emit(ok, message)
        self.actionFinished.emit(ok, message)

    @Slot()
    def skipControllerStep(self):
        if self._controller_worker is not None:
            self._controller_worker.skip = True

    @Slot()
    def cancelControllerSetup(self):
        if self._controller_worker is not None:
            self._controller_worker.cancelled = True


    # --- Screen & Sleep -----------------------------------------------------
    # Screen lock lives in kscreenlockerrc, screen-off / sleep / lid in
    # powerdevilrc (Plasma 6.3+ layout: [AC|Battery][Display] and
    # [AC|Battery][SuspendAndShutdown]). Read and written with
    # kreadconfig6/kwriteconfig6, the same way the rest of ReyOS edits KDE config.
    # Minutes everywhere in the UI; 0 means "never".
    _POWER_PROFILES = {"ac": "AC", "battery": "Battery"}
    _LID_NOTHING, _LID_SLEEP, _LID_LOCK = 0, 1, 32

    @staticmethod
    def _kread(file, groups, key, default=""):
        cmd = ["kreadconfig6", "--file", file]
        for g in groups:
            cmd += ["--group", g]
        cmd += ["--key", key, "--default", default]
        try:
            return subprocess.check_output(cmd, text=True, timeout=5).strip()
        except Exception:
            return default

    @staticmethod
    def _kwrite(file, groups, key, value):
        cmd = ["kwriteconfig6", "--file", file]
        for g in groups:
            cmd += ["--group", g]
        cmd += ["--key", key, str(value)]
        subprocess.run(cmd, check=True, timeout=5)

    @staticmethod
    def _compute_screen_sleep():
        read = Backend._kread
        lock_on = read("kscreenlockerrc", ["Daemon"], "Autolock", "true") != "false"
        info = {
            "lockMinutes": int(read("kscreenlockerrc", ["Daemon"], "Timeout", "5") or 5) if lock_on else 0,
            "lockOnResume": read("kscreenlockerrc", ["Daemon"], "LockOnResume", "true") != "false",
        }
        for name, group in Backend._POWER_PROFILES.items():
            off_on = read("powerdevilrc", [group, "Display"], "TurnOffDisplayWhenIdle", "true") != "false"
            off_s = int(read("powerdevilrc", [group, "Display"], "TurnOffDisplayIdleTimeoutSec", "600") or 600)
            dim_on = read("powerdevilrc", [group, "Display"], "DimDisplayWhenIdle", "true") != "false"
            dim_s = int(read("powerdevilrc", [group, "Display"], "DimDisplayIdleTimeoutSec", "300") or 300)
            sleep_act = int(read("powerdevilrc", [group, "SuspendAndShutdown"], "AutoSuspendAction", "1") or 0)
            sleep_s = int(read("powerdevilrc", [group, "SuspendAndShutdown"], "AutoSuspendIdleTimeoutSec", "900") or 900)
            lid = int(read("powerdevilrc", [group, "SuspendAndShutdown"], "LidAction", "1") or 1)
            info[name + "ScreenOff"] = round(off_s / 60) if off_on else 0
            info[name + "Dim"] = round(dim_s / 60) if dim_on else 0
            info[name + "Sleep"] = round(sleep_s / 60) if sleep_act == 1 else 0
            info[name + "Lid"] = lid
        info["hasBattery"] = bool(glob.glob("/sys/class/power_supply/BAT*"))
        return info

    @Slot()
    def refreshScreenSleep(self):
        self._screen_sleep_worker = InfoWorker(self._compute_screen_sleep)
        self._screen_sleep_worker.ready.connect(self.screenSleepReady.emit)
        self._screen_sleep_worker.start()

    @Slot("QVariantMap")
    def applyScreenSleep(self, v):
        def task(emit):
            kwrite = Backend._kwrite
            lock = int(v["lockMinutes"])
            kwrite("kscreenlockerrc", ["Daemon"], "Autolock", "true" if lock > 0 else "false")
            if lock > 0:
                kwrite("kscreenlockerrc", ["Daemon"], "Timeout", lock)
            kwrite("kscreenlockerrc", ["Daemon"], "LockOnResume", "true" if v["lockOnResume"] else "false")
            for name, group in Backend._POWER_PROFILES.items():
                off, sleep = int(v[name + "ScreenOff"]), int(v[name + "Sleep"])
                dim = int(v[name + "Dim"])
                kwrite("powerdevilrc", [group, "Display"], "DimDisplayWhenIdle", "true" if dim > 0 else "false")
                if dim > 0:
                    kwrite("powerdevilrc", [group, "Display"], "DimDisplayIdleTimeoutSec", dim * 60)
                kwrite("powerdevilrc", [group, "Display"], "TurnOffDisplayWhenIdle", "true" if off > 0 else "false")
                if off > 0:
                    kwrite("powerdevilrc", [group, "Display"], "TurnOffDisplayIdleTimeoutSec", off * 60)
                kwrite("powerdevilrc", [group, "SuspendAndShutdown"], "AutoSuspendAction", 1 if sleep > 0 else 0)
                if sleep > 0:
                    kwrite("powerdevilrc", [group, "SuspendAndShutdown"], "AutoSuspendIdleTimeoutSec", sleep * 60)
                kwrite("powerdevilrc", [group, "SuspendAndShutdown"], "LidAction", int(v[name + "Lid"]))
            # Ask the running power daemon to re-read powerdevilrc so the change
            # applies now, not at the next login. Best effort: the screen locker
            # watches its own file, and an older Plasma just applies it later.
            for tool in ("qdbus6", "qdbus"):
                if shutil.which(tool):
                    subprocess.run([tool, "org.kde.Solid.PowerManagement", "/org/kde/Solid/PowerManagement",
                                    "org.kde.Solid.PowerManagement.reparseConfiguration"],
                                   capture_output=True, timeout=5)
                    break
            return True, "Screen and sleep settings saved."
        self._run_action(task)

    @Slot(str)
    def setGovernor(self, gov):
        def task(emit):
            paths = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
            if not paths:
                return False, "No cpufreq scaling available on this system (common in VMs)."
            if gov not in Backend._available_governors():
                return False, f"This CPU doesn't offer the {gov} governor."
            if not Backend._write_governor(paths, gov):
                return False, "Couldn't change the governor (permission denied)."
            return True, f"Governor set to: {gov}"
        self._run_action(task)

    @staticmethod
    def _available_governors():
        try:
            return Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors").read_text().split()
        except OSError:
            return []

    @staticmethod
    def _write_governor(paths, gov):
        return subprocess.run(["sudo", "-n", REYOS_ADMIN, "governor", gov], capture_output=True).returncode == 0

    @staticmethod
    def _apply_swappiness(value):
        # `sysctl -w` only touches live kernel state -- the sysctl.d drop-in
        # makes it survive a reboot instead of silently reverting.
        return subprocess.run(["sudo", "-n", REYOS_ADMIN, "swappiness", str(value)],
                              capture_output=True).returncode == 0

    @Slot()
    def performanceMode(self):
        def task(emit):
            paths = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
            note = " (governor skipped -- no cpufreq scaling on this system)"
            if paths:
                if "performance" not in Backend._available_governors():
                    note = " (this CPU has no performance governor)"
                elif Backend._write_governor(paths, "performance"):
                    note = ""
                else:
                    return False, "Couldn't change the governor (permission denied)."
            if not Backend._apply_swappiness(10):
                return False, "Couldn't change swappiness (permission denied)."
            return True, f"Performance mode applied.{note} Swappiness -> 10 (persists across reboots)."
        self._run_action(task)

    @Slot(int)
    def setSwappiness(self, value):
        def task(emit):
            v = max(0, min(200, int(value)))
            if not Backend._apply_swappiness(v):
                return False, "Couldn't change swappiness (permission denied)."
            return True, f"Swappiness set to: {v} (persists across reboots)"
        self._run_action(task)

    @staticmethod
    def _swap_unit_for_device(device):
        try:
            return subprocess.check_output(
                ["systemd-escape", "--path", "--suffix=swap", device], text=True,
            ).strip()
        except Exception:
            return ""

    @staticmethod
    def _masked_swap_units():
        try:
            out = subprocess.check_output(
                ["systemctl", "list-unit-files", "--type=swap", "--state=masked", "--no-legend", "--plain"],
                text=True,
            )
        except Exception:
            return []
        return [line.split()[0] for line in out.splitlines() if line.split()]

    @staticmethod
    def _active_swaps():
        try:
            return [l.split()[0] for l in Path("/proc/swaps").read_text().splitlines()[1:] if l.split()]
        except OSError:
            return []

    @Slot()
    def toggleSwap(self):
        def task(emit):
            swap_on = Backend._active_swaps()
            if swap_on:
                # swapoff -a only affects the running session -- systemd
                # regenerates the swap unit (fstab or zram-generator) on every
                # boot, so mask it (an /etc/systemd/system mask always wins
                # over that generated unit) rather than editing fstab directly.
                units = [Backend._swap_unit_for_device(d) for d in swap_on]
                subprocess.run(["sudo", "-n", REYOS_ADMIN, "swap", "off"] + [u for u in units if u],
                               capture_output=True)
                if Backend._active_swaps():
                    return False, "Couldn't turn swap off."
                return True, "Swap disabled (stays off after reboot)."
            units = Backend._masked_swap_units()
            # zram swap (ReyOS's default) has no fstab line, so swapon -a
            # alone never brings it back: the helper unmasks and starts its unit too.
            subprocess.run(["sudo", "-n", REYOS_ADMIN, "swap", "on"] + list(units), capture_output=True)
            if not Backend._active_swaps():
                return False, "Couldn't turn swap on -- no swap device came up."
            return True, "Swap enabled."
        self._run_action(task)

    # plasma-apply-lookandfeel's KPackage lookup silently no-ops on our own
    # custom look-and-feel packages -- confirmed via kreadconfig6: rc=0, zero
    # stdout even under full Qt debug logging, no config change, even after
    # kbuildsycoca6 and a plasmashell restart. Works fine for stock org.kde.*
    # packages, so this only affects our own themes. Apply their constituent
    # pieces (colorscheme + icon theme + the bookkeeping key) directly instead.
    # Fourth element: whether KWin's blur effect should stay enabled under
    # this look-and-feel. Both entries keep the same branded (dark) wallpaper
    # -- no light-toned wallpaper art exists yet -- so under the Light scheme,
    # popup menus blur-reveal that dark wallpaper behind them while Breeze's
    # popup style still computes icon/text colors assuming a light
    # background. Confirmed live: this specifically breaks palette-tinted
    # icons like the desktop context menu's "Create New"/"Icons" entries
    # (washed out to near-invisible) while full-color icons stay fine,
    # exactly matching the reported bug -- and disabling blur entirely
    # while colors/wallpaper were otherwise unchanged fixed it immediately.
    # Dark keeps blur on since a dark wallpaper behind a dark-styled popup
    # doesn't have the same mismatch.
    # The color scheme itself is no longer fixed per entry -- see
    # _scheme_for(): it follows whichever Look is active. Dark uses the
    # ReyOS icon theme (what reyos-apply-branding.sh seeds on first login,
    # and what applyLook() recolors); it used to be breeze-dark here, so a
    # Light->Dark round trip silently dropped the branded icons.
    _REYOS_LOOKANDFEEL = {
        "org.reyos.desktop": (False, "ReyOS", None, True),
        LIGHT_LOOKANDFEEL: (True, "breeze", None, False),
    }

    @Slot(result=str)
    def activeLookAndFeel(self) -> str:
        try:
            current = subprocess.check_output(
                ["kreadconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", "LookAndFeelPackage"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
            return current if current in self._REYOS_LOOKANDFEEL else "org.reyos.desktop"
        except (OSError, subprocess.CalledProcessError):
            return "org.reyos.desktop"

    @Slot(str)
    def applyLookAndFeel(self, package_id):
        def task(emit):
            if package_id in self._REYOS_LOOKANDFEEL:
                light, icons, wallpaper, blur_enabled = self._REYOS_LOOKANDFEEL[package_id]
                colorscheme = _scheme_for(_current_look_id(), light)
                rc = subprocess.run(["plasma-apply-colorscheme", colorscheme]).returncode
                if wallpaper:
                    subprocess.run(["plasma-apply-wallpaperimage", wallpaper])
                subprocess.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "Icons", "--key", "Theme", icons])
                subprocess.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", "LookAndFeelPackage", package_id])
                subprocess.run(["kwriteconfig6", "--file", "kwinrc", "--group", "Plugins", "--key", "blurEnabled",
                                 "true" if blur_enabled else "false"])
                # `qdbus6 .../KWin reconfigure` alone re-reads config for
                # already-loaded effects but doesn't reliably (re)load one
                # that's currently unloaded -- confirmed live going
                # false->true left blur config'd on but still unloaded.
                # loadEffect/unloadEffect on the live /Effects interface
                # act immediately and correctly either direction; the
                # config write above is still needed so the choice sticks
                # across the next full KWin restart/login.
                subprocess.run([
                    "qdbus6", "org.kde.KWin", "/Effects",
                    "org.kde.kwin.Effects.loadEffect" if blur_enabled else "org.kde.kwin.Effects.unloadEffect",
                    "blur",
                ], capture_output=True)
                # kwriteconfig6 alone only changes the file on disk -- it
                # doesn't tell any already-running app (including this one)
                # to re-resolve icons, so items that had already been drawn
                # under the old theme went blank instead of re-tinting
                # (reported live: switching to ReyOS Light left some sidebar
                # icons white). QIcon.setThemeName() is the same call Qt's
                # own platform theme integration makes when it *does* pick up
                # a live change; forcing it here fixes lookups from this
                # point on, though icons already painted before the switch
                # may still need the page/app reopened to fully repaint.
                QIcon.setThemeName(icons)
                _write_panel_theme()
                # Light/Dark never re-ran the Look's recolor, so anything a
                # package update had reset to copper (window border, app
                # icons) stayed copper -- reported live.
                _recolor_look_assets(_current_look_id())
                # The panel/taskbar/systray icons are drawn by plasmashell,
                # a separate already-running process -- confirmed live that
                # neither the kwriteconfig6 write nor a KGlobalSettings
                # notifyChange D-Bus broadcast makes it re-resolve them (they
                # stayed on the old theme's icons, unreadable against the
                # new panel color). A full plasmashell restart is the only
                # thing that actually refreshed them in testing; brief
                # flicker is an acceptable tradeoff for icons that are
                # otherwise invisible against the new background.
                _restart_plasmashell_and_wait()
                return rc == 0, ("Look and feel applied; matching wallpaper set when available." if rc == 0 else "Failed to apply color scheme.")
            rc = subprocess.run(["plasma-apply-lookandfeel", "--apply", package_id]).returncode
            return rc == 0, ("Look and feel applied." if rc == 0 else "Failed to apply look and feel.")
        worker = ActionWorker(task)
        worker.finished_ok.connect(self.actionFinished.emit)
        # A running app's own Qt platform style/window chrome doesn't
        # hot-reload on a live color-scheme switch (confirmed: sidebar
        # icons refresh fine via QIcon.setThemeName() above, but the
        # window's own chrome stays on the old style until reopened) --
        # relaunching this app is the same fix already applied to
        # plasmashell above for the same class of "already-running
        # process doesn't repaint" problem. REYOS_CC_INITIAL_PAGE brings
        # the new window back to this same Appearance page.
        worker.finished_ok.connect(lambda ok, _msg: ok and self._relaunch_self())
        self._lookandfeel_worker = worker
        self.actionStarted.emit()
        worker.start()

    def _relaunch_self(self, page="AppearancePage.qml"):
        env = dict(os.environ)
        env["REYOS_CC_INITIAL_PAGE"] = page
        subprocess.Popen(
            [str(APP_DIR / "main.py")],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        QTimer.singleShot(300, QGuiApplication.quit)

    @Slot(result="QVariantList")
    def looksInfo(self):
        current = _current_look_id()
        light = _is_light_mode()
        light_base = configparser.ConfigParser(strict=False, interpolation=None)
        light and light_base.read(_LIGHT_BASE_SCHEME)

        looks = []
        if not LOOKS_DIR.is_dir():
            return looks
        for look_dir in sorted(LOOKS_DIR.iterdir()):
            colors_file = look_dir / "colors.colors"
            if not look_dir.is_dir() or not colors_file.is_file():
                continue
            parser = configparser.ConfigParser(strict=False)
            parser.read(colors_file)
            # Preview swatch shows the surfaces this Look will actually get
            # in the current Light/Dark mode, not always its dark scheme.
            surfaces = light_base if light_base.has_section("Colors:Window") else parser
            looks.append({
                "id": look_dir.name,
                "name": parser.get("General", "Name", fallback=look_dir.name.capitalize()),
                "background": "#" + "".join(f"{int(c):02x}" for c in surfaces.get("Colors:Window", "BackgroundNormal", fallback="20,20,20").split(",")),
                "accent": "#" + "".join(f"{int(c):02x}" for c in parser.get("Colors:Button", "DecorationFocus", fallback="100,100,100").split(",")),
                "foreground": "#" + "".join(f"{int(c):02x}" for c in surfaces.get("Colors:Window", "ForegroundNormal", fallback="230,230,230").split(",")),
                "active": look_dir.name == current,
            })
        return looks

    @Slot(str)
    def applyLook(self, look_id):
        def task(emit):
            look_dir = LOOKS_DIR / look_id
            colors_file = look_dir / "colors.colors"
            if not colors_file.is_file():
                return False, f"Unknown look: {look_id}"

            # plasma-apply-colorscheme only resolves a registered scheme name
            # (looked up under /usr/share/color-schemes or the user's local
            # copy) -- a full path is accepted but silently reduced to its
            # last path component, which fails to resolve. Every look's
            # ColorScheme id is shipped there too for exactly this reason.
            parser = configparser.ConfigParser(strict=False)
            parser.read(colors_file)
            if not parser.get("General", "ColorScheme", fallback=None):
                return False, f"Look '{look_id}' has no ColorScheme id."
            # Stay in whichever Light/Dark mode is active -- applying the
            # Look's own (always dark) scheme here is what used to flip a
            # Light desktop back to dark panels.
            _kwrite("kdeglobals", "ReyOS", "Look", look_id)
            rc = subprocess.run(["plasma-apply-colorscheme", _scheme_for(look_id, _is_light_mode())]).returncode

            # Per-Look mouse pointer (reyos-looks ships a prebuilt XCursor
            # theme per Look, ReyOS-Copper/-Crimson/-etc -- see assets/cursor/
            # build-cursors.sh; everything but the pointer's own accent rim
            # inherits from breeze_cursors, so this is the one "compact"
            # cursor asset, not a full cursor-set redesign). kcminputrc is a
            # per-user file (unlike the icons/decoration patches below), so
            # this needs no /tmp staging or sudo helper -- same reasoning as
            # plasma-apply-colorscheme/-wallpaperimage above.
            cursor_theme = f"ReyOS-{look_id.capitalize()}"
            if Path(f"/usr/share/icons/{cursor_theme}").is_dir():
                subprocess.run(["plasma-apply-cursortheme", cursor_theme], capture_output=True)

            # Accent-baked icons/window border/browser/terminal files.
            _recolor_look_assets(look_id)

            wallpaper_dir = look_dir / "wallpaper"
            if wallpaper_dir.is_dir():
                subprocess.run([
                    "qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript",
                    'var d = desktops();'
                    'for (i = 0; i < d.length; i++) {'
                    '    d[i].wallpaperPlugin = "org.kde.slideshow";'
                    '    d[i].currentConfigGroup = ["Wallpaper", "org.kde.slideshow", "General"];'
                    f'    d[i].writeConfig("SlidePaths", ["{wallpaper_dir}/"]);'
                    '    d[i].writeConfig("SlideInterval", 1800);'
                    '}'
                ], capture_output=True)

            # Every Look shares the same ReyOS keybinding scheme (SUPER-based
            # workspace/window shortcuts) -- only the palette/wallpaper differ
            # per look, so this file lives at LOOKS_DIR root, not per-look.
            shortcuts_file = LOOKS_DIR / "shortcuts.conf"
            if shortcuts_file.is_file():
                for line in shortcuts_file.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key_part, value = line.split("=", 1)
                    component, _, action = key_part.partition(".")
                    subprocess.run(["kwriteconfig6", "--file", "kglobalshortcutsrc",
                                     "--group", component, "--key", action, value])
                # Reloads kwin's own component only -- confirmed the same way
                # apply_virtual_desktops() in reyos-apply-branding.sh notes
                # config-file re-reads behave inconsistently for KWin, but this
                # specific call is KWin's documented way to re-read
                # kglobalshortcutsrc for its own global shortcuts.
                subprocess.run(["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"], capture_output=True)

            # Same lesson as applyLookAndFeel() above: plasmashell doesn't
            # repaint panel/systray icons on its own just because kdeglobals
            # changed underneath it -- a full restart is the only thing that
            # reliably refreshed them in testing.
            _write_panel_theme()
            _restart_plasmashell_and_wait()
            return rc == 0, (f"{look_id.capitalize()} applied." if rc == 0 else "Failed to apply color scheme.")

        worker = ActionWorker(task)
        worker.finished_ok.connect(self.actionFinished.emit)
        # Same reasoning as applyLookAndFeel()'s relaunch: this window's own
        # chrome doesn't hot-reload on a live color-scheme switch.
        worker.finished_ok.connect(lambda ok, _msg: ok and self._relaunch_self("LooksPage.qml"))
        self._looks_worker = worker
        self.actionStarted.emit()
        worker.start()

    @Slot()
    def pickWallpaperImage(self):
        def task(emit):
            result = subprocess.run(
                ["kdialog", "--title", "Choose Wallpaper Image", "--getopenfilename",
                 str(Path.home() / "Pictures"), "Images (*.png *.jpg *.jpeg *.bmp)"],
                capture_output=True, text=True,
            )
            # kdialog exits non-zero on Cancel -- that's a normal outcome here,
            # not a failure, so always report True with whatever (possibly
            # empty) path it returned rather than routing through actionFinished.
            return True, result.stdout.strip()
        self._picker_worker = ActionWorker(task)
        self._picker_worker.finished_ok.connect(lambda _ok, path: self.imageSelected.emit(path))
        self._picker_worker.start()

    @Slot(str, bool)
    def browsePath(self, target, for_folder):
        def task(emit):
            if for_folder:
                cmd = ["kdialog", "--title", "Choose Folder", "--getexistingdirectory", str(Path.home())]
            else:
                cmd = ["kdialog", "--title", "Choose File", "--getopenfilename", str(Path.home())]
            result = subprocess.run(cmd, capture_output=True, text=True)
            # Same as pickWallpaperImage: Cancel is a normal outcome (non-zero
            # exit, empty stdout), not a failure -- always report True and let
            # the QML side just ignore an empty path.
            return True, result.stdout.strip()
        self._browse_worker = ActionWorker(task)
        self._browse_worker.finished_ok.connect(lambda _ok, path: self.pathBrowsed.emit(target, path))
        self._browse_worker.start()

    @Slot()
    def resetWallpaper(self):
        def task(emit):
            rc = subprocess.run(
                ["plasma-apply-wallpaperimage", "/usr/share/backgrounds/reyos-wallpaper.jpg"]
            ).returncode
            return rc == 0, ("Wallpaper reset to ReyOS default." if rc == 0 else "Failed to set wallpaper.")
        self._run_action(task)

    @Slot(str)
    def applyWallpaper(self, path):
        def task(emit):
            image = _expand(path)
            if not Path(image).is_file():
                return False, f"File not found: {image}"
            rc = subprocess.run(["plasma-apply-wallpaperimage", image]).returncode
            return rc == 0, ("Wallpaper applied." if rc == 0 else "Failed to set wallpaper — is it a valid image?")
        self._run_action(task)

    @Slot(result=int)
    def panelOpacity(self):
        return _panel_opacity()

    @Slot(int)
    def applyPanelOpacity(self, percent):
        def task(emit):
            _kwrite("kdeglobals", "ReyOS", "PanelOpacity", max(10, min(100, int(percent))))
            # Only the Translucent opacity mode draws widgets/panel-background
            # (the one carrying the slider's value); Adaptive swaps to the
            # opaque solid/ variant whenever a window is maximized. Written
            # straight to the config file for the same reason
            # reyos-apply-branding.sh's apply_panel_opacity() does: setting
            # opacityMode through the scripting API never persists.
            appletsrc = Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
            if appletsrc.is_file():
                containment = None
                for line in appletsrc.read_text().splitlines():
                    m = re.fullmatch(r"\[Containments\]\[(\d+)\]", line.strip())
                    if m:
                        containment = m.group(1)
                    elif containment and line.strip() == "plugin=org.kde.panel":
                        subprocess.run(["kwriteconfig6", "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                                        "--group", "Containments", "--group", containment,
                                        "--group", "General", "--key", "opacityMode", "Translucent"])
                        containment = None
            _write_panel_theme()
            _restart_plasmashell_and_wait()
            return True, f"Panel transparency set to {100 - int(percent)}%."
        self._run_action(task)

    @Slot()
    def unlockPanelEditing(self):
        # Same immutability write reyos-apply-branding.sh's unlock_panel_layout()
        # does when a user opts in via Welcome's first-run toggle -- exposed
        # here too since that toggle only ever gets a first-run chance, with
        # no way back for someone who skipped it then and wants panel editing
        # unlocked later.
        #
        # reyos-edit-mode-guard.service polls PlasmaShell's editMode and forces
        # it back off every 0.3s regardless of immutability, so unlocking
        # immutability alone still leaves Plasma's Edit Mode toggle non-functional
        # -- the guard must be stopped too whenever editing is unlocked.
        def task(emit):
            script = "var e=panels(); for (var p=0; p<e.length; p++) { e[p].immutability=1; }"
            rc = subprocess.run(
                ["qdbus6", "org.kde.plasmashell", "/PlasmaShell",
                 "org.kde.PlasmaShell.evaluateScript", script]
            ).returncode
            subprocess.run(["systemctl", "--user", "disable", "--now", "reyos-edit-mode-guard.service"])
            return rc == 0, ("Panel editing unlocked." if rc == 0 else "Failed to unlock panels.")
        self._run_action(task)

    @Slot()
    def lockPanelEditing(self):
        def task(emit):
            script = "var e=panels(); for (var p=0; p<e.length; p++) { e[p].immutability=3; }"
            rc = subprocess.run(
                ["qdbus6", "org.kde.plasmashell", "/PlasmaShell",
                 "org.kde.PlasmaShell.evaluateScript", script]
            ).returncode
            subprocess.run(["systemctl", "--user", "enable", "--now", "reyos-edit-mode-guard.service"])
            return rc == 0, ("Panel layout locked." if rc == 0 else "Failed to lock panels.")
        self._run_action(task)

    @staticmethod
    def _compute_network_info():
        addresses = []
        try:
            out = subprocess.check_output(["ip", "-4", "addr"], text=True)
            iface = ""
            for line in out.splitlines():
                line = line.strip()
                if line and line[0].isdigit() and ":" in line:
                    iface = line.split(":")[1].strip()
                elif line.startswith("inet "):
                    addr = line.split()[1]
                    addresses.append({"iface": iface, "address": addr})
        except Exception:
            pass

        gateway = ""
        try:
            out = subprocess.check_output(["ip", "route"], text=True)
            for line in out.splitlines():
                if line.startswith("default"):
                    gateway = line
                    break
        except Exception:
            pass

        ports = []
        try:
            out = subprocess.check_output(["ss", "-tuln"], text=True)
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5 and "LISTEN" in line:
                    ports.append({"proto": parts[0], "address": parts[4]})
        except Exception:
            pass

        return {"addresses": addresses, "gateway": gateway, "ports": ports}

    @Slot()
    def refreshNetworkInfo(self):
        # ip/ss calls are cheap, but this still went through a worker thread
        # like refreshDiskInfo below, rather than a plain @Slot(result=...)
        # returning straight to QML -- any synchronous slot blocks the whole
        # GUI thread for its duration, and consistency here is cheap insurance
        # against this page ever growing a slower lookup later.
        self._network_worker = InfoWorker(self._compute_network_info)
        self._network_worker.ready.connect(self.networkInfoReady.emit)
        self._network_worker.start()

    @staticmethod
    def _compute_about_info():
        os_name = "Unknown"
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    os_name = line.split("=", 1)[1].strip().strip('"')
                    break
        except Exception:
            pass

        try:
            kernel = subprocess.check_output(["uname", "-r"], text=True).strip()
        except Exception:
            kernel = "Unknown"

        try:
            arch = subprocess.check_output(["uname", "-m"], text=True).strip()
        except Exception:
            arch = "Unknown"

        try:
            hostname = Path("/etc/hostname").read_text().strip()
        except Exception:
            hostname = "Unknown"

        cpu_model = "Unknown"
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass

        # lspci's own device-name string is already the friendliest thing
        # available without a GPU-specific tool (nvidia-smi/etc. may not be
        # installed) -- pciutils is a small, standard dependency worth
        # adding just for this.
        gpu_model = "Unknown"
        try:
            out = subprocess.check_output(["lspci"], text=True)
            for line in out.splitlines():
                if "VGA compatible controller" in line or "3D controller" in line:
                    gpu_model = line.split(": ", 1)[1].strip() if ": " in line else line.strip()
                    break
        except Exception:
            pass

        return {
            "osName": os_name, "kernel": kernel, "arch": arch,
            "hostname": hostname, "cpuModel": cpu_model, "gpuModel": gpu_model,
        }

    @Slot()
    def refreshAboutInfo(self):
        self._about_worker = InfoWorker(self._compute_about_info)
        self._about_worker.ready.connect(self.aboutInfoReady.emit)
        self._about_worker.start()

    # --- Drivers ---------------------------------------------------------
    # First real version of the planned "driver manager" functionality
    # (see docs/whats-next.md) -- lives as a Control Center page rather
    # than a standalone package, same call the Backup page already made.

    @staticmethod
    def _compute_driver_status():
        # Vendor comes from the PCI vendor ID, never from the marketing name
        # ("Intel Corporation" contains "ati" and used to be labelled AMD).
        # Same rule as /usr/share/reyos/bin/reyos-gpu-detect, which the
        # installer uses: NVIDIA's open kernel module needs a GPU System
        # Processor, present from Turing (device ID 0x1e00) onwards.
        vendors = {"8086": "intel", "1002": "amd", "10de": "nvidia"}
        gpus = []
        try:
            out = subprocess.check_output(["lspci", "-nnk"], text=True)
        except Exception:
            out = ""

        current = None
        for line in out.splitlines():
            if line and not line[0].isspace():
                if current:
                    gpus.append(current)
                    current = None
                if "VGA compatible controller" in line or "3D controller" in line:
                    desc = line.split(": ", 1)[1].strip() if ": " in line else line.strip()
                    ids = re.search(r"\[([0-9a-f]{4}):([0-9a-f]{4})\]", desc)
                    vendor_id, device_id = (ids.group(1), ids.group(2)) if ids else ("", "")
                    model = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]", "", desc)
                    current = {
                        "model": model,
                        "vendor": vendors.get(vendor_id, "other"),
                        "driver": "",
                        "nvidiaOpenSupported": bool(ids) and vendor_id == "10de" and int(device_id, 16) >= 0x1E00,
                    }
            elif current is not None:
                stripped = line.strip()
                if stripped.startswith("Kernel driver in use:"):
                    current["driver"] = stripped.split(":", 1)[1].strip()
        if current:
            gpus.append(current)

        # Offer NVIDIA's driver only to a card that can run it and that is
        # still on nouveau (or nothing). Maxwell/Pascal/older cards are best
        # served by nouveau, so they get no button at all.
        needs_nvidia = any(
            g["vendor"] == "nvidia" and g["nvidiaOpenSupported"] and g["driver"] in ("nouveau", "")
            for g in gpus
        )
        return {"gpus": gpus, "needsNvidiaDriver": needs_nvidia}

    @Slot()
    def refreshDriverStatus(self):
        self._driver_worker = InfoWorker(self._compute_driver_status)
        self._driver_worker.ready.connect(self.driverStatusReady.emit)
        self._driver_worker.start()

    @Slot()
    def installNvidiaDrivers(self):
        def task(emit):
            # nvidia-open-dkms rebuilds the module against whatever kernel is
            # currently installed automatically on every kernel update --
            # more maintenance-free than the plain `nvidia` package
            # (which is tied to one specific kernel package/version), and
            # ReyOS runs the standard `linux` kernel this ships against.
            if not any(g["nvidiaOpenSupported"] for g in self._compute_driver_status()["gpus"]):
                return False, "This NVIDIA card is not supported by the current proprietary driver. Keep the open-source nouveau driver."
            result = subprocess.run(
                ["sudo", "-n", "pacman", "-S", "--noconfirm", "--needed", "nvidia-open-dkms", "nvidia-utils"],
                capture_output=True, text=True,
            )
            ok = result.returncode == 0
            if ok:
                return True, "NVIDIA drivers installed. Reboot for them to take effect."
            return False, (result.stderr.strip() or result.stdout.strip() or "Failed to install NVIDIA drivers.")
        self._run_action(task)

    @staticmethod
    def _compute_disk_info():
        filesystems = []
        try:
            out = subprocess.check_output(
                # devtmpfs (source "dev" on Arch) and efivarfs aren't disks the
                # user stores anything on -- they used to show up as rows here.
                ["df", "-h", "-x", "tmpfs", "-x", "devtmpfs", "-x", "efivarfs",
                 "--output=source,size,used,avail,pcent,target"], text=True
            )
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 6:
                    continue
                src, size, used, avail, pct, mnt = parts[0], parts[1], parts[2], parts[3], parts[4], " ".join(parts[5:])
                if src in ("tmpfs", "udev", "none"):
                    continue
                filesystems.append({"mount": mnt, "size": size, "used": used, "avail": avail, "pct": pct})
        except Exception:
            pass

        largest = []
        try:
            home = str(Path.home())
            # Permission-denied on any one subdirectory (e.g. a root-owned
            # build artifact) makes du exit non-zero -- check_output would
            # discard the partial stdout for every *other* entry along with
            # it, so use run() and read stdout regardless of the exit code.
            result = subprocess.run(
                ["du", "-sh", "--exclude=node_modules", "--exclude=.git", "--exclude=.cache"]
                + glob.glob(home + "/*"),
                capture_output=True, text=True,
            )
            rows = [l.split("\t") for l in result.stdout.splitlines() if "\t" in l]
            # du -h suffixes (K/M/G/T) sort wrong as plain strings ("8.0K" >
            # "3.2G" lexically) -- convert to bytes for a true largest-first order.
            suffix_mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
            def size_to_bytes(sz):
                sz = sz.strip()
                if sz and sz[-1] in suffix_mult:
                    try:
                        return float(sz[:-1]) * suffix_mult[sz[-1]]
                    except ValueError:
                        return 0
                try:
                    return float(sz)
                except ValueError:
                    return 0
            rows.sort(key=lambda r: size_to_bytes(r[0]), reverse=True)
            for sz, path in rows[:15]:
                largest.append({"itemSize": sz, "itemPath": path})
        except Exception:
            pass

        return {"filesystems": filesystems, "largest": largest}

    @Slot()
    def refreshDiskInfo(self):
        # du -sh across all of $HOME can take a real while (a large game/ROM
        # library, a big Downloads folder, etc.) -- this used to be a plain
        # @Slot(result=...) called straight from QML, which runs on and
        # blocks the GUI thread for the whole scan. Moved onto the same
        # background-worker pattern every other slow/privileged action here
        # already uses.
        self._disk_worker = InfoWorker(self._compute_disk_info)
        self._disk_worker.ready.connect(self.diskInfoReady.emit)
        self._disk_worker.start()

    @Slot(str, str)
    def fixFolderPermissions(self, path, mode):
        def task(emit):
            folder = _expand(path)
            if not Path(folder).exists():
                return False, f"Path does not exist: {folder}"
            # chown needs root, and is deliberately excluded from the
            # Calamares-installed NOPASSWD sudoers rule (a passwordless
            # NOPASSWD chown would be a real local-escalation hole) -- so this
            # goes through polkit/pkexec for a real, per-call admin password
            # prompt instead of plain sudo (which has no tty to prompt on when
            # launched from the app grid). The helper script does the actual
            # chown+chmod and re-validates the path itself.
            helper = str(APP_DIR / "reyos-fix-permissions.sh")
            result = subprocess.run(
                ["pkexec", helper, folder, mode], capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, "Done: " + folder
            if result.returncode in (126, 127):
                return False, "Authentication cancelled."
            return False, (result.stderr.strip() or "Permission fix failed.")
        self._run_action(task)

    @Slot(str, bool)
    def createPath(self, path, is_directory):
        def task(emit):
            target = _expand(path)
            if Path(target).exists():
                return False, f"Already exists: {target}"
            try:
                if is_directory:
                    Path(target).mkdir(parents=True)
                else:
                    Path(target).parent.mkdir(parents=True, exist_ok=True)
                    Path(target).touch()
                return True, "Created: " + target
            except OSError as e:
                return False, str(e)
        self._run_action(task)

    @Slot(str)
    def makeExecutable(self, path):
        def task(emit):
            f = _expand(path)
            if not Path(f).is_file():
                return False, f"File not found: {f}"
            rc = subprocess.run(["chmod", "+x", f]).returncode
            return rc == 0, ("Done. Run it with: ./" + Path(f).name if rc == 0 else "chmod failed.")
        self._run_action(task)

    # --- Package search / remove (Updates page) ---------------------------

    @staticmethod
    def _compute_package_search(query):
        query = query.strip().lower()
        if not query:
            return []
        try:
            out = subprocess.check_output(["pacman", "-Qq"], text=True)
        except Exception:
            return []
        names = sorted(n for n in out.splitlines() if query in n.lower())[:60]
        results = []
        for name in names:
            version = ""
            try:
                line = subprocess.check_output(["pacman", "-Q", name], text=True).strip()
                version = line.split(" ", 1)[1] if " " in line else ""
            except Exception:
                pass
            results.append({"name": name, "version": version})
        return results

    @Slot(str)
    def searchPackages(self, query):
        self._pkgsearch_worker = ListWorker(lambda: self._compute_package_search(query))
        self._pkgsearch_worker.ready.connect(self.packagesFound.emit)
        self._pkgsearch_worker.start()

    @Slot(str)
    def getPackageInfo(self, pkgname):
        def task():
            # -Qi is entirely local (the installed package's own recorded
            # metadata) -- no sudo, no network, safe for any installed name.
            try:
                info = subprocess.check_output(["pacman", "-Qi", "--", pkgname], text=True)
            except Exception:
                info = "Could not read package info."
            return {"name": pkgname, "info": info}
        self._pkginfo_worker = InfoWorker(task)
        self._pkginfo_worker.ready.connect(lambda r: self.packageInfoReady.emit(r["name"], r["info"]))
        self._pkginfo_worker.start()

    @Slot(str)
    def removePackage(self, pkgname):
        def task(emit):
            _wait_for_pacman_lock(emit)
            rc = _run(["sudo", "-n", REYOS_ADMIN, "remove-package", pkgname], emit)
            return rc == 0, (
                f"Removed: {pkgname}" if rc == 0
                else f"Failed to remove {pkgname} -- it may still be required by another package."
            )
        self._run_action(task)

    # --- Flatpak -----------------------------------------------------------

    @staticmethod
    def _compute_flatpak_list():
        try:
            out = subprocess.check_output(
                ["flatpak", "list", "--app", "--columns=application,name,version"], text=True,
            )
        except Exception:
            return []
        apps = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            apps.append({
                "appId": parts[0],
                "appName": parts[1],
                "appVersion": parts[2] if len(parts) > 2 else "",
            })
        return apps

    @Slot()
    def listFlatpaks(self):
        self._flatpak_worker = ListWorker(self._compute_flatpak_list)
        self._flatpak_worker.ready.connect(self.flatpaksListed.emit)
        self._flatpak_worker.start()

    @Slot(str)
    def removeFlatpak(self, app_id):
        def task(emit):
            rc = _run(["flatpak", "uninstall", "-y", app_id], emit)
            return rc == 0, (f"Removed: {app_id}" if rc == 0 else f"Failed to remove {app_id}.")
        self._run_action(task)

    @Slot()
    def updateFlatpaks(self):
        def task(emit):
            rc = _run(["flatpak", "update", "-y"], emit)
            return rc == 0, ("Flatpaks updated." if rc == 0 else "Flatpak update failed.")
        self._run_action(task)

    # --- systemd services ---------------------------------------------------

    @staticmethod
    def _compute_service_search(query):
        query = query.strip().lower()
        if not query:
            return []
        try:
            out = subprocess.check_output(
                ["systemctl", "list-unit-files", "--type=service", "--no-legend", "--plain", "--no-pager"],
                text=True,
            )
        except Exception:
            return []
        matches = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            unit, state = parts[0], parts[1]
            if query not in unit.lower():
                continue
            matches.append({"unit": unit, "unitEnabled": state})
            if len(matches) >= 40:
                break
        # Live active state + description only for the (small) filtered set
        # actually shown -- calling this per unit for every installed
        # .service file would be hundreds of subprocess calls.
        for m in matches:
            m["active"] = Backend._service_is_active(m["unit"])
            m["desc"] = Backend._service_description(m["unit"])
        return matches

    @staticmethod
    def _service_is_active(unit):
        try:
            return subprocess.check_output(
                ["systemctl", "is-active", unit], text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except subprocess.CalledProcessError as e:
            return (e.output or "inactive").strip()
        except Exception:
            return "unknown"

    @staticmethod
    def _service_description(unit):
        try:
            return subprocess.check_output(
                ["systemctl", "show", unit, "--property=Description", "--value"], text=True,
            ).strip()
        except Exception:
            return ""

    @staticmethod
    def _compute_running_services():
        try:
            out = subprocess.check_output(
                ["systemctl", "list-units", "--type=service", "--state=running",
                 "--no-legend", "--plain", "--no-pager"], text=True,
            )
        except Exception:
            return []
        results = []
        for line in out.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 1:
                continue
            unit = parts[0]
            desc = parts[4] if len(parts) > 4 else Backend._service_description(unit)
            try:
                enabled = subprocess.check_output(
                    ["systemctl", "is-enabled", unit], text=True, stderr=subprocess.DEVNULL,
                ).strip()
            except subprocess.CalledProcessError as e:
                enabled = (e.output or "unknown").strip()
            except Exception:
                enabled = "unknown"
            results.append({"unit": unit, "active": "active", "unitEnabled": enabled, "desc": desc})
        return results

    @Slot(str)
    def searchServices(self, query):
        self._services_worker = ListWorker(lambda: self._compute_service_search(query))
        self._services_worker.ready.connect(self.servicesFound.emit)
        self._services_worker.start()

    @Slot()
    def listRunningServices(self):
        self._services_worker = ListWorker(self._compute_running_services)
        self._services_worker.ready.connect(self.servicesFound.emit)
        self._services_worker.start()

    @Slot(str, bool)
    def setServiceActive(self, unit, start):
        def task(emit):
            rc = _run(["pkexec", REYOS_ADMIN, "service", "start" if start else "stop", unit], emit)
            if rc in PKEXEC_DISMISSED:
                return True, ""
            verb = "started" if start else "stopped"
            return rc == 0, (f"{unit}: {verb}." if rc == 0 else f"Failed to {'start' if start else 'stop'} {unit}.")
        self._run_action(task)

    @Slot(str, bool)
    def setServiceEnabled(self, unit, enable):
        def task(emit):
            rc = _run(["pkexec", REYOS_ADMIN, "service", "enable" if enable else "disable", unit], emit)
            if rc in PKEXEC_DISMISSED:
                return True, ""
            verb = "enabled" if enable else "disabled"
            return rc == 0, (f"{unit}: {verb}." if rc == 0 else f"Failed to {verb} {unit}.")
        self._run_action(task)

    # --- Firewall (ufw) ------------------------------------------------------
    # ufw refuses to run at all as a non-root user, even for `ufw status`, so
    # every call here goes through sudo (all covered by the scoped NOPASSWD
    # rule written at install time -- see shellprocess_sudoers_reyos_menu.conf).

    @staticmethod
    def _compute_firewall_status():
        try:
            out = subprocess.check_output(
                ["sudo", "-n", REYOS_ADMIN, "firewall", "status", "verbose"], text=True, stderr=subprocess.STDOUT,
            )
        except Exception as e:
            return {"enabled": False, "rules": [], "error": str(e)}

        lines = out.splitlines()
        enabled = any(l.startswith("Status: active") for l in lines)
        default_line = next((l for l in lines if l.startswith("Default:")), "")

        rules = []
        try:
            numbered = subprocess.check_output(
                ["sudo", "-n", REYOS_ADMIN, "firewall", "status", "numbered"], text=True, stderr=subprocess.STDOUT,
            )
            for line in numbered.splitlines():
                line = line.strip()
                if not line.startswith("["):
                    continue
                num, _, rest = line.partition("]")
                rules.append({"num": num.strip("[ "), "rule": rest.strip()})
        except Exception:
            pass

        return {"enabled": enabled, "defaultPolicy": default_line, "rules": rules}

    @Slot()
    def refreshFirewallStatus(self):
        self._firewall_worker = InfoWorker(self._compute_firewall_status)
        self._firewall_worker.ready.connect(self.firewallStatusReady.emit)
        self._firewall_worker.start()

    @Slot(bool)
    def setFirewallEnabled(self, enable):
        def task(emit):
            note = ""
            if enable and Backend._service_is_active("sshd") == "active":
                # Enabling with default-deny-incoming and no SSH rule cuts off
                # the very session used to enable it -- a well-known ufw
                # footgun, confirmed the hard way live on the dev VM (locked
                # out of SSH, had to recover via the VM's virtual
                # keyboard/mouse). If sshd is actually running, open 22/tcp
                # first so enabling never strands an active SSH session.
                subprocess.run(["sudo", "-n", REYOS_ADMIN, "firewall", "allow", "22/tcp"], capture_output=True)
                note = " (SSH access on 22/tcp was kept open automatically.)"
            cmd = ["sudo", "-n", REYOS_ADMIN, "firewall", "enable" if enable else "disable"]
            rc = subprocess.run(cmd, capture_output=True, text=True).returncode
            if rc != 0:
                return False, "Failed to change firewall state."
            return True, ("Firewall enabled." + note if enable else "Firewall disabled.")
        self._run_action(task)

    @Slot(str, bool)
    def addFirewallRule(self, port, allow):
        def task(emit):
            port = port.strip()
            if not port:
                return False, "Enter a port (e.g. 22 or 22/tcp) or service name."
            verb = "allow" if allow else "deny"
            result = subprocess.run(["sudo", "-n", REYOS_ADMIN, "firewall", verb, port], capture_output=True, text=True)
            ok = result.returncode == 0
            return ok, (f"Rule added: {verb} {port}" if ok else (result.stderr.strip() or result.stdout.strip() or "Failed to add rule."))
        self._run_action(task)

    @Slot(str)
    def removeFirewallRule(self, rule_num):
        def task(emit):
            result = subprocess.run(
                ["sudo", "-n", REYOS_ADMIN, "firewall", "delete", rule_num], capture_output=True, text=True,
            )
            ok = result.returncode == 0
            return ok, (f"Rule {rule_num} removed." if ok else (result.stderr.strip() or "Failed to remove rule."))
        self._run_action(task)

    # --- VPN (WireGuard, bring-your-own-config) -------------------------------
    # No bundled provider -- users import a .conf from whatever WireGuard-based
    # VPN they already have (Mullvad, ProtonVPN, etc). wg-quick@.service is
    # the systemd template wireguard-tools itself ships, one unit per profile
    # name (matching the .conf file's basename in /etc/wireguard).

    @staticmethod
    def _compute_vpn_status():
        try:
            profiles = subprocess.run(["sudo", "-n", REYOS_ADMIN, "vpn", "list"],
                                      capture_output=True, text=True).stdout.split()
        except Exception:
            profiles = []
        active = ""
        try:
            out = subprocess.check_output(
                ["sudo", "-n", REYOS_ADMIN, "vpn", "interfaces"], text=True, stderr=subprocess.DEVNULL,
            ).split()
            active = out[0] if out else ""
        except Exception:
            pass
        return {"profiles": profiles, "active": active}

    @Slot()
    def refreshVpnStatus(self):
        self._vpn_worker = InfoWorker(self._compute_vpn_status)
        self._vpn_worker.ready.connect(self.vpnStatusReady.emit)
        self._vpn_worker.start()

    @Slot()
    def pickVpnConfigFile(self):
        def task(emit):
            result = subprocess.run(
                ["kdialog", "--title", "Import VPN Config", "--getopenfilename",
                 str(Path.home()), "WireGuard configs (*.conf)"],
                capture_output=True, text=True,
            )
            return True, result.stdout.strip()
        self._vpn_picker_worker = ActionWorker(task)
        self._vpn_picker_worker.finished_ok.connect(lambda _ok, path: self.vpnConfigSelected.emit(path))
        self._vpn_picker_worker.start()

    @Slot(str)
    def importVpnConfig(self, path):
        def task(emit):
            src = _expand(path)
            if not Path(src).is_file():
                return False, f"File not found: {src}"
            name = Path(src).stem
            result = subprocess.run(["sudo", "-n", REYOS_ADMIN, "vpn", "import", str(Path(src).resolve())],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                return True, f'Imported "{name}".'
            return False, (result.stderr.strip().removeprefix("reyos-admin: ") or "Failed to import config.")
        self._run_action(task)

    @Slot(str)
    def connectVpn(self, name):
        def task(emit):
            # A single "connect" toggle implies one active tunnel at a time,
            # even though WireGuard itself supports several simultaneously --
            # stop whatever else is up first so switching profiles doesn't
            # leave two tunnels racing for the default route.
            try:
                active = subprocess.check_output(
                    ["sudo", "-n", REYOS_ADMIN, "vpn", "interfaces"], text=True, stderr=subprocess.DEVNULL,
                ).split()
            except Exception:
                active = []
            for iface in active:
                if iface != name:
                    subprocess.run(["sudo", "-n", REYOS_ADMIN, "vpn", "down", iface], capture_output=True)
            result = subprocess.run(
                ["sudo", "-n", REYOS_ADMIN, "vpn", "up", name], capture_output=True, text=True,
            )
            ok = result.returncode == 0
            return ok, (f"Connected: {name}" if ok else (result.stderr.strip() or "Failed to connect."))
        self._run_action(task)

    @Slot(str)
    def disconnectVpn(self, name):
        def task(emit):
            result = subprocess.run(
                ["sudo", "-n", REYOS_ADMIN, "vpn", "down", name], capture_output=True, text=True,
            )
            ok = result.returncode == 0
            return ok, ("Disconnected." if ok else (result.stderr.strip() or "Failed to disconnect."))
        self._run_action(task)

    @Slot(str)
    def deleteVpnConfig(self, name):
        def task(emit):
            rc = subprocess.run(["sudo", "-n", REYOS_ADMIN, "vpn", "delete", name]).returncode
            return rc == 0, (f'Removed "{name}".' if rc == 0 else "Failed to remove config.")
        self._run_action(task)

    # --- Security dashboard ---------------------------------------------------
    # Consolidated firewall+VPN+Shields+permissions view -- the "safe by
    # default" pitch should be provable at a glance, not something a user
    # has to go find three separate pages to confirm piece by piece.

    @staticmethod
    def _compute_security_overview():
        firewall = Backend._compute_firewall_status()
        vpn = Backend._compute_vpn_status()
        shields_blocked = 0
        try:
            stats_path = Path.home() / ".local" / "share" / "reyos-browser" / "shields-stats.json"
            data = json.loads(stats_path.read_text(encoding="utf-8"))
            shields_blocked = data.get("lifetimeBlocked", 0)
            if not isinstance(shields_blocked, int):
                shields_blocked = 0
        except (OSError, json.JSONDecodeError):
            pass
        return {
            "firewallEnabled": firewall.get("enabled", False),
            "vpnActive": vpn.get("active", ""),
            "vpnProfileCount": len(vpn.get("profiles", [])),
            "shieldsBlocked": shields_blocked,
        }

    @Slot()
    def refreshSecurityOverview(self):
        self._security_worker = InfoWorker(self._compute_security_overview)
        self._security_worker.ready.connect(self.securityOverviewReady.emit)
        self._security_worker.start()

    # --- USBGuard (BadUSB protection, opt-in) ---------------------------------
    # Deliberately off by default -- unlike the firewall, blocking new USB
    # devices out of the box would surprise a normal user plugging in a
    # flash drive on a "simple" pitch OS. This is an opt-in toggle, not a
    # default-on protection.

    @staticmethod
    def _compute_usbguard_status():
        return {"enabled": Backend._service_is_active("usbguard") == "active"}

    @Slot()
    def refreshUsbGuardStatus(self):
        self._usbguard_worker = InfoWorker(self._compute_usbguard_status)
        self._usbguard_worker.ready.connect(self.usbGuardStatusReady.emit)
        self._usbguard_worker.start()

    @Slot()
    def enableUsbGuard(self):
        def task(emit):
            rc = subprocess.run(["sudo", "-n", REYOS_ADMIN, "usbguard", "enable"]).returncode
            return rc == 0, ("USB protection enabled. Currently connected devices were allowed automatically." if rc == 0 else "Failed to start USBGuard.")
        self._run_action(task)

    @Slot()
    def disableUsbGuard(self):
        def task(emit):
            rc = subprocess.run(["sudo", "-n", REYOS_ADMIN, "usbguard", "disable"]).returncode
            return rc == 0, ("USB protection disabled." if rc == 0 else "Failed to stop USBGuard.")
        self._run_action(task)

    # --- CVE-tagged updates ----------------------------------------------------
    # Arch has no clean official CVE-tagging built into pacman itself to
    # distinguish "security-critical" from routine updates -- but the Arch
    # Security Team already maintains exactly that data at
    # security.archlinux.org, and arch-audit (an official-ish, actively
    # maintained package) already reads it correctly. Wrapping that real
    # tool instead of hand-rolling a parser against an unofficial feed.

    @staticmethod
    def _compute_security_updates():
        try:
            out = subprocess.check_output(
                ["arch-audit", "-u", "-f", "%n|%v|%s|%c"],
                text=True, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return []
        except subprocess.CalledProcessError as e:
            # arch-audit exits non-zero when it finds anything -- that's
            # the normal "issues found" case, not a real failure; the
            # output is still valid.
            out = e.output or ""
        issues = []
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) < 4 or not parts[0]:
                continue
            issues.append({
                "name": parts[0], "fixedVersion": parts[1],
                "severity": parts[2], "cves": parts[3],
            })
        return issues

    @Slot()
    def refreshSecurityUpdates(self):
        self._security_updates_worker = ListWorker(self._compute_security_updates)
        self._security_updates_worker.ready.connect(self.securityUpdatesReady.emit)
        self._security_updates_worker.start()

    # --- Users & Groups ------------------------------------------------------
    # Listing needs no privilege (/etc/passwd is world-readable) -- only
    # add/delete/password/admin-toggle go through pkexec, via the dedicated
    # reyos-manage-users.sh helper (org.reyos.controlcenter.manageusers),
    # which does its own hard validation (refuses to touch the calling
    # account or any system account) independent of whatever this process
    # sends it.

    _USERS_HELPER = str(APP_DIR / "reyos-manage-users.sh")

    @staticmethod
    def _compute_user_list():
        try:
            wheel_members = set(grp.getgrnam("wheel").gr_mem)
        except KeyError:
            wheel_members = set()
        self_name = pwd.getpwuid(os.getuid()).pw_name

        users = []
        for entry in pwd.getpwall():
            # Arch's useradd default range (login.defs UID_MIN/UID_MAX) --
            # excludes system/service accounts and the 65534 nobody account.
            if not (1000 <= entry.pw_uid < 60000):
                continue
            users.append({
                "username": entry.pw_name,
                "fullName": entry.pw_gecos.split(",")[0] or entry.pw_name,
                "uid": entry.pw_uid,
                "homeDir": entry.pw_dir,
                "shell": entry.pw_shell,
                "isAdmin": entry.pw_name in wheel_members,
                "isSelf": entry.pw_name == self_name,
            })
        users.sort(key=lambda u: u["uid"])
        return users

    @Slot()
    def listUsers(self):
        self._users_worker = ListWorker(self._compute_user_list)
        self._users_worker.ready.connect(self.usersListed.emit)
        self._users_worker.start()

    @Slot(str, str, str, bool)
    def addUser(self, username, fullname, password, is_admin):
        def task(emit):
            result = subprocess.run(
                ["pkexec", self._USERS_HELPER, "add", username, fullname, "1" if is_admin else "0"],
                input=password, capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f"User created: {username}"
            if result.returncode in (126, 127):
                return False, "Authentication cancelled."
            return False, (result.stderr.strip() or "Failed to create user.")
        self._run_action(task)

    @Slot(str, bool)
    def deleteUser(self, username, remove_home):
        def task(emit):
            result = subprocess.run(
                ["pkexec", self._USERS_HELPER, "delete", username, "1" if remove_home else "0"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f"User removed: {username}"
            if result.returncode in (126, 127):
                return False, "Authentication cancelled."
            return False, (result.stderr.strip() or "Failed to remove user.")
        self._run_action(task)

    @Slot(str, str)
    def setUserPassword(self, username, password):
        def task(emit):
            result = subprocess.run(
                ["pkexec", self._USERS_HELPER, "setpassword", username],
                input=password, capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f"Password changed for {username}."
            if result.returncode in (126, 127):
                return False, "Authentication cancelled."
            return False, (result.stderr.strip() or "Failed to change password.")
        self._run_action(task)

    @Slot(str, bool)
    def setUserAdmin(self, username, enable):
        def task(emit):
            result = subprocess.run(
                ["pkexec", self._USERS_HELPER, "setadmin", username, "1" if enable else "0"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, (f"{username} is now an admin." if enable else f"{username} is no longer an admin.")
            if result.returncode in (126, 127):
                return False, "Authentication cancelled."
            return False, (result.stderr.strip() or "Failed to change admin status.")
        self._run_action(task)

    # --- Startup apps (autostart) -------------------------------------------
    # User entries live in ~/.config/autostart; system ones in
    # $XDG_CONFIG_DIRS/autostart. A same-named user file overrides the system
    # one, and Hidden=true there turns it off for this user only -- the same
    # convention Plasma's own Autostart settings use, honoured by
    # systemd-xdg-autostart-generator.

    @staticmethod
    def _compute_autostart_list():
        items, system_fields = {}, {}
        for d in reversed(_autostart_system_dirs()):
            for f in sorted(d.glob("*.desktop")):
                fields = _read_desktop_entry(f)
                if (fields.get("Hidden") == "true" or not _shown_in_kde(fields)
                        or _is_session_plumbing(f.name, fields)):
                    items.pop(f.name, None)
                    continue
                items[f.name] = _autostart_item(f.name, fields, system=True, enabled=True)
                system_fields[f.name] = fields
        if _AUTOSTART_USER_DIR.is_dir():
            for f in sorted(_AUTOSTART_USER_DIR.glob("*.desktop")):
                fields = {**system_fields.get(f.name, {}), **_read_desktop_entry(f)}
                system = f.name in items and items[f.name]["system"]
                hidden = fields.get("Hidden") == "true"
                if not _shown_in_kde(fields) or (hidden and not system):
                    continue
                enabled = not hidden and fields.get("X-GNOME-Autostart-enabled") != "false"
                items[f.name] = _autostart_item(f.name, fields, system=system, enabled=enabled)
        return sorted(items.values(), key=lambda i: i["name"].lower())

    @Slot()
    def listAutostart(self):
        self._autostart_worker = ListWorker(self._compute_autostart_list)
        self._autostart_worker.ready.connect(self.autostartListed.emit)
        self._autostart_worker.start()

    @staticmethod
    def _compute_startup_candidates():
        already = {i["id"] for i in Backend._compute_autostart_list()}
        apps = {}
        for d in _APPLICATION_DIRS:
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.desktop")):
                fields = _read_desktop_entry(f)
                if (fields.get("Type", "Application") != "Application" or fields.get("NoDisplay") == "true"
                        or fields.get("Hidden") == "true" or not fields.get("Exec") or not _shown_in_kde(fields)):
                    apps.pop(f.name, None)
                    continue
                if f.name not in already:
                    apps[f.name] = {"id": f.name, "name": fields.get("Name", f.stem),
                                    "icon": fields.get("Icon", ""), "comment": fields.get("Comment", "")}
        return sorted(apps.values(), key=lambda a: a["name"].lower())

    @Slot()
    def listStartupCandidates(self):
        self._candidates_worker = ListWorker(self._compute_startup_candidates)
        self._candidates_worker.ready.connect(self.startupCandidatesListed.emit)
        self._candidates_worker.start()

    @Slot(str, bool)
    def setAutostartEnabled(self, entry_id, enable):
        def task(emit):
            if not _valid_desktop_id(entry_id):
                return False, "Not a startup entry."
            target = _AUTOSTART_USER_DIR / entry_id
            if not target.is_file():
                source = next((d / entry_id for d in _autostart_system_dirs() if (d / entry_id).is_file()), None)
                if source is None:
                    return False, f"Startup entry not found: {entry_id}"
                _AUTOSTART_USER_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            _set_desktop_keys(target, {"Hidden": "false" if enable else "true",
                                       "X-GNOME-Autostart-enabled": "true" if enable else "false"})
            name = _read_desktop_entry(target).get("Name", entry_id)
            return True, ("Starts at login: " if enable else "Won't start at login: ") + name
        self._run_action(task)

    @Slot(str)
    def addAutostart(self, desktop_id):
        def task(emit):
            if not _valid_desktop_id(desktop_id):
                return False, "Not an app."
            source = None
            for d in _APPLICATION_DIRS:
                if (d / desktop_id).is_file():
                    source = d / desktop_id
            if source is None:
                return False, f"App not found: {desktop_id}"
            _AUTOSTART_USER_DIR.mkdir(parents=True, exist_ok=True)
            target = _AUTOSTART_USER_DIR / desktop_id
            shutil.copyfile(source, target)
            _set_desktop_keys(target, {"Hidden": "false", "X-GNOME-Autostart-enabled": "true"})
            return True, "Starts at login: " + _read_desktop_entry(target).get("Name", desktop_id)
        self._run_action(task)

    @Slot(str)
    def removeAutostart(self, entry_id):
        def task(emit):
            target = _AUTOSTART_USER_DIR / entry_id
            if not _valid_desktop_id(entry_id) or not target.is_file():
                return False, "Startup entry not found."
            if any((d / entry_id).is_file() for d in _autostart_system_dirs()):
                return False, "This one comes with the system -- switch it off instead."
            if entry_id.startswith("reyos-"):
                return False, "This is part of ReyOS -- switch it off instead."
            name = _read_desktop_entry(target).get("Name", entry_id)
            target.unlink()
            return True, "Removed from startup: " + name
        self._run_action(task)

    @Slot(result=bool)
    def sessionRestoreEnabled(self):
        return self._kread("ksmserverrc", ["General"], "loginMode", "restorePreviousLogout") != "emptySession"

    @Slot(bool)
    def setSessionRestore(self, enable):
        def task(emit):
            self._kwrite("ksmserverrc", ["General"], "loginMode",
                         "restorePreviousLogout" if enable else "emptySession")
            return True, ("Apps open at logout will reopen next time." if enable
                          else "You'll start with an empty desktop next time.")
        self._run_action(task)


    # --- Sound (PipeWire via pactl) ------------------------------------------
    # No sudo anywhere here -- pactl only ever talks to the caller's own
    # PipeWire session, same privilege level as any other desktop app.

    @staticmethod
    def _pactl_json(kind):
        try:
            out = subprocess.check_output(["pactl", "-f", "json", "list", kind], text=True)
            return json.loads(out)
        except Exception:
            return []

    @staticmethod
    def _compute_audio_info():
        default_sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True).stdout.strip()
        default_source = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True).stdout.strip()

        def summarize(devices, default_name):
            rows = []
            for d in devices:
                vol_pct = 0
                vols = d.get("volume") or {}
                if vols:
                    first = next(iter(vols.values()))
                    try:
                        vol_pct = int(str(first.get("value_percent", "0%")).rstrip("%"))
                    except ValueError:
                        vol_pct = 0
                rows.append({
                    "name": d.get("name", ""),
                    "description": d.get("description") or d.get("name", ""),
                    "volume": vol_pct,
                    "muted": bool(d.get("mute", False)),
                    "isDefault": d.get("name", "") == default_name,
                })
            return rows

        return {
            "sinks": summarize(Backend._pactl_json("sinks"), default_sink),
            "sources": summarize(Backend._pactl_json("sources"), default_source),
        }

    @Slot()
    def refreshAudioInfo(self):
        self._audio_worker = InfoWorker(self._compute_audio_info)
        self._audio_worker.ready.connect(self.audioInfoReady.emit)
        self._audio_worker.start()

    @Slot(str)
    def setDefaultSink(self, name):
        def task(emit):
            rc = subprocess.run(["pactl", "set-default-sink", name], capture_output=True).returncode
            return rc == 0, ("Default output set." if rc == 0 else "Failed to set default output.")
        self._run_action(task)

    @Slot(str)
    def setDefaultSource(self, name):
        def task(emit):
            rc = subprocess.run(["pactl", "set-default-source", name], capture_output=True).returncode
            return rc == 0, ("Default input set." if rc == 0 else "Failed to set default input.")
        self._run_action(task)

    @Slot(str, int)
    def setSinkVolume(self, name, percent):
        def task(emit):
            rc = subprocess.run(["pactl", "set-sink-volume", name, f"{percent}%"], capture_output=True).returncode
            return rc == 0, ("Volume set." if rc == 0 else "Failed to set volume.")
        self._run_action(task)

    @Slot(str, bool)
    def setSinkMute(self, name, mute):
        def task(emit):
            rc = subprocess.run(["pactl", "set-sink-mute", name, "1" if mute else "0"], capture_output=True).returncode
            return rc == 0, (("Muted." if mute else "Unmuted.") if rc == 0 else "Failed to change mute state.")
        self._run_action(task)

    @Slot(str, int)
    def setSourceVolume(self, name, percent):
        def task(emit):
            rc = subprocess.run(["pactl", "set-source-volume", name, f"{percent}%"], capture_output=True).returncode
            return rc == 0, ("Volume set." if rc == 0 else "Failed to set volume.")
        self._run_action(task)

    @Slot(str, bool)
    def setSourceMute(self, name, mute):
        def task(emit):
            rc = subprocess.run(["pactl", "set-source-mute", name, "1" if mute else "0"], capture_output=True).returncode
            return rc == 0, (("Muted." if mute else "Unmuted.") if rc == 0 else "Failed to change mute state.")
        self._run_action(task)

    # --- Bluetooth ---------------------------------------------------------
    # bluetoothctl hangs indefinitely -- not just fails -- when there's no
    # adapter or bluetoothd isn't responding (confirmed live on the dev VM,
    # a plain `bluetoothctl show` with no adapter present never returned).
    # Every call here goes through `timeout` so a missing adapter degrades to
    # "no adapter found" instead of freezing that action's worker thread.

    @staticmethod
    def _bt(args, timeout_s=5):
        try:
            return subprocess.run(
                ["timeout", str(timeout_s), "bluetoothctl"] + args,
                capture_output=True, text=True,
            )
        except Exception:
            return None

    # Discovery only lasts as long as the bluetoothctl client that started
    # it: a plain non-interactive `bluetoothctl scan on` exits in ~10 ms
    # (BlueZ 5.87), which stops discovery again before anything is found.
    # `--timeout N` keeps the client -- and so the scan -- alive for N
    # seconds; it runs as a background process so the device list can
    # refresh live while it scans.
    _bt_scan_proc = None
    BT_SCAN_SECONDS = 30

    @staticmethod
    def _bt_scanning():
        proc = Backend._bt_scan_proc
        return proc is not None and proc.poll() is None

    @staticmethod
    def _bt_stop_scan():
        proc = Backend._bt_scan_proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        Backend._bt_scan_proc = None

    @staticmethod
    def _compute_bluetooth_status():
        show = Backend._bt(["show"])
        if show is None or show.returncode != 0 or not show.stdout.strip():
            return {"hasAdapter": False, "powered": False, "scanning": False, "devices": []}

        powered = "Powered: yes" in show.stdout

        devices = []
        listed = Backend._bt(["devices"])
        if listed and listed.stdout:
            for line in listed.stdout.splitlines():
                parts = line.split(" ", 2)
                if len(parts) < 3 or parts[0] != "Device":
                    continue
                mac, name = parts[1], parts[2]
                info = Backend._bt(["info", mac])
                connected = bool(info and "Connected: yes" in info.stdout)
                paired = bool(info and "Paired: yes" in info.stdout)
                # A scan in a busy room turns up dozens of nameless BLE
                # beacons (BlueZ names them after their address) that
                # nobody can pair with anyway -- hide those unless paired.
                if name == mac.replace(":", "-") and not paired:
                    continue
                devices.append({"mac": mac, "name": name, "connected": connected, "paired": paired})

        return {"hasAdapter": True, "powered": powered, "scanning": Backend._bt_scanning(), "devices": devices}

    @Slot()
    def refreshBluetoothStatus(self):
        # Overwriting a still-running QThread aborts the process, and the
        # live scan refresh makes overlapping calls possible -- but dropping
        # the call instead left the page showing the pre-pair state, so
        # remember it and run once more when the current refresh is done.
        worker = getattr(self, "_bluetooth_worker", None)
        if worker is not None and worker.isRunning():
            self._bt_refresh_again = True
            return
        self._bt_refresh_again = False
        self._bluetooth_worker = InfoWorker(self._compute_bluetooth_status)
        self._bluetooth_worker.ready.connect(self._bt_status_ready)
        self._bluetooth_worker.start()

    def _bt_status_ready(self, info):
        self.bluetoothStatusReady.emit(info)
        if getattr(self, "_bt_refresh_again", False):
            QTimer.singleShot(0, self.refreshBluetoothStatus)

    def _bt_scan_tick(self):
        self.refreshBluetoothStatus()
        if not Backend._bt_scanning():
            self._bt_scan_timer.stop()
            # One last refresh after the worker above finishes, so the page
            # sees scanning=false even if that refresh was skipped.
            QTimer.singleShot(1500, self.refreshBluetoothStatus)

    @Slot(bool)
    def setBluetoothPowered(self, on):
        def task(emit):
            result = Backend._bt(["power", "on" if on else "off"])
            ok = bool(result and result.returncode == 0)
            return ok, (("Bluetooth turned on." if on else "Bluetooth turned off.") if ok else "Failed -- is an adapter present?")
        self._run_action(task)

    @Slot()
    def scanBluetoothDevices(self):
        Backend._bt_stop_scan()
        try:
            Backend._bt_scan_proc = subprocess.Popen(
                ["bluetoothctl", "--timeout", str(Backend.BT_SCAN_SECONDS), "scan", "on"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=_die_with_parent,
            )
        except Exception as e:
            self.actionFinished.emit(False, f"Couldn't start scanning: {e}")
            return
        if not hasattr(self, "_bt_scan_timer"):
            self._bt_scan_timer = QTimer(self)
            self._bt_scan_timer.setInterval(2000)
            self._bt_scan_timer.timeout.connect(self._bt_scan_tick)
        self._bt_scan_timer.start()
        self.refreshBluetoothStatus()

    @Slot()
    def stopBluetoothScan(self):
        # Called when the user leaves the Bluetooth page: discovery slows
        # down already-connected Bluetooth audio/input, so don't leave it on.
        Backend._bt_stop_scan()

    @Slot(str)
    def pairBluetoothDevice(self, mac):
        def task(emit):
            # Pairing while discovery is running failed every time on real
            # hardware (Intel adapter + Xbox pad: ConnectionAttemptFailed in
            # ~0.1 s), so stop the scan first. A pad only stays in pairing
            # mode for ~20 s, so retry quickly -- rediscovering it briefly
            # if BlueZ already dropped it -- rather than failing once.
            Backend._bt_stop_scan()
            # Another app still searching (KDE's "Add Bluetooth Device"
            # wizard, a second Control Center window) makes the pair fail
            # in ~0.1 s; stopping our own scan can't stop theirs.
            time.sleep(0.5)
            show = Backend._bt(["show"])
            other_scan = bool(show and "Discovering: yes" in show.stdout)
            pair = None
            for attempt in range(3):
                info = Backend._bt(["info", mac])
                if not info or info.returncode != 0 or not info.stdout.strip():
                    Backend._bt(["--timeout", "4", "scan", "on"], timeout_s=6)
                pair = Backend._bt(["pair", mac], timeout_s=30)
                done = Backend._bt(["info", mac])
                if done and "Paired: yes" in done.stdout:
                    break
                time.sleep(1)
            else:
                detail = (pair.stdout.strip().splitlines() or [""])[-1] if pair else ""
                if other_scan:
                    return False, ("Couldn't pair: another app is searching for Bluetooth devices at the same time "
                                   "(close KDE's \"Add Bluetooth Device\" window or other Control Center windows), then try again."
                                   + (f" ({detail})" if detail else ""))
                return False, (f"Couldn't pair with {mac}. Make sure it is in pairing mode, then try again."
                               + (f" ({detail})" if detail else ""))
            Backend._bt(["trust", mac])
            # Input devices (pads, keyboards, mice) connect themselves right
            # after pairing; only ask for a connection if that didn't happen.
            time.sleep(2)
            info = Backend._bt(["info", mac])
            if not (info and "Connected: yes" in info.stdout):
                Backend._bt(["connect", mac], timeout_s=15)
                info = Backend._bt(["info", mac])
            ok = bool(info and "Connected: yes" in info.stdout)
            return True, (f"Paired and connected: {mac}" if ok else f"Paired: {mac} -- turn the device on to connect.")
        self._run_action(task)

    @Slot(str)
    def connectBluetoothDevice(self, mac):
        def task(emit):
            result = Backend._bt(["connect", mac], timeout_s=10)
            ok = bool(result and result.returncode == 0)
            return ok, (f"Connected: {mac}" if ok else f"Failed to connect: {mac}")
        self._run_action(task)

    @Slot(str)
    def disconnectBluetoothDevice(self, mac):
        def task(emit):
            result = Backend._bt(["disconnect", mac])
            ok = bool(result and result.returncode == 0)
            return ok, (f"Disconnected: {mac}" if ok else f"Failed to disconnect: {mac}")
        self._run_action(task)

    @Slot(str)
    def removeBluetoothDevice(self, mac):
        def task(emit):
            result = Backend._bt(["remove", mac])
            ok = bool(result and result.returncode == 0)
            return ok, (f"Removed: {mac}" if ok else f"Failed to remove: {mac}")
        self._run_action(task)

    # --- Wi-Fi (NetworkManager via nmcli) -----------------------------------
    # No sudo -- NetworkManager's own polkit rules already let the active
    # local session user manage their own connections (same reason the
    # plasma-nm applet never prompts for a password on a normal toggle).

    @staticmethod
    def _compute_wifi_status():
        radio = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True).stdout.strip()
        enabled = radio == "enabled"

        has_device = False
        try:
            devs = subprocess.check_output(["nmcli", "-t", "-f", "TYPE,DEVICE,STATE", "device"], text=True)
            has_device = any(line.startswith("wifi:") for line in devs.splitlines())
        except Exception:
            pass

        aps = []
        if enabled and has_device:
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"], text=True,
                )
                seen = set()
                for line in out.splitlines():
                    parts = _nmcli_fields(line)
                    if len(parts) < 4:
                        continue
                    in_use, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
                    if not ssid or ssid in seen:
                        continue
                    seen.add(ssid)
                    try:
                        signal_i = int(signal)
                    except ValueError:
                        signal_i = 0
                    aps.append({"ssid": ssid, "signal": signal_i, "security": security, "inUse": in_use == "*"})
                aps.sort(key=lambda a: a["signal"], reverse=True)
            except Exception:
                pass

        saved = []
        try:
            out = subprocess.check_output(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"], text=True)
            for line in out.splitlines():
                parts = _nmcli_fields(line)
                if len(parts) >= 2 and parts[1] == "802-11-wireless":
                    saved.append(parts[0])
        except Exception:
            pass

        return {"hasDevice": has_device, "enabled": enabled, "aps": aps, "saved": saved}

    @Slot()
    def refreshWifiStatus(self):
        self._wifi_worker = InfoWorker(self._compute_wifi_status)
        self._wifi_worker.ready.connect(self.wifiStatusReady.emit)
        self._wifi_worker.start()

    @Slot(bool)
    def setWifiRadioEnabled(self, enable):
        def task(emit):
            rc = subprocess.run(["nmcli", "radio", "wifi", "on" if enable else "off"], capture_output=True).returncode
            return rc == 0, (("Wi-Fi turned on." if enable else "Wi-Fi turned off.") if rc == 0 else "Failed to change Wi-Fi radio state.")
        self._run_action(task)

    @Slot(str, str)
    def connectWifi(self, ssid, password):
        def task(emit):
            cmd = ["nmcli", "device", "wifi", "connect", ssid]
            if password:
                cmd += ["password", password]
            result = subprocess.run(cmd, capture_output=True, text=True)
            ok = result.returncode == 0
            return ok, (f"Connected to {ssid}." if ok else (result.stderr.strip() or f"Failed to connect to {ssid}."))
        self._run_action(task)

    @Slot(str)
    def forgetWifi(self, name):
        def task(emit):
            rc = subprocess.run(["nmcli", "connection", "delete", name], capture_output=True).returncode
            return rc == 0, (f"Forgot: {name}" if rc == 0 else f"Failed to forget: {name}")
        self._run_action(task)

    # --- WireGuard (NetworkManager via nmcli) ---------------------------------
    # Same no-sudo reasoning as Wi-Fi above -- NetworkManager's polkit rules
    # already let the active session user import/activate/remove their own
    # connection profiles.

    @staticmethod
    def _compute_wireguard_connections():
        conns = []
        try:
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "NAME,TYPE,ACTIVE", "connection", "show"], text=True,
            )
            for line in out.splitlines():
                parts = _nmcli_fields(line)
                if len(parts) >= 3 and parts[1] == "wireguard":
                    conns.append({"name": parts[0], "active": parts[2] == "yes"})
        except Exception:
            pass
        return conns

    @Slot()
    def refreshWireguardStatus(self):
        self._wireguard_worker = ListWorker(self._compute_wireguard_connections)
        self._wireguard_worker.ready.connect(self.wireguardListed.emit)
        self._wireguard_worker.start()

    @Slot()
    def importWireguardConfig(self):
        def task(emit):
            picked = subprocess.run(
                ["kdialog", "--title", "Choose WireGuard Configuration", "--getopenfilename",
                 str(Path.home()), "WireGuard config (*.conf)"],
                capture_output=True, text=True,
            )
            path = picked.stdout.strip()
            if not path:
                # Cancel is a normal outcome, not a failure -- say nothing.
                return True, ""
            result = subprocess.run(
                ["sudo", "-n", REYOS_ADMIN, "nm-import-wireguard", str(Path(path).resolve())],
                capture_output=True, text=True,
            )
            ok = result.returncode == 0
            if ok:
                return True, f"Imported: {Path(path).name}"
            # NetworkManager requires the profile name (derived from the
            # interface name inside the file) to be a valid interface name --
            # surface its actual stderr rather than a generic failure message,
            # since that's the most common reason this fails.
            return False, (result.stderr.strip() or "Failed to import configuration.")
        self._run_action(task)

    @Slot(str)
    def connectWireguard(self, name):
        def task(emit):
            result = subprocess.run(["nmcli", "connection", "up", name], capture_output=True, text=True)
            ok = result.returncode == 0
            return ok, (f"Connected: {name}" if ok else (result.stderr.strip() or f"Failed to connect: {name}"))
        self._run_action(task)

    @Slot(str)
    def disconnectWireguard(self, name):
        def task(emit):
            rc = subprocess.run(["nmcli", "connection", "down", name], capture_output=True).returncode
            return rc == 0, (f"Disconnected: {name}" if rc == 0 else f"Failed to disconnect: {name}")
        self._run_action(task)

    @Slot(str)
    def removeWireguard(self, name):
        def task(emit):
            rc = subprocess.run(["nmcli", "connection", "delete", name], capture_output=True).returncode
            return rc == 0, (f"Removed: {name}" if rc == 0 else f"Failed to remove: {name}")
        self._run_action(task)

    # --- Date & Time ---------------------------------------------------------

    _CLOCK_APPLETSRC = Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
    _CLOCK_FORMAT_VALUES = {"default": "0", "12h": "1", "24h": "2"}
    _CLOCK_FORMAT_LABELS = {"default": "Regional default", "12h": "12-hour", "24h": "24-hour"}

    @staticmethod
    def _digital_clock_paths():
        # Same direct-file-parse + kwriteconfig6 technique already proven for
        # the desktop folder containment in reyos-apply-branding.sh (awk over
        # the raw appletsrc file, matched by `plugin=`) rather than trusting
        # a live D-Bus reconfigure to pick this up -- `KWin reconfigure` is
        # documented elsewhere in this project (virtual desktops) to not
        # reliably re-read config for an already-running session.
        if not Backend._CLOCK_APPLETSRC.is_file():
            return []
        paths = []
        current = None
        for line in Backend._CLOCK_APPLETSRC.read_text().splitlines():
            if re.match(r"^(\[[^\]]*\])+$", line):
                current = line
                continue
            if current and line.startswith("plugin=org.kde.plasma.digitalclock") and "[Applets]" in current:
                ids = re.findall(r"\[(\d+)\]", current)
                if len(ids) >= 2:
                    paths.append((ids[0], ids[1]))
        return paths

    @staticmethod
    def _compute_datetime_info():
        try:
            out = subprocess.check_output(
                ["timedatectl", "show", "--property=Timezone,NTP,NTPSynchronized"], text=True,
            )
            info = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        except Exception:
            info = {}
        try:
            local_time = subprocess.check_output(["date", "+%Y-%m-%d %H:%M:%S %Z"], text=True).strip()
        except Exception:
            local_time = "Unknown"

        clock_format = "default"
        paths = Backend._digital_clock_paths()
        if paths:
            containment_id, applet_id = paths[0]
            try:
                out = subprocess.check_output([
                    "kreadconfig6", "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                    "--group", "Containments", "--group", containment_id,
                    "--group", "Applets", "--group", applet_id,
                    "--group", "Configuration", "--group", "Appearance",
                    "--key", "use24hFormat",
                ], text=True).strip()
                clock_format = {v: k for k, v in Backend._CLOCK_FORMAT_VALUES.items()}.get(out, "default")
            except Exception:
                pass

        return {
            "timezone": info.get("Timezone", "Unknown"),
            "ntp": info.get("NTP", "no") == "yes",
            "synced": info.get("NTPSynchronized", "no") == "yes",
            "localTime": local_time,
            "clockFormat": clock_format,
        }

    @Slot()
    def refreshDateTimeInfo(self):
        self._datetime_worker = InfoWorker(self._compute_datetime_info)
        self._datetime_worker.ready.connect(self.datetimeInfoReady.emit)
        self._datetime_worker.start()

    # Regions dropped from the picker per the user's call -- not relevant to
    # ReyOS's actual userbase, and "Etc/GMT+N" entries are inverted-sign
    # POSIX artifacts (Etc/GMT+5 is actually UTC-5) that just confuse people,
    # not real places.
    _TZ_EXCLUDED_PREFIXES = ("Africa/", "Antarctica/", "Arctic/", "Etc/", "Indian/", "Atlantic/")

    @Slot()
    def listTimezones(self):
        def compute():
            try:
                zones = subprocess.check_output(["timedatectl", "list-timezones"], text=True).splitlines()
            except Exception:
                return []
            return [z for z in zones if not z.startswith(Backend._TZ_EXCLUDED_PREFIXES)]
        self._timezones_worker = ListWorker(compute)
        self._timezones_worker.ready.connect(self.timezonesListed.emit)
        self._timezones_worker.start()

    @Slot(str)
    def setTimezone(self, tz):
        def task(emit):
            rc = subprocess.run(["sudo", "-n", REYOS_ADMIN, "time", "zone", tz], capture_output=True).returncode
            return rc == 0, (f"Timezone set to {tz}." if rc == 0 else "Failed to set timezone.")
        self._run_action(task)

    @Slot(bool)
    def setNtpEnabled(self, enable):
        def task(emit):
            rc = subprocess.run(
                ["sudo", "-n", REYOS_ADMIN, "time", "ntp", "true" if enable else "false"], capture_output=True,
            ).returncode
            return rc == 0, (("Automatic time sync enabled." if enable else "Automatic time sync disabled.") if rc == 0 else "Failed to change NTP setting.")
        self._run_action(task)

    @Slot(str)
    def setManualDateTime(self, value):
        def task(emit):
            result = subprocess.run(["sudo", "-n", REYOS_ADMIN, "time", "set", value], capture_output=True, text=True)
            ok = result.returncode == 0
            return ok, ("Date/time set." if ok else (result.stderr.strip() or "Failed -- disable automatic sync first."))
        self._run_action(task)

    @Slot(str)
    def setClockFormat(self, mode):
        def task(emit):
            value = Backend._CLOCK_FORMAT_VALUES.get(mode, "0")
            paths = Backend._digital_clock_paths()
            if not paths:
                return False, "No clock widget found on any panel."
            for containment_id, applet_id in paths:
                subprocess.run([
                    "kwriteconfig6", "--file", "plasma-org.kde.plasma.desktop-appletsrc",
                    "--group", "Containments", "--group", containment_id,
                    "--group", "Applets", "--group", applet_id,
                    "--group", "Configuration", "--group", "Appearance",
                    "--key", "use24hFormat", value,
                ])
            # Best-effort live nudge -- the write above already persists
            # regardless of whether the running panel actually redraws
            # without a re-login (not confirmed live, no VM access this
            # session -- verify on the dev VM).
            subprocess.run([
                "qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript",
                'var p = panels(); for (var i = 0; i < p.length; i++) {'
                ' var w = p[i].widgets("org.kde.plasma.digitalclock");'
                ' for (var j = 0; j < w.length; j++) { w[j].reloadConfig(); } }',
            ], capture_output=True)
            label = Backend._CLOCK_FORMAT_LABELS.get(mode, mode)
            return True, f"Clock format set to {label} ({len(paths)} panel clock{'s' if len(paths) != 1 else ''}). May need a re-login to fully apply."
        self._run_action(task)

    # --- Keyboard --------------------------------------------------------------
    # Layout list (kxkbrc) and repeat rate (kcminputrc [Keyboard]) are both
    # plain global config, unlike Mouse below -- written directly, no
    # per-device addressing needed. Live-apply for either is session/version
    # dependent and not reliably testable in this VM, so changes take effect
    # at next login rather than chasing a fragile live-reload call.

    # Standard XKB group-switch options (real System Settings' Keyboard >
    # Layouts > "Change layout" dropdown is backed by this exact same list --
    # a stable X.org/XKB standard, not KDE-version-specific internal config,
    # so unlike most of this page it doesn't need a live VM to trust).
    LAYOUT_SWITCH_OPTIONS = [
        ("", "None"),
        ("grp:alt_shift_toggle", "Alt+Shift"),
        ("grp:ctrl_shift_toggle", "Ctrl+Shift"),
        ("grp:win_space_toggle", "Win+Space"),
        ("grp:caps_toggle", "Caps Lock"),
        ("grp:sclk_toggle", "Scroll Lock"),
        ("grp:lwin_toggle", "Left Win"),
        ("grp:rwin_toggle", "Right Win"),
    ]

    @Slot()
    def refreshKeyboardInfo(self):
        def compute():
            layouts = []
            try:
                layouts = subprocess.check_output(["localectl", "list-x11-keymap-layouts"], text=True).splitlines()
            except Exception:
                pass

            current = []
            switch_shortcut = ""
            kxkbrc = Path.home() / ".config" / "kxkbrc"
            if kxkbrc.is_file():
                for line in kxkbrc.read_text().splitlines():
                    if line.startswith("LayoutList="):
                        current = [l for l in line.split("=", 1)[1].split(",") if l]
                    elif line.startswith("Options="):
                        for opt in line.split("=", 1)[1].split(","):
                            if opt.startswith("grp:"):
                                switch_shortcut = opt
                                break
            if not current:
                try:
                    out = subprocess.check_output(["localectl"], text=True)
                    for line in out.splitlines():
                        if "X11 Layout:" in line:
                            current = [line.split(":", 1)[1].strip()]
                except Exception:
                    pass

            def kb_read(key, default):
                try:
                    out = subprocess.check_output(
                        ["kreadconfig6", "--file", "kcminputrc", "--group", "Keyboard", "--key", key], text=True,
                    ).strip()
                    return out if out else default
                except Exception:
                    return default

            return {
                "availableLayouts": layouts[:300],
                "currentLayouts": current,
                "repeatRate": float(kb_read("RepeatRate", "25") or 25),
                "repeatDelay": int(float(kb_read("RepeatDelay", "600") or 600)),
                "switchShortcut": switch_shortcut,
                "switchShortcutOptions": [{"value": v, "label": l} for v, l in Backend.LAYOUT_SWITCH_OPTIONS],
            }
        self._keyboard_worker = InfoWorker(compute)
        self._keyboard_worker.ready.connect(self.keyboardInfoReady.emit)
        self._keyboard_worker.start()

    @Slot("QVariantList")
    def setKeyboardLayouts(self, layouts):
        def task(emit):
            if not layouts:
                return False, "Select at least one layout."
            csv = ",".join(layouts)
            subprocess.run(["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "LayoutList", csv])
            subprocess.run(["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "Use", "true"])
            return True, f"Layout set to: {csv} (takes effect next login)"
        self._run_action(task)

    @Slot(int, int)
    def setKeyRepeat(self, rate, delay):
        def task(emit):
            subprocess.run(["kwriteconfig6", "--file", "kcminputrc", "--group", "Keyboard", "--key", "RepeatRate", str(rate)])
            subprocess.run(["kwriteconfig6", "--file", "kcminputrc", "--group", "Keyboard", "--key", "RepeatDelay", str(delay)])
            return True, "Key repeat settings saved (takes effect next login)."
        self._run_action(task)

    @Slot(str)
    def setLayoutSwitchShortcut(self, option):
        def task(emit):
            kxkbrc = Path.home() / ".config" / "kxkbrc"
            other_opts = []
            if kxkbrc.is_file():
                for line in kxkbrc.read_text().splitlines():
                    if line.startswith("Options="):
                        other_opts = [o for o in line.split("=", 1)[1].split(",") if o and not o.startswith("grp:")]
                        break
            opts = other_opts + ([option] if option else [])
            subprocess.run(["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "Options", ",".join(opts)])
            subprocess.run(["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "ResetOldOptions", "true"])

            # Live-apply for this X11 session: setxkbmap has no "replace a
            # single option" mode, so clear every XKB option first, then
            # reapply everything (ours plus whatever else was already set).
            subprocess.run(["setxkbmap", "-option", ""], capture_output=True)
            live = True
            if option:
                live = subprocess.run(["setxkbmap", "-option", option], capture_output=True).returncode == 0
            for o in other_opts:
                subprocess.run(["setxkbmap", "-option", o], capture_output=True)

            label = dict(Backend.LAYOUT_SWITCH_OPTIONS).get(option, option or "None")
            return True, (f"Switch-layout shortcut set to {label}." if live else "Saved (live apply needs an X11 session).")
        self._run_action(task)

    # --- Custom (global) shortcuts -----------------------------------------
    # Plasma's own "Custom Shortcuts" storage format is internal/undocumented
    # KDE config (kglobalaccel component wiring) that has burned this project
    # before when guessed instead of diffed against a real change (see the
    # kcminputrc per-device group and plasma-apply-lookandfeel entries in
    # fixes.md) -- with no VM access to verify the real keys this session,
    # guessing it blind risks shipping something that silently does nothing.
    # xbindkeys is a small, stable, well-documented X11 tool that does exactly
    # "key combo -> run a command" on its own, independent of any Plasma
    # version's internal shortcut storage -- safer to build on even though it
    # means one more dependency + its own autostart entry (see PKGBUILD).
    # Our own JSON file is the source of truth; ~/.xbindkeysrc is a generated
    # artifact regenerated on every add/remove, same "template renders to a
    # real config file" pattern used for panel-template.conf elsewhere.

    _SHORTCUTS_FILE = Path.home() / ".config" / "reyos" / "custom-shortcuts.json"
    _XBINDKEYSRC = Path.home() / ".xbindkeysrc"

    @staticmethod
    def _load_shortcuts():
        try:
            return json.loads(Backend._SHORTCUTS_FILE.read_text())
        except Exception:
            return []

    @staticmethod
    def _write_shortcuts(shortcuts):
        Backend._SHORTCUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        Backend._SHORTCUTS_FILE.write_text(json.dumps(shortcuts, indent=2))
        lines = []
        for s in shortcuts:
            lines.append(f'"{s["command"]}"')
            lines.append(f'    {s["keys"]}')
            lines.append("")
        Backend._XBINDKEYSRC.write_text("\n".join(lines))
        # xbindkeys re-reads its config on SIGHUP if already running; if this
        # is the first shortcut added this session, start it -- it
        # daemonizes itself by default, same as its autostart entry does.
        if subprocess.run(["pkill", "-HUP", "-x", "xbindkeys"], capture_output=True).returncode != 0:
            subprocess.run(["xbindkeys"], capture_output=True)

    @Slot()
    def listCustomShortcuts(self):
        self.customShortcutsListed.emit(Backend._load_shortcuts())

    @Slot(str, str)
    def addCustomShortcut(self, keys, command):
        def task(emit):
            # Reassigning keys/command here (even to their own .strip()'d
            # values) makes Python treat them as locals to this closure --
            # shadowing the enclosing addCustomShortcut() parameters -- and
            # UnboundLocalError's on the read side of that same assignment.
            # Confirmed live: caught by actually clicking "Add" in the
            # running app, not by reading the code.
            k, c = keys.strip(), command.strip()
            if not k or not c:
                return False, "Enter both a key combo and a command."
            shortcuts = Backend._load_shortcuts()
            shortcuts.append({"keys": k, "command": c})
            Backend._write_shortcuts(shortcuts)
            return True, f"Shortcut added: {k} → {c}"
        self._run_action(task)

    @Slot(int)
    def removeCustomShortcut(self, index):
        def task(emit):
            shortcuts = Backend._load_shortcuts()
            if index < 0 or index >= len(shortcuts):
                return False, "Invalid shortcut."
            removed = shortcuts.pop(index)
            Backend._write_shortcuts(shortcuts)
            return True, f"Removed: {removed['keys']}"
        self._run_action(task)

    # --- Mouse -------------------------------------------------------------
    # KDE Plasma 6 stores pointer-device settings *per physical device*, not
    # in one flat [Mouse] group -- confirmed empirically on the dev VM by
    # changing System Settings' own Mouse KCM and diffing kcminputrc:
    # group "[Libinput][<vendorId>][<productId>][<device name>]", vendor/
    # product as *decimal* (kernel's /proc/bus/input/devices reports them in
    # hex -- 0x627 there is the "1575" in the config group). Assuming a
    # single global [Mouse] group here (the first draft, before checking)
    # would have silently written to a group nothing ever reads.

    @Slot(result=int)
    def mouseCursorSize(self):
        try:
            out = subprocess.check_output(
                ["kreadconfig6", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorSize"],
                text=True, timeout=2,
            ).strip()
            size = int(out) if out else 24
            return size if size in (24, 32, 48, 64) else 24
        except Exception:
            return 24

    @Slot(int)
    def setMouseCursorSize(self, size):
        if size not in (24, 32, 48, 64):
            self.actionFinished.emit(False, "Choose a supported cursor size.")
            return

        def task(emit):
            saved = subprocess.run(
                ["kwriteconfig6", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorSize", str(size)],
                capture_output=True, text=True, timeout=5,
            ).returncode == 0
            if not saved:
                return False, "Could not save the cursor size."

            # plasma-apply-cursortheme <current theme> --size N is a silent
            # no-op: it prints "already set" and exits 0 without touching the
            # size, and the theme is always already set (applyLook() does
            # that). So this used to report success while nothing changed.
            # Broadcast the same CursorChanged (5) notice the cursor KCM
            # sends after writing kcminputrc -- confirmed live on the Dev VM
            # to resize the pointer immediately, 24 -> 64 and back.
            notified = subprocess.run(
                ["dbus-send", "--session", "--type=signal", "/KGlobalSettings",
                 "org.kde.KGlobalSettings.notifyChange", "int32:5", "int32:0"],
                capture_output=True, text=True, timeout=5,
            ).returncode == 0
            return True, (f"Cursor size set to {size} px." if notified else f"Cursor size saved as {size} px; it will apply at next login.")
        self._run_action(task)

    @staticmethod
    def _pointer_devices():
        try:
            text = Path("/proc/bus/input/devices").read_text()
        except Exception:
            return []
        devices = []
        for block in text.split("\n\n"):
            if "Handlers=" not in block or "mouse" not in block:
                continue
            vendor = product = None
            name = None
            for line in block.splitlines():
                if line.startswith("I:"):
                    m = re.search(r"Vendor=([0-9a-fA-F]+) Product=([0-9a-fA-F]+)", line)
                    if m:
                        vendor, product = int(m.group(1), 16), int(m.group(2), 16)
                elif line.startswith("N:"):
                    m = re.search(r'Name="(.*)"', line)
                    if m:
                        name = m.group(1)
            if vendor is not None and name:
                devices.append({"vendor": vendor, "product": product, "name": name})
        return devices

    @staticmethod
    def _libinput_group_args(vendor, product, name):
        return ["--group", "Libinput", "--group", str(vendor), "--group", str(product), "--group", name]

    @staticmethod
    def _kreadconfig_libinput(vendor, product, name, key, default=""):
        try:
            out = subprocess.check_output(
                ["kreadconfig6", "--file", "kcminputrc"] + Backend._libinput_group_args(vendor, product, name) + ["--key", key],
                text=True,
            ).strip()
            return out if out else default
        except Exception:
            return default

    @staticmethod
    def _xinput_device_id(name):
        # X11-session live-apply path. Match by device name against the
        # "slave  pointer" rows only -- xinput also lists a master pointer +
        # XTEST virtual device that can share/contain the same name
        # substring.
        try:
            out = subprocess.check_output(["xinput", "list"], text=True)
        except Exception:
            return None
        for line in out.splitlines():
            if "slave  pointer" in line and name in line:
                m = re.search(r"id=(\d+)", line)
                if m:
                    return m.group(1)
        return None

    @staticmethod
    def _xinput_set(name, prop, value):
        dev_id = Backend._xinput_device_id(name)
        if dev_id is None:
            return False
        r = subprocess.run(["xinput", "set-prop", dev_id, prop, value], capture_output=True)
        return r.returncode == 0

    @staticmethod
    def _kwin_input_device_path(name):
        # Wayland-session live-apply path. Confirmed empirically on the dev
        # VM (busctl introspect + a live qdbus6 Set/Get round trip, not
        # guessed): under a real KWin Wayland session, KWin owns libinput
        # directly and exposes every device on the session bus at
        # org.kde.KWin's /org/kde/KWin/InputDevice/<eventN>, each with
        # writable leftHanded/naturalScroll/pointerAcceleration properties
        # that apply immediately -- this is what real System Settings'
        # Mouse KCM itself talks to under Wayland. xinput (above) can't see
        # real per-device names here at all -- Xwayland only exposes a
        # single synthetic multiplexed pointer, confirmed live the same way
        # (a toggle silently matched nothing).
        try:
            paths = subprocess.check_output(["qdbus6", "org.kde.KWin"], text=True).splitlines()
        except Exception:
            return None
        for path in paths:
            path = path.strip()
            if not path.startswith("/org/kde/KWin/InputDevice/"):
                continue
            try:
                dev_name = subprocess.check_output(
                    ["qdbus6", "org.kde.KWin", path, "org.freedesktop.DBus.Properties.Get",
                     "org.kde.KWin.InputDevice", "name"], text=True,
                ).strip()
            except Exception:
                continue
            if dev_name == name:
                return path
        return None

    @staticmethod
    def _kwin_input_set(name, prop, value):
        path = Backend._kwin_input_device_path(name)
        if path is None:
            return False
        r = subprocess.run(
            ["qdbus6", "org.kde.KWin", path, "org.freedesktop.DBus.Properties.Set",
             "org.kde.KWin.InputDevice", prop, value],
            capture_output=True,
        )
        return r.returncode == 0

    @staticmethod
    def _live_mouse_set(name, kwin_prop, kwin_value, xinput_prop, xinput_value):
        # Try the Wayland path first (this project's actual default session
        # -- see bugs.md), fall back to X11/xinput; if neither matches, the
        # setting still persisted to kcminputrc just above and takes effect
        # at next login.
        if Backend._kwin_input_set(name, kwin_prop, kwin_value):
            return True
        return Backend._xinput_set(name, xinput_prop, xinput_value)

    @Slot()
    def refreshMouseInfo(self):
        def compute():
            devices = []
            for d in Backend._pointer_devices():
                v, p, n = d["vendor"], d["product"], d["name"]
                accel = Backend._kreadconfig_libinput(v, p, n, "PointerAcceleration", "0")
                try:
                    accel_f = float(accel)
                except ValueError:
                    accel_f = 0.0
                devices.append({
                    "vendor": v, "product": p, "name": n,
                    "leftHanded": Backend._kreadconfig_libinput(v, p, n, "LeftHanded", "false") == "true",
                    "naturalScroll": Backend._kreadconfig_libinput(v, p, n, "NaturalScroll", "false") == "true",
                    "pointerAcceleration": accel_f,
                })
            return {"devices": devices}
        self._mouse_worker = InfoWorker(compute)
        self._mouse_worker.ready.connect(self.mouseInfoReady.emit)
        self._mouse_worker.start()

    @Slot(int, int, str, bool)
    def setMouseLeftHanded(self, vendor, product, name, enabled):
        def task(emit):
            subprocess.run(
                ["kwriteconfig6", "--file", "kcminputrc"] + Backend._libinput_group_args(vendor, product, name)
                + ["--key", "LeftHanded", "true" if enabled else "false"],
            )
            live = Backend._live_mouse_set(
                name, "leftHanded", "true" if enabled else "false",
                "libinput Left Handed Enabled", "1" if enabled else "0",
            )
            return True, ("Left-handed mode applied." if live else "Saved (takes effect next login -- live apply needs this device to be reachable via KWin or xinput).")
        self._run_action(task)

    @Slot(int, int, str, bool)
    def setMouseNaturalScroll(self, vendor, product, name, enabled):
        def task(emit):
            subprocess.run(
                ["kwriteconfig6", "--file", "kcminputrc"] + Backend._libinput_group_args(vendor, product, name)
                + ["--key", "NaturalScroll", "true" if enabled else "false"],
            )
            live = Backend._live_mouse_set(
                name, "naturalScroll", "true" if enabled else "false",
                "libinput Natural Scrolling Enabled", "1" if enabled else "0",
            )
            return True, ("Natural scrolling applied." if live else "Saved (takes effect next login -- live apply needs this device to be reachable via KWin or xinput).")
        self._run_action(task)

    @Slot(int, int, str, float)
    def setMousePointerAcceleration(self, vendor, product, name, value):
        def task(emit):
            subprocess.run(
                ["kwriteconfig6", "--file", "kcminputrc"] + Backend._libinput_group_args(vendor, product, name)
                + ["--key", "PointerAcceleration", f"{value:.3f}"],
            )
            # Both KWin's own "pointerAcceleration" property and libinput's
            # "Accel Speed" xinput property use the same -1..1 range our
            # slider already does -- no unit conversion needed either way
            # (confirmed live: KWin's reported value already matched the
            # slider's kcminputrc-persisted value before any change).
            live = Backend._live_mouse_set(
                name, "pointerAcceleration", f"{value:.3f}",
                "libinput Accel Speed", f"{value:.3f}",
            )
            return True, ("Pointer speed applied." if live else "Saved (takes effect next login -- live apply needs this device to be reachable via KWin or xinput).")
        self._run_action(task)

    # -- printers & scanners ----------------------------------------------

    @Slot()
    def refreshPrinters(self):
        def task():
            # lpstat translates its output ("la impresora X está inactiva"),
            # so read it in the C locale. A printer that is printing or
            # disabled has no "is <state>" in its line ("printer X now
            # printing X-1." / "printer X disabled since ...") -- matching
            # only "is" dropped it from the list right after adding it.
            result = subprocess.run(["lpstat", "-p"], capture_output=True, text=True, env=_C_LOCALE)
            default_result = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, env=_C_LOCALE)
            default_name = default_result.stdout.rsplit(":", 1)[-1].strip() if ":" in default_result.stdout else ""
            printers = []
            for line in result.stdout.splitlines():
                m = re.match(r"printer (\S+) (?:is (.+?)\.|(now printing)|(disabled))", line)
                if m:
                    status = m.group(2) or ("printing" if m.group(3) else "disabled")
                    printers.append({
                        "name": m.group(1),
                        "status": status,
                        "isDefault": m.group(1) == default_name,
                    })
            return printers
        self._printer_list_worker = ListWorker(task)
        self._printer_list_worker.ready.connect(self.printersListed.emit)
        self._printer_list_worker.start()

    @Slot()
    def discoverPrinterDevices(self):
        # `lpinfo -v` also probes the network (mDNS/IPP), so this can take
        # several seconds -- always the async ListWorker, never a plain
        # synchronous @Slot(result=...), so it doesn't freeze the page.
        def task():
            result = subprocess.run(["lpinfo", "-v"], capture_output=True, text=True, timeout=20)
            configured = subprocess.run(["lpstat", "-v"], capture_output=True, text=True)
            already = {line.rsplit(" ", 1)[-1].strip() for line in configured.stdout.splitlines() if ":" in line}
            devices = []
            for line in result.stdout.splitlines():
                parts = line.strip().split(" ", 1)
                # `lpinfo -v` always lists the bare backend schemes it has
                # available (e.g. "network http", "network beh") even with
                # zero real printers found -- those aren't addressable
                # devices (no host/path), just driver capabilities, and
                # `lpadmin -v http -m everywhere` would fail if "added".
                # A genuine discovered device's URI always has "://".
                if len(parts) == 2 and "://" in parts[1] and parts[1] not in already:
                    devices.append({"kind": parts[0], "uri": parts[1]})
            return devices
        self._printer_device_worker = ListWorker(task)
        self._printer_device_worker.ready.connect(self.printerDevicesFound.emit)
        self._printer_device_worker.start()

    @Slot(str, str)
    def addPrinter(self, name, uri):
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name or ""):
            self.actionFinished.emit(False, "Printer name can only contain letters, numbers, - and _")
            return

        def task(emit):
            # `-m everywhere` uses IPP Everywhere / driverless printing --
            # works for the large majority of printers made since ~2015
            # without needing to locate and install a vendor PPD/driver.
            result = subprocess.run(
                ["sudo", "-n", REYOS_ADMIN, "printer", "add", name, uri],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f'"{name}" added.'
            return False, (result.stderr.strip() or "Could not add that printer.")
        self._run_action(task)

    @Slot(str)
    def removePrinter(self, name):
        def task(emit):
            result = subprocess.run(["sudo", "-n", REYOS_ADMIN, "printer", "remove", name], capture_output=True, text=True)
            if result.returncode == 0:
                return True, f'"{name}" removed.'
            return False, (result.stderr.strip() or "Could not remove that printer.")
        self._run_action(task)

    @Slot(str)
    def setDefaultPrinter(self, name):
        def task(emit):
            result = subprocess.run(["sudo", "-n", REYOS_ADMIN, "printer", "default", name], capture_output=True, text=True)
            if result.returncode == 0:
                return True, f'"{name}" set as default.'
            return False, (result.stderr.strip() or "Could not set the default printer.")
        self._run_action(task)

    @Slot(str)
    def testPrint(self, name):
        def task(emit):
            # Printing itself never needs root -- only lpadmin's
            # add/remove/set-default operations do.
            result = subprocess.run(
                ["lp", "-d", name, "/usr/share/cups/data/testprint"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f"Test page sent to \"{name}\"."
            return False, (result.stderr.strip() or "Could not send the test page.")
        self._run_action(task)

    @Slot()
    def refreshScanners(self):
        def task():
            result = subprocess.run(["scanimage", "-L"], capture_output=True, text=True, timeout=20, env=_C_LOCALE)
            scanners = []
            for line in result.stdout.splitlines():
                m = re.match(r"device `([^']+)' is (.+)", line)
                if m:
                    scanners.append({"device": m.group(1), "label": m.group(2)})
            return scanners
        self._scanner_list_worker = ListWorker(task)
        self._scanner_list_worker.ready.connect(self.scannersListed.emit)
        self._scanner_list_worker.start()

    @Slot(str)
    def scanTestPage(self, device):
        def task(emit):
            out_dir = Path.home() / "Pictures"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"scan-{time.strftime('%Y%m%d-%H%M%S')}.png"
            result = subprocess.run(
                ["scanimage", "--device", device, "--format=png", "-o", str(out_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return True, f"Scanned to {out_path}"
            return False, (result.stderr.strip() or "Could not scan from that device.")
        self._run_action(task)


def main():
    # Kept for anything still calling main.py --reapply-look; the login
    # script itself runs the Qt-free looks.py directly.
    if "--reapply-look" in sys.argv:
        import looks
        looks.main()
        return
    if setproctitle is not None:
        setproctitle.setproctitle("reyos-control-center")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Control Center")
    app.setDesktopFileName("reyos-control-center")
    engine = QQmlApplicationEngine()

    backend = Backend()
    app.aboutToQuit.connect(backend.stopStatsWorker)
    app.aboutToQuit.connect(Backend._bt_stop_scan)
    backend.actionFinished.connect(lambda ok, msg: _log_failure("action", ok, msg))
    backend.pkgFinished.connect(lambda ok, msg: _log_failure("package", ok, msg + f" (output: {PKG_LOG})"))
    backend.gamingFinished.connect(lambda ok, msg: _log_failure("gaming", ok, msg))
    app.aboutToQuit.connect(backend.cancelControllerSetup)
    # A package update still running when the window closes finishes first.
    app.aboutToQuit.connect(_THREADS.wait_all)
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("reyosAccentColor", _reyos_accent_color())
    # Lets launchers (e.g. ReyOS Welcome's "Check for Updates" button) open
    # straight to a specific page instead of always landing on System Info.
    engine.rootContext().setContextProperty(
        "initialPage", os.environ.get("REYOS_CC_INITIAL_PAGE", "SystemInfoPage.qml")
    )

    qml_file = APP_DIR / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        sys.exit(1)

    window = engine.rootObjects()[0]
    window.setIcon(QIcon.fromTheme("reyos-control-center"))

    def try_activate(remaining=6):
        window.raise_()
        window.requestActivate()
        if remaining > 0:
            QTimer.singleShot(300, lambda: try_activate(remaining - 1))

    QTimer.singleShot(200, try_activate)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
