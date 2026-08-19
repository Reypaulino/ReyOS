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
    "git": "git",
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
    # System-restore utility -- rsync-based snapshots work on any
    # filesystem (including the ext4 this image currently ships with);
    # switches to faster Btrfs-snapshot mode automatically if the target
    # is ever installed on Btrfs later, no reconfiguration needed.
    "timeshift": "timeshift",
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


class InstallWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(bool, str)

    def __init__(self, pacman_pkgs, flatpak_ids):
        super().__init__()
        self.pacman_pkgs = pacman_pkgs
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

            if self.pacman_pkgs:
                if "wine" in self.pacman_pkgs or "steam" in self.pacman_pkgs:
                    self._ensure_multilib()
                # The live session never runs `pacman -Sy` on its own, so the
                # sync databases don't exist yet — any -S install fails
                # outright (even for an already-installed package) until
                # this runs at least once.
                self.progress.emit("Syncing package databases...")
                self._run(["sudo", "pacman", "-Sy", "--noconfirm"])
                self.progress.emit(f"Installing: {self.pacman_pkgs}")
                rc = self._run(["sudo", "pacman", "-S", "--needed", "--noconfirm"] + self.pacman_pkgs.split())
                if rc != 0:
                    self.finished_ok.emit(False, "Package install failed — see log.")
                    return
                if "wine" in self.pacman_pkgs:
                    self._run(["sudo", "systemctl", "restart", "systemd-binfmt"])
                if "timeshift" in self.pacman_pkgs:
                    # Baseline safety-net snapshot right after install, not
                    # left fully manual -- --scripted skips Timeshift's
                    # interactive first-run wizard; with no existing config
                    # it defaults to rsync mode, which works on any
                    # filesystem (this image ships ext4).
                    self.progress.emit("Creating initial Timeshift snapshot...")
                    self._run(["sudo", "timeshift", "--create", "--scripted",
                               "--comments", "ReyOS factory default"])

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
            subprocess.run(
                ["sudo", "sed", "-i", "/^#\\[multilib\\]/,/^#Include/ s/^#//", "/etc/pacman.conf"],
                check=False,
            )
            # The unconditional -Sy right after this call in run() picks up
            # the newly-enabled repo, so no separate sync needed here.


class Backend(QObject):
    progressLine = Signal(str)
    installFinished = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._worker = None

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
        pacman_pkgs = " ".join(APP_PACMAN[a] for a in appIds if a in APP_PACMAN)
        flatpak_ids = " ".join(APP_FLATPAK[a] for a in appIds if a in APP_FLATPAK)

        if not pacman_pkgs and not flatpak_ids:
            self.installFinished.emit(True, "Nothing selected — skipped.")
            return

        self._worker = InstallWorker(pacman_pkgs, flatpak_ids)
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


def apply_branding_on_exit():
    # Keep this detached so Welcome can close promptly, but preserve stdout
    # and stderr. A failed branding run is otherwise invisible to the user
    # and impossible to diagnose after the Welcome window has exited.
    customization_request = Path.home() / ".config" / "reyos-kde-customization-requested"
    command = ["/usr/share/reyos/bin/reyos-apply-branding.sh"]
    if customization_request.exists():
        command = ["/bin/bash", "-c", "/usr/share/reyos/bin/reyos-apply-branding.sh && /usr/share/reyos/kde/reyos-apply-customization.sh && rm -f ~/.config/reyos-kde-customization-requested"]
    log_path = Path.home() / ".cache" / "reyos" / "welcome-branding.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as log:
        log.write(f"\n=== branding requested {datetime.now().isoformat(timespec="seconds")} ===\n")
        log.flush()
        subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)

def main():
    # The live ISO opens Calamares only; Welcome is for the installed desktop.
    if Path("/run/archiso/airootfs").is_mount():
        return

    # Only runs automatically once — after this, it's launched manually from the app menu.
    autostart_file = Path.home() / ".config" / "autostart" / "reyos-welcome-autostart.desktop"
    autostart_file.unlink(missing_ok=True)
    hide_panels_on_start()

    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Welcome")
    # Was previously a separate autostart entry racing against this app for
    # the same Plasma config file — confirmed source of the panel/shortcuts
    # clobbering bugs. Triggering it only once Welcome actually closes
    # (Skip, Finish, or the window's own close button all fire this)
    # removes the concurrency instead of surviving it.
    app.aboutToQuit.connect(apply_branding_on_exit)
    engine = QQmlApplicationEngine()

    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)

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
