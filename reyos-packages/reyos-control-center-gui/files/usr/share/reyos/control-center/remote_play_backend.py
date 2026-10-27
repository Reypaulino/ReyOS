"""The Qt side of Remote Play (remote_play.py), shared by Control Center's
Gaming page and ReyOS Games: both register a RemotePlayBackend as
`remotePlay` and use qml/RemotePlayPanel.qml. Slow calls run off the window's
thread; results come back as signals."""
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QGuiApplication

import remote_play

REYOS_ADMIN = "/usr/share/reyos/bin/reyos-admin"


def _live_session():
    try:
        cmdline = Path("/proc/cmdline").read_text()
    except OSError:
        return False
    return "archisobasedir=" in cmdline or "archisolabel=" in cmdline


def _ufw_status():
    try:
        return subprocess.run(["sudo", "-n", REYOS_ADMIN, "firewall", "status"], capture_output=True,
                              text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


class _Job(QThread):
    done = Signal("QVariant")
    progress = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception as e:  # shown to the user, never a crash
            self.done.emit((False, str(e)))


class RemotePlayBackend(QObject):
    statusReady = Signal("QVariantMap")
    pairingsReady = Signal("QVariantList", "QVariantList", str)  # pending, paired, error
    busyChanged = Signal(bool)
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs = []
        self._busy = False
        self._polling = None

    def _start(self, fn, then):
        job = _Job(fn)
        job.done.connect(then)
        job.progress.connect(self.progress.emit)
        # Kept until finished: a collected QThread that's still running aborts.
        self._jobs = [j for j in self._jobs if j.isRunning()] + [job]
        job.start()

    def _action(self, fn):
        if self._busy:
            self.finished.emit(False, "Still working on the last step, one moment.")
            return
        self._busy = True
        self.busyChanged.emit(True)
        self._start(fn, self._action_done)

    def _action_done(self, result):
        self._busy = False
        self.busyChanged.emit(False)
        ok, message = result
        self.finished.emit(ok, message)
        self.refresh()

    @Slot(result=bool)
    def busy(self):
        return self._busy

    @Slot()
    def refresh(self):
        self._start(lambda emit: remote_play.status(_ufw_status()), self.statusReady.emit)

    @Slot()
    def install(self):
        if _live_session():
            self.finished.emit(False, "Remote Play can't be installed in the live session: install ReyOS first.")
            return

        def task(emit):
            pkgs = remote_play.packages()
            emit("Installing " + ", ".join(pkgs) + " with any waiting system updates...")
            proc = subprocess.Popen(["sudo", "-n", REYOS_ADMIN, "install-apps", *pkgs], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                emit(line.rstrip())
            if proc.wait() != 0:
                return False, "Install failed: check your network connection and try again."
            remote_play.save_settings({"show_in_games": remote_play.load_settings().get("show_in_games", True)})
            remote_play.set_up()
            return True, "Remote Play is installed. Press Turn on when you want to stream."
        self._action(task)

    @Slot()
    def turnOn(self):
        self._action(lambda emit: remote_play.start())

    @Slot()
    def turnOff(self):
        self._action(lambda emit: remote_play.stop())

    @Slot(bool)
    def setStartsAtLogin(self, on):
        self._action(lambda emit: remote_play.set_starts_at_login(on))

    @Slot(bool)
    def allowNetwork(self, on):
        """Lets Moonlight through the firewall (home networks and Tailscale)
        or closes it again. Opening asks for the password."""
        def task(emit):
            cmd = (["pkexec", REYOS_ADMIN, "remote-play-firewall", "on"] if on
                   else ["sudo", "-n", REYOS_ADMIN, "remote-play-firewall", "off"])
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode in (126, 127) and on:
                return False, "Not changed: the password window was closed."
            if result.returncode != 0:
                return False, "The firewall didn't change: " + (result.stderr.strip() or "ufw failed")
            return True, ("Devices on your home network and Tailscale can now reach Remote Play. "
                          "They still need your PIN to pair." if on
                          else "The firewall blocks Remote Play again.")
        self._action(task)

    @Slot(bool)
    def setShowInGames(self, on):
        remote_play.save_settings({"show_in_games": bool(on)})
        self.refresh()

    @Slot(result=bool)
    def showInGames(self):
        return remote_play.show_in_games()

    @Slot()
    def loadPairings(self):
        """Pending requests and paired devices; quietly empty when Sunshine
        is off."""
        def task(emit):
            if not remote_play.installed() or not remote_play.running():
                return [], [], ""
            try:
                return remote_play.pending_pairings(), remote_play.paired_devices(), ""
            except remote_play.ApiError as e:
                return [], [], str(e)
        # A failed job comes back as (False, message) instead of three items.
        self._start(task, lambda r: self.pairingsReady.emit(*r) if len(r) == 3 else
                    self.pairingsReady.emit([], [], r[1]))

    @Slot(str, str, str)
    def pair(self, pairing_id, pin, name):
        def task(emit):
            emit("Waiting for Moonlight to finish pairing...")
            return remote_play.pair(pairing_id, pin, name)
        self._action(task)

    @Slot(str)
    def decline(self, pairing_id):
        def task(emit):
            ok = remote_play.decline(pairing_id)
            return ok, "Pairing request declined." if ok else "That request had already ended."
        self._action(task)

    @Slot(str)
    def unpair(self, uuid):
        self._action(lambda emit: remote_play.unpair(uuid))

    @Slot()
    def openSettings(self):
        subprocess.Popen(["xdg-open", remote_play.API], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot(result=str)
    def loginName(self):
        return remote_play.credentials()[0]

    @Slot()
    def copyPassword(self):
        password = remote_play.credentials()[1]
        QGuiApplication.clipboard().setText(password)
        self.finished.emit(bool(password), "Password copied. Sign in as \"reyos\" in Sunshine's settings."
                           if password else "There's no password yet: press Turn on first.")

    @Slot()
    def copyDiagnostics(self):
        def task(emit):
            text = remote_play.diagnostics(_ufw_status())
            return True, text
        self._start(task, self._diagnostics_ready)

    def _diagnostics_ready(self, result):
        ok, text = result
        if ok:
            QGuiApplication.clipboard().setText(text)
            self.finished.emit(True, "Diagnostics copied: paste them into a message or a bug report.")
        else:
            self.finished.emit(False, text)
