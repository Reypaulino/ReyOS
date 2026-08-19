#!/usr/bin/env python3
import glob
import grp
import json
import os
import pwd
import re
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QThread, QUrl, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

APP_DIR = Path(__file__).resolve().parent

PKG_ACTIONS = {
    "check":   (["sudo", "pacman", "-Sy"], None),
    "upgrade": (["sudo", "pacman", "-Su", "--noconfirm"], None),
    # "full" and "clean" are handled specially in PkgWorker (multiple commands).
    "full":    (None, None),
    "clean":   (None, None),
}


def _is_live_session():
    return os.path.ismount("/run/archiso/airootfs")


def _run(cmd, progress_emit=None):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    for line in proc.stdout:
        if progress_emit:
            progress_emit(line.rstrip())
    return proc.wait()


def _purge_stale_download_sandboxes():
    # pacman's download sandboxing (the unprivileged `alpm` user) makes a
    # per-download temp dir under the cache and removes it when the download
    # finishes -- an interrupted/killed pacman run (network drop, a session
    # dying mid-transaction) can leave one behind. `pacman -Sc` then tries to
    # open every entry in the cache dir as a package file and fails loudly on
    # each leftover directory ("could not open file ... Error reading fd 7"),
    # which reads as a real error even though it's just cache noise. These
    # accumulate silently over time, so sweep them before every cache clean.
    subprocess.run(
        ["sudo", "find", "/var/cache/pacman/pkg", "-mindepth", "1", "-maxdepth", "1",
         "-type", "d", "-name", "download-*", "-exec", "rm", "-rf", "{}", "+"],
        capture_output=True,
    )


class StatsWorker(QThread):
    statsReady = Signal("QVariantMap")

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def _cpu_times(self):
        with open("/proc/stat") as f:
            parts = f.readline().split()
        return list(map(int, parts[1:8]))

    def run(self):
        while not self._stop:
            t1 = self._cpu_times()
            time.sleep(0.2)
            if self._stop:
                break
            t2 = self._cpu_times()
            total1, total2 = sum(t1), sum(t2)
            idle1, idle2 = t1[3], t2[3]
            denom = (total2 - total1) or 1
            cpu_pct = round((1 - (idle2 - idle1) / denom) * 100, 1)

            mem_total = mem_used = swap_total = swap_used = 0
            try:
                out = subprocess.check_output(["free", "-m"], text=True)
                for line in out.splitlines():
                    if line.startswith("Mem:"):
                        parts = line.split()
                        mem_total, mem_used = int(parts[1]), int(parts[2])
                    elif line.startswith("Swap:"):
                        parts = line.split()
                        swap_total, swap_used = int(parts[1]), int(parts[2])
            except Exception:
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
                swap_on = subprocess.run(
                    ["swapon", "--show"], capture_output=True, text=True
                ).stdout.strip()
                swap_status = "ON" if swap_on else "OFF"
            except Exception:
                swap_status = "OFF"

            try:
                uptime = subprocess.check_output(["uptime", "-p"], text=True).strip()
                uptime = uptime.removeprefix("up ")
            except Exception:
                uptime = "N/A"

            self.statsReady.emit({
                "cpu": cpu_pct,
                "memUsed": mem_used, "memTotal": mem_total, "memPct": mem_pct,
                "swapUsed": swap_used, "swapTotal": swap_total, "swapStatus": swap_status,
                "governor": governor, "swappiness": swappiness, "uptime": uptime,
            })

            for _ in range(9):
                if self._stop:
                    break
                time.sleep(0.2)


class PkgWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(bool, str)

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        try:
            emit = self.progress.emit
            if self.action in ("upgrade", "full", "clean") and _is_live_session():
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
                emit("$ sudo pacman -Syu")
                rc = _run(["sudo", "pacman", "-Syu"], emit)
                self.finished_ok.emit(rc == 0, "Updates installed." if rc == 0 else "Update failed.")
            elif self.action == "full":
                emit("[1/3] Syncing + upgrading...")
                rc = _run(["sudo", "pacman", "-Syu", "--noconfirm"], emit)
                if rc != 0:
                    self.finished_ok.emit(False, "Full update failed.")
                    return
                emit("[2/3] Removing orphaned packages...")
                orphans = subprocess.run(
                    ["pacman", "-Qtdq"], capture_output=True, text=True
                ).stdout.split()
                if orphans:
                    _run(["sudo", "pacman", "-Rns", "--noconfirm"] + orphans, emit)
                _purge_stale_download_sandboxes()
                _run(["sudo", "pacman", "-Sc", "--noconfirm"], emit)
                emit("[3/3] Flatpak update...")
                _run(["flatpak", "update", "-y"], emit)
                self.finished_ok.emit(True, "Full update complete.")
            elif self.action == "clean":
                orphans = subprocess.run(
                    ["pacman", "-Qtdq"], capture_output=True, text=True
                ).stdout.split()
                if orphans:
                    emit("Removing: " + " ".join(orphans))
                    _run(["sudo", "pacman", "-Rns", "--noconfirm"] + orphans, emit)
                else:
                    emit("No orphaned packages.")
                _purge_stale_download_sandboxes()
                _run(["sudo", "pacman", "-Sc", "--noconfirm"], emit)
                self.finished_ok.emit(True, "Cache cleaned.")
        except Exception as e:
            self.finished_ok.emit(False, str(e))


class ActionWorker(QThread):
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


class InfoWorker(QThread):
    ready = Signal("QVariantMap")

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.ready.emit(self.fn())


class ListWorker(QThread):
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
    orphansListed = Signal("QVariantList")
    actionFinished = Signal(bool, str)
    imageSelected = Signal(str)
    pathBrowsed = Signal(str, str)
    networkInfoReady = Signal("QVariantMap")
    diskInfoReady = Signal("QVariantMap")
    aboutInfoReady = Signal("QVariantMap")
    driverStatusReady = Signal("QVariantMap")
    firewallStatusReady = Signal("QVariantMap")
    usersListed = Signal("QVariantList")
    packagesFound = Signal("QVariantList")
    packageInfoReady = Signal(str, str)
    flatpaksListed = Signal("QVariantList")
    servicesFound = Signal("QVariantList")
    autostartListed = Signal("QVariantList")
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

    @Slot()
    def openTimeshift(self):
        try:
            subprocess.Popen(["timeshift-launcher"])
        except FileNotFoundError:
            self.actionFinished.emit(False, "Timeshift is not installed yet. Reboot into the next ReyOS ISO build.")

    def stopStatsWorker(self):
        self._stats_worker.stop()
        self._stats_worker.wait(1000)

    @Slot(str)
    def runPkgAction(self, action):
        self._pkg_worker = PkgWorker(action)
        self._pkg_worker.progress.connect(self.pkgProgress.emit)
        self._pkg_worker.finished_ok.connect(self.pkgFinished.emit)
        self._pkg_worker.start()

    @Slot()
    def listOrphans(self):
        orphans = subprocess.run(
            ["pacman", "-Qtdq"], capture_output=True, text=True
        ).stdout.split()
        self.orphansListed.emit(orphans)

    def _run_action(self, fn):
        self._action_worker = ActionWorker(fn)
        self._action_worker.finished_ok.connect(self.actionFinished.emit)
        self._action_worker.start()

    @Slot(str)
    def setGovernor(self, gov):
        def task(emit):
            paths = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
            if not paths:
                return False, "No cpufreq scaling available on this system (common in VMs)."
            for p in paths:
                subprocess.run(["sudo", "tee", p], input=gov, capture_output=True, text=True)
            return True, f"Governor set to: {gov}"
        self._run_action(task)

    @Slot()
    def performanceMode(self):
        def task(emit):
            paths = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
            if paths:
                for p in paths:
                    subprocess.run(["sudo", "tee", p], input="performance", capture_output=True, text=True)
            subprocess.run(["sudo", "sysctl", "-w", "vm.swappiness=10"], capture_output=True)
            Backend._persist_swappiness(10)
            note = "" if paths else " (governor skipped — no cpufreq scaling on this system)"
            return True, f"Performance mode applied.{note} Swappiness → 10 (persists across reboots)."
        self._run_action(task)

    @staticmethod
    def _persist_swappiness(value):
        # `sysctl -w` only touches live kernel state -- write the same value to
        # a sysctl.d drop-in so it survives reboot instead of silently reverting
        # to the distro default.
        subprocess.run(
            ["sudo", "tee", "/etc/sysctl.d/99-reyos-swappiness.conf"],
            input=f"vm.swappiness={value}\n", capture_output=True, text=True,
        )

    @Slot(int)
    def setSwappiness(self, value):
        def task(emit):
            subprocess.run(["sudo", "sysctl", "-w", f"vm.swappiness={value}"], capture_output=True)
            Backend._persist_swappiness(value)
            return True, f"Swappiness set to: {value} (persists across reboots)"
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

    @Slot()
    def toggleSwap(self):
        def task(emit):
            swap_on = subprocess.run(
                ["swapon", "--show=NAME", "--noheadings"], capture_output=True, text=True
            ).stdout.strip()
            if swap_on:
                # swapoff -a only affects the running session -- systemd
                # regenerates the swap unit from fstab on every boot, so mask
                # it (an /etc/systemd/system mask always wins over that
                # generated unit) rather than editing fstab directly.
                units = [Backend._swap_unit_for_device(d) for d in swap_on.splitlines()]
                subprocess.run(["sudo", "swapoff", "-a"], capture_output=True)
                for unit in units:
                    if unit:
                        subprocess.run(["sudo", "systemctl", "mask", unit], capture_output=True)
                return True, "Swap disabled (stays off after reboot)."
            else:
                for unit in Backend._masked_swap_units():
                    subprocess.run(["sudo", "systemctl", "unmask", unit], capture_output=True)
                subprocess.run(["sudo", "swapon", "-a"], capture_output=True)
                return True, "Swap enabled."
        self._run_action(task)

    # plasma-apply-lookandfeel's KPackage lookup silently no-ops on our own
    # custom look-and-feel packages -- confirmed via kreadconfig6: rc=0, zero
    # stdout even under full Qt debug logging, no config change, even after
    # kbuildsycoca6 and a plasmashell restart. Works fine for stock org.kde.*
    # packages, so this only affects our own themes. Apply their constituent
    # pieces (colorscheme + icon theme + the bookkeeping key) directly instead.
    _REYOS_LOOKANDFEEL = {
        "org.reyos.desktop": ("ReyOS", "breeze-dark", None),
        "org.reyos.light.desktop": ("ReyOSLight", "breeze", None),
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
                colorscheme, icons, wallpaper = self._REYOS_LOOKANDFEEL[package_id]
                rc = subprocess.run(["plasma-apply-colorscheme", colorscheme]).returncode
                if wallpaper:
                    subprocess.run(["plasma-apply-wallpaperimage", wallpaper])
                subprocess.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "Icons", "--key", "Theme", icons])
                subprocess.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", "LookAndFeelPackage", package_id])
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
                return rc == 0, ("Look and feel applied; matching wallpaper set when available." if rc == 0 else "Failed to apply color scheme.")
            rc = subprocess.run(["plasma-apply-lookandfeel", "--apply", package_id]).returncode
            return rc == 0, ("Look and feel applied." if rc == 0 else "Failed to apply look and feel.")
        self._run_action(task)

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
        gpus = []
        try:
            out = subprocess.check_output(["lspci", "-k"], text=True)
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
                    low = desc.lower()
                    if "nvidia" in low:
                        vendor = "nvidia"
                    elif "amd" in low or "ati" in low or "radeon" in low:
                        vendor = "amd"
                    elif "intel" in low:
                        vendor = "intel"
                    else:
                        vendor = "other"
                    current = {"model": desc, "vendor": vendor, "driver": ""}
            elif current is not None:
                stripped = line.strip()
                if stripped.startswith("Kernel driver in use:"):
                    current["driver"] = stripped.split(":", 1)[1].strip()
        if current:
            gpus.append(current)

        # Open-source nouveau (or no driver bound at all) on real NVIDIA
        # hardware means 3D acceleration is either crippled or entirely
        # missing -- the single biggest "not actually ready to play" gap
        # on a fresh install, since ReyOS ships the open mesa/libglvnd
        # stack by default and never bundles NVIDIA's proprietary driver.
        needs_nvidia = any(
            g["vendor"] == "nvidia" and g["driver"] in ("nouveau", "")
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
            # nvidia-dkms rebuilds the module against whatever kernel is
            # currently installed automatically on every kernel update --
            # more maintenance-free than the plain `nvidia` package
            # (which is tied to one specific kernel package/version), and
            # ReyOS runs the standard `linux` kernel this ships against.
            result = subprocess.run(
                ["sudo", "pacman", "-S", "--noconfirm", "--needed", "nvidia-dkms", "nvidia-utils"],
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
                ["df", "-h", "--output=source,size,used,avail,pcent,target"], text=True
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
            rc = _run(["sudo", "pacman", "-Rns", "--noconfirm", pkgname], emit)
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
            rc = _run(["sudo", "systemctl", "start" if start else "stop", unit], emit)
            verb = "started" if start else "stopped"
            return rc == 0, (f"{unit}: {verb}." if rc == 0 else f"Failed to {'start' if start else 'stop'} {unit}.")
        self._run_action(task)

    @Slot(str, bool)
    def setServiceEnabled(self, unit, enable):
        def task(emit):
            rc = _run(["sudo", "systemctl", "enable" if enable else "disable", unit], emit)
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
                ["sudo", "ufw", "status", "verbose"], text=True, stderr=subprocess.STDOUT,
            )
        except Exception as e:
            return {"enabled": False, "rules": [], "error": str(e)}

        lines = out.splitlines()
        enabled = any(l.startswith("Status: active") for l in lines)
        default_line = next((l for l in lines if l.startswith("Default:")), "")

        rules = []
        try:
            numbered = subprocess.check_output(
                ["sudo", "ufw", "status", "numbered"], text=True, stderr=subprocess.STDOUT,
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
                subprocess.run(["sudo", "ufw", "allow", "22/tcp"], capture_output=True)
                note = " (SSH access on 22/tcp was kept open automatically.)"
            cmd = ["sudo", "ufw", "--force", "enable"] if enable else ["sudo", "ufw", "disable"]
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
            result = subprocess.run(["sudo", "ufw", verb, port], capture_output=True, text=True)
            ok = result.returncode == 0
            return ok, (f"Rule added: {verb} {port}" if ok else (result.stderr.strip() or result.stdout.strip() or "Failed to add rule."))
        self._run_action(task)

    @Slot(str)
    def removeFirewallRule(self, rule_num):
        def task(emit):
            result = subprocess.run(
                ["sudo", "ufw", "--force", "delete", rule_num], capture_output=True, text=True,
            )
            ok = result.returncode == 0
            return ok, (f"Rule {rule_num} removed." if ok else (result.stderr.strip() or "Failed to remove rule."))
        self._run_action(task)

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

    @staticmethod
    def _compute_autostart_list():
        d = Path.home() / ".config" / "autostart"
        if not d.is_dir():
            return []
        items = []
        for f in sorted(d.glob("*.desktop")):
            try:
                text = f.read_text()
            except Exception:
                continue
            name = f.stem
            is_enabled = True
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("Name=") and "[" not in line:
                    name = line.split("=", 1)[1]
                elif line in ("Hidden=true", "X-GNOME-Autostart-enabled=false"):
                    is_enabled = False
            items.append({"file": str(f), "name": name, "isEnabled": is_enabled})
        return items

    @Slot()
    def listAutostart(self):
        self._autostart_worker = ListWorker(self._compute_autostart_list)
        self._autostart_worker.ready.connect(self.autostartListed.emit)
        self._autostart_worker.start()

    @Slot(str, bool)
    def setAutostartEnabled(self, file_path, enable):
        def task(emit):
            p = Path(file_path)
            if not p.is_file():
                return False, f"File not found: {file_path}"
            lines = [l for l in p.read_text().splitlines()
                     if not l.strip().startswith("X-GNOME-Autostart-enabled=")]
            lines.append("X-GNOME-Autostart-enabled=" + ("true" if enable else "false"))
            p.write_text("\n".join(lines) + "\n")
            return True, (("Enabled: " if enable else "Disabled: ") + p.stem)
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

    @staticmethod
    def _compute_bluetooth_status():
        show = Backend._bt(["show"])
        if show is None or show.returncode != 0 or not show.stdout.strip():
            return {"hasAdapter": False, "powered": False, "devices": []}

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
                devices.append({"mac": mac, "name": name, "connected": connected, "paired": paired})

        return {"hasAdapter": True, "powered": powered, "devices": devices}

    @Slot()
    def refreshBluetoothStatus(self):
        self._bluetooth_worker = InfoWorker(self._compute_bluetooth_status)
        self._bluetooth_worker.ready.connect(self.bluetoothStatusReady.emit)
        self._bluetooth_worker.start()

    @Slot(bool)
    def setBluetoothPowered(self, on):
        def task(emit):
            result = Backend._bt(["power", "on" if on else "off"])
            ok = bool(result and result.returncode == 0)
            return ok, (("Bluetooth turned on." if on else "Bluetooth turned off.") if ok else "Failed -- is an adapter present?")
        self._run_action(task)

    @Slot()
    def scanBluetoothDevices(self):
        def task(emit):
            # `scan on` streams forever on its own -- the timeout wrapper
            # (longer here than other calls) is what actually bounds it, not
            # bluetoothctl itself.
            Backend._bt(["scan", "on"], timeout_s=8)
            return True, "Scan complete."
        self._run_action(task)

    @Slot(str)
    def pairBluetoothDevice(self, mac):
        def task(emit):
            pair = Backend._bt(["pair", mac], timeout_s=15)
            if not pair or pair.returncode != 0:
                return False, f"Failed to pair with {mac}."
            Backend._bt(["trust", mac])
            connect = Backend._bt(["connect", mac], timeout_s=10)
            ok = bool(connect and connect.returncode == 0)
            return True, (f"Paired and connected: {mac}" if ok else f"Paired but couldn't connect: {mac}")
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
                    parts = line.split(":")
                    if len(parts) < 4:
                        continue
                    in_use, ssid, signal = parts[0], parts[1], parts[2]
                    security = ":".join(parts[3:])
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
                parts = line.split(":")
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
                parts = line.split(":")
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
                ["sudo", "nmcli", "connection", "import", "type", "wireguard", "file", path],
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
            rc = subprocess.run(["sudo", "timedatectl", "set-timezone", tz], capture_output=True).returncode
            return rc == 0, (f"Timezone set to {tz}." if rc == 0 else "Failed to set timezone.")
        self._run_action(task)

    @Slot(bool)
    def setNtpEnabled(self, enable):
        def task(emit):
            rc = subprocess.run(
                ["sudo", "timedatectl", "set-ntp", "true" if enable else "false"], capture_output=True,
            ).returncode
            return rc == 0, (("Automatic time sync enabled." if enable else "Automatic time sync disabled.") if rc == 0 else "Failed to change NTP setting.")
        self._run_action(task)

    @Slot(str)
    def setManualDateTime(self, value):
        def task(emit):
            result = subprocess.run(["sudo", "timedatectl", "set-time", value], capture_output=True, text=True)
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


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Control Center")
    app.setDesktopFileName("reyos-control-center")
    engine = QQmlApplicationEngine()

    backend = Backend()
    app.aboutToQuit.connect(backend.stopStatsWorker)
    engine.rootContext().setContextProperty("backend", backend)
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
