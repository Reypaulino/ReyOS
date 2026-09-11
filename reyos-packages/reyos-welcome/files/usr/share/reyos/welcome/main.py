#!/usr/bin/env python3
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QThread, QUrl, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

APP_DIR = Path(__file__).resolve().parent
LOG_FILE = Path.home() / ".cache" / "reyos-welcome.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Per-app, not per-category — each checkbox in SoftwarePage.qml installs
# exactly one of these, not a whole bundle. IDs here must match the "id"
# fields in SoftwarePage.qml's groups model.
APP_PACMAN = {
    "steam": "steam",
    "lutris": "lutris",
    "retroarch": "retroarch",
    "perf-tools": "gamemode lib32-gamemode mangohud lib32-mangohud",
    "wine": "wine wine-mono wine-gecko winetricks",
    "docker": "docker",
    "neovim": "neovim",
    "base-devel": "base-devel",
    # Chrome itself is AUR-only (proprietary, not on Flathub or official repos) —
    # Chromium is the closest official-repo equivalent, same engine.
    "chromium": "chromium",
    "gimp": "gimp",
    "krita": "krita",
    "obs-studio": "obs-studio",
    # okular/gwenview (PDF+image viewing) already ship in the base image —
    # LibreOffice is the one genuinely heavy piece worth keeping opt-in.
    "libreoffice": "libreoffice-fresh",
    "btop": "btop",
    "partitionmanager": "partitionmanager",
    "fwupd": "fwupd",
    "filelight": "filelight",
    "bleachbit": "bleachbit",
}
APP_FLATPAK = {
    "vscode": "com.visualstudio.code",
    "brave": "com.brave.Browser",
    # Opera GX specifically is AUR-only (not on Flathub); regular Opera stands in for it.
    "opera": "com.opera.Opera",
}


class BrandingWorker(QThread):
    """Runs the same branding command apply_branding_on_exit used to fire
    detached — but synchronously, so the UI can show real progress instead
    of quitting instantly and leaving the user staring at a panel-less
    desktop for up to ~90s with no indication anything is happening."""
    finished_ok = Signal(bool, str)

    def run(self):
        customization_request = Path.home() / ".config" / "reyos-kde-customization-requested"
        command = ["/usr/share/reyos/bin/reyos-apply-branding.sh"]
        if customization_request.exists():
            command = ["/bin/bash", "-c",
                       "/usr/share/reyos/bin/reyos-apply-branding.sh && "
                       "/usr/share/reyos/kde/reyos-apply-customization.sh && "
                       "rm -f ~/.config/reyos-kde-customization-requested"]
        log_path = Path.home() / ".cache" / "reyos" / "welcome-branding.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as log:
            log.write(f"\n=== branding requested {datetime.now().isoformat(timespec='seconds')} ===\n")
            log.flush()
            rc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
        self.finished_ok.emit(rc == 0, "" if rc == 0 else "Desktop setup finished with warnings.")


class InstallWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(bool, str)

    def __init__(self, pacman_groups, flatpak_ids):
        super().__init__()
        self.pacman_groups = pacman_groups
        self.flatpak_ids = flatpak_ids

    def _run(self, cmd):
        self.progress.emit("$ " + " ".join(cmd))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        with LOG_FILE.open("a") as log:
            for line in proc.stdout:
                self.progress.emit(line.rstrip())
                log.write(line)
        return proc.wait()

    def run(self):
        try:
            with LOG_FILE.open("a") as log:
                log.write(f"\n=== ReyOS Welcome install run ===\n")

            if self.pacman_groups:
                joined = " ".join(self.pacman_groups)
                if "wine" in joined or "steam" in joined:
                    self._ensure_multilib()
                # The live session never runs `pacman -Sy` on its own, so the
                # sync databases don't exist yet — any -S install fails
                # outright (even for an already-installed package) until
                # this runs at least once.
                self.progress.emit("Syncing package databases...")
                self._run(["sudo", "pacman", "-Sy", "--noconfirm"])
                # One `pacman -S` call per selected app, not all combined into
                # one -- each call's argv then matches a fixed, individually
                # listed NOPASSWD sudoers line (see
                # shellprocess_sudoers_reyos_menu.conf) instead of an
                # unpredictable combined argv sudoers could never match.
                for group in self.pacman_groups:
                    self.progress.emit(f"Installing: {group}")
                    rc = self._run(["sudo", "pacman", "-S", "--needed", "--noconfirm"] + group.split())
                    if rc != 0:
                        self.finished_ok.emit(False, f"Package install failed ({group}) — see log.")
                        return
                if "wine" in joined:
                    self._run(["sudo", "systemctl", "restart", "systemd-binfmt"])

            if self.flatpak_ids:
                # A fresh user has no --user-scoped flathub remote yet, even
                # if flatpak itself is installed system-wide — confirmed bug:
                # "install --user flathub ..." fails outright with "No remote
                # refs found for 'flathub'" on a brand-new account. Each user
                # needs their own --user remote added once.
                self._run(["flatpak", "remote-add", "--user", "--if-not-exists",
                           "flathub", "https://flathub.org/repo/flathub.flatpakrepo"])
                self.progress.emit(f"Installing (Flatpak): {self.flatpak_ids}")
                rc = self._run(["flatpak", "install", "-y", "--user", "flathub"] + self.flatpak_ids.split())
                if rc != 0:
                    self.finished_ok.emit(False, "Flatpak install failed — see log.")
                    return

            self.finished_ok.emit(True, "All done!")
        except Exception as e:
            self.finished_ok.emit(False, str(e))

    def _ensure_multilib(self):
        conf = Path("/etc/pacman.conf").read_text()
        if "#[multilib]" in conf:
            self.progress.emit("Enabling multilib repository...")
            # Calls a fixed helper script (no arguments) instead of a raw
            # sed one-liner, since sed's own regex escaping plus sudoers'
            # glob metacharacters both fighting over the same `[`/`]`
            # characters made a hand-escaped sudoers rule too risky to get
            # right blind -- a wrong rule here breaks `visudo -c` for the
            # whole sudoers file, not just this one line.
            subprocess.run(
                ["sudo", "/usr/share/reyos/welcome/enable-multilib.sh"],
                check=False,
            )
            # The unconditional -Sy right after this call in run() picks up
            # the newly-enabled repo, so no separate sync needed here.


class Backend(QObject):
    progressLine = Signal(str)
    installFinished = Signal(bool, str)
    brandingFinished = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._worker = None
        self._branding_worker = None
        self.branding_started = False

    @Slot()
    def startBranding(self):
        # Idempotent -- both DonePage buttons call this, and the
        # aboutToQuit fallback (for someone who closes the window via the
        # X button instead) checks this flag before running its own
        # detached copy, so branding never runs twice.
        if self.branding_started:
            return
        self.branding_started = True
        self._branding_worker = BrandingWorker()
        self._branding_worker.finished_ok.connect(self.brandingFinished.emit)
        self._branding_worker.start()

    @Slot()
    def openDiscover(self):
        subprocess.Popen(["setsid", "plasma-discover"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @Slot()
    def openControlCenterUpdates(self):
        env = os.environ.copy()
        env["REYOS_CC_INITIAL_PAGE"] = "UpdatesPage.qml"
        # Avoid presenting a stale Control Center window when this action is used repeatedly.
        subprocess.run(["pkill", "-f", "python3 /usr/share/reyos/control-center/main.py"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(
            ["setsid", "python3", "/usr/share/reyos/control-center/main.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
        )

    @Slot(bool)
    def setKdeCustomization(self, enabled):
        request = Path.home() / ".config" / "reyos-kde-customization-requested"
        if enabled:
            request.parent.mkdir(parents=True, exist_ok=True)
            request.touch()
        else:
            request.unlink(missing_ok=True)

    @Slot(bool)
    def setPanelEditing(self, enabled):
        """Persist the user's explicit panel-editing choice for branding."""
        request = Path.home() / ".config" / "reyos-panel-editing-requested"
        if enabled:
            request.parent.mkdir(parents=True, exist_ok=True)
            request.touch()
        else:
            request.unlink(missing_ok=True)

    @Slot("QVariantList")
    def startInstall(self, appIds):
        # Kept as one group per selected app (not joined into a single
        # combined pacman call) so each `pacman -S` invocation's argv
        # matches one of the fixed, individually-listed NOPASSWD sudoers
        # lines Calamares writes for this user -- see
        # shellprocess_sudoers_reyos_menu.conf. A combined multi-app call
        # would produce an unpredictable argv sudoers could never match.
        pacman_groups = [APP_PACMAN[a] for a in appIds if a in APP_PACMAN]
        flatpak_ids = " ".join(APP_FLATPAK[a] for a in appIds if a in APP_FLATPAK)

        if not pacman_groups and not flatpak_ids:
            self.installFinished.emit(True, "Nothing selected — skipped.")
            return

        self._worker = InstallWorker(pacman_groups, flatpak_ids)
        self._worker.progress.connect(self.progressLine.emit)
        self._worker.finished_ok.connect(self.installFinished.emit)
        self._worker.start()


def hide_panels_on_start():
    # The default panel Plasma's own bootstrap created is still on screen
    # while Welcome runs (our real ReyOS panel only gets built by
    # apply_branding_on_exit) -- autohide it for a cleaner first-boot-into-
    # setup-wizard feel. No cleanup needed on exit: apply_panel_layout
    # unconditionally strips and replaces every panel containment anyway,
    # so whatever hiding state this leaves behind is discarded with it.
    subprocess.Popen(
        ["qdbus6", "org.kde.plasmashell", "/PlasmaShell",
         "org.kde.PlasmaShell.evaluateScript",
         'var p = panelIds(); for (i = 0; i < p.length; i++) { panelById(p[i]).hiding = "autohide"; }'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def apply_branding_on_exit(backend):
    # Fallback only, for a window closed via the X button (or anything else
    # that skips DonePage's buttons) rather than the normal Finish/Check-
    # for-Updates flow, which already runs branding synchronously with real
    # progress UI via Backend.startBranding(). Guarded by branding_started
    # so it never runs a second time on top of that.
    if backend.branding_started:
        return
    backend.branding_started = True
    customization_request = Path.home() / ".config" / "reyos-kde-customization-requested"
    command = ["/usr/share/reyos/bin/reyos-apply-branding.sh"]
    if customization_request.exists():
        command = ["/bin/bash", "-c", "/usr/share/reyos/bin/reyos-apply-branding.sh && /usr/share/reyos/kde/reyos-apply-customization.sh && rm -f ~/.config/reyos-kde-customization-requested"]
    log_path = Path.home() / ".cache" / "reyos" / "welcome-branding.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as log:
        log.write(f"\n=== branding requested {datetime.now().isoformat(timespec='seconds')} ===\n")
        log.flush()
        subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)

def _is_live_session():
    # /run/archiso/airootfs no longer exists on current archiso builds --
    # confirmed live (2026-08-31). Same fix as reyos-control-center-gui's
    # main.py: check the kernel cmdline's archiso parameters instead, the
    # actual stable marker mkarchiso sets for a live boot.
    try:
        cmdline = Path("/proc/cmdline").read_text()
    except OSError:
        return False
    return "archisobasedir=" in cmdline or "archisolabel=" in cmdline


def main():
    # The live ISO opens Calamares only; Welcome is for the installed desktop.
    if _is_live_session():
        return

    # Only runs automatically once — after this, it's launched manually from the app menu.
    autostart_file = Path.home() / ".config" / "autostart" / "reyos-welcome-autostart.desktop"
    autostart_file.unlink(missing_ok=True)
    hide_panels_on_start()

    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Welcome")
    engine = QQmlApplicationEngine()

    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    # Was previously a separate autostart entry racing against this app for
    # the same Plasma config file — confirmed source of the panel/shortcuts
    # clobbering bugs. Triggering it only once Welcome actually closes
    # removes the concurrency instead of surviving it. The normal Finish/
    # Check-for-Updates path already starts branding itself (with progress
    # UI) before quitting; this is just the fallback for an abrupt close.
    app.aboutToQuit.connect(lambda: apply_branding_on_exit(backend))

    qml_file = APP_DIR / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        sys.exit(1)

    # Launched via autostart with no window focus — the first click on any
    # window in that state gets consumed by the compositor just to raise/
    # focus it, never reaching the button underneath (reported as "have to
    # click Next twice"). An immediate requestActivate() right after load()
    # didn't fix it — plausibly too early (window not yet mapped by the
    # compositor) and/or Wayland's activation-token model blocking
    # self-activation for apps not launched through a token-granting path
    # (systemd autostart units don't grant one). Retry a few times on a
    # short delay via QTimer so the loop is running and the window has had
    # a chance to actually map before each attempt.
    window = engine.rootObjects()[0]
    # Kirigami.ApplicationWindow has no assignable "icon" property in QML
    # (confirmed: "Cannot assign to non-existent property" at load time) --
    # setting it via the underlying QWindow API works instead.
    window.setIcon(QIcon.fromTheme("reyos-logo"))

    def try_activate(remaining=6):
        window.raise_()
        window.requestActivate()
        if remaining > 0:
            QTimer.singleShot(300, lambda: try_activate(remaining - 1))

    QTimer.singleShot(200, try_activate)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
