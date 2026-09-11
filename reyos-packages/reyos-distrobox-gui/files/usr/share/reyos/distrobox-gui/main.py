#!/usr/bin/env python3
"""ReyOS Distrobox GUI -- a native front-end for the `distrobox` CLI.

Wraps container lifecycle (create/list/enter/stop/delete) and app export
into the host launcher, so a user never has to touch a terminal for the
common cases. Distrobox itself does the real work; this just drives it.
"""
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QThread, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

APP_DIR = Path(__file__).resolve().parent

# Common, well-known Docker Hub images -- distrobox works with any OCI
# image, but a curated list is far friendlier than a blank text field for
# a "setup wizard"-style first run.
BASE_IMAGES = [
    {"label": "Ubuntu 24.04", "image": "ubuntu:24.04"},
    {"label": "Debian 12", "image": "debian:12"},
    {"label": "Fedora 40", "image": "fedora:40"},
    {"label": "Arch Linux", "image": "archlinux:latest"},
    {"label": "openSUSE Tumbleweed", "image": "opensuse/tumbleweed:latest"},
]

_TERMINALS = ["konsole", "xterm"]


def _terminal_cmd():
    for term in _TERMINALS:
        if subprocess.run(["which", term], capture_output=True).returncode == 0:
            return term
    return None


class Worker(QThread):
    """Runs one blocking subprocess call off the UI thread."""
    finished_ok = Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            ok, msg = self._fn()
        except Exception as exc:  # last resort -- never let a bad call crash the app
            ok, msg = False, str(exc)
        self.finished_ok.emit(ok, msg)


class ListWorker(QThread):
    """Same as Worker, but for a call that returns a list -- PySide6 can't
    marshal a Python list through a Signal(bool, str), it fails silently
    (a `_pythonToCppCopy` warning on stderr, no exception raised, the
    signal just never reaches its slot) rather than raising where it'd
    get caught.
    """
    finished_ok = Signal(list, str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            items, msg = self._fn()
        except Exception as exc:
            items, msg = [], str(exc)
        self.finished_ok.emit(items, msg)


class Backend(QObject):
    boxesChanged = Signal()
    actionFinished = Signal(bool, str)
    exportListReady = Signal(list, str)  # [(name, desktop_id), ...], box name

    def __init__(self):
        super().__init__()
        self._boxes = []
        self._workers = []  # keep references so QThreads aren't GC'd mid-run
        self.refreshBoxes()

    # -- listing --------------------------------------------------------

    @Slot(result="QVariantList")
    def boxes(self):
        return self._boxes

    @Slot()
    def refreshBoxes(self):
        result = subprocess.run(
            ["distrobox", "list", "--no-color"],
            capture_output=True, text=True,
        )
        boxes = []
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # Header line is "ID | NAME | STATUS | IMAGE"; skip it.
            for line in lines[1:]:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    _id, name, status, image = parts[0], parts[1], parts[2], parts[3]
                    boxes.append({
                        "name": name,
                        "status": status,
                        "running": status.lower().startswith("up") or status.lower().startswith("running"),
                        "image": image,
                    })
        self._boxes = boxes
        self.boxesChanged.emit()

    # -- lifecycle actions ------------------------------------------------

    def _run_action(self, fn):
        worker = Worker(fn)

        def on_done(ok, msg):
            self.refreshBoxes()
            self.actionFinished.emit(ok, msg)
            self._workers.remove(worker)

        worker.finished_ok.connect(on_done)
        self._workers.append(worker)
        worker.start()

    @Slot(str, str)
    def createBox(self, name, image):
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name or ""):
            self.actionFinished.emit(False, "Name can only contain letters, numbers, - . and _")
            return

        def task():
            result = subprocess.run(
                ["distrobox", "create", "--yes", "--name", name, "--image", image],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f'"{name}" created.'
            return False, (result.stderr.strip() or "Could not create the container.")
        self._run_action(task)

    @Slot(str)
    def deleteBox(self, name):
        def task():
            result = subprocess.run(
                ["distrobox", "rm", "--force", name],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f'"{name}" deleted.'
            return False, (result.stderr.strip() or "Could not delete the container.")
        self._run_action(task)

    @Slot(str)
    def stopBox(self, name):
        def task():
            result = subprocess.run(
                ["distrobox", "stop", "--yes", name],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f'"{name}" stopped.'
            return False, (result.stderr.strip() or "Could not stop the container.")
        self._run_action(task)

    @Slot(str)
    def enterBox(self, name):
        term = _terminal_cmd()
        if term is None:
            self.actionFinished.emit(False, "No terminal application found to open.")
            return
        # Keep the terminal open after the shell inside the box exits
        # (rather than the window vanishing the instant the user types
        # `exit`), same pattern as a normal "Open Terminal Here" action.
        inner = f"distrobox enter {name}; exec bash"
        subprocess.Popen(
            [term, "-e", "bash", "-c", inner],
            start_new_session=True,
        )

    # -- app export -------------------------------------------------------

    @Slot(str)
    def listExportableApps(self, name):
        def task():
            result = subprocess.run(
                ["distrobox", "enter", name, "--",
                 "sh", "-c", "grep -l '^Type=Application' /usr/share/applications/*.desktop 2>/dev/null"],
                capture_output=True, text=True,
            )
            paths = [p for p in result.stdout.strip().splitlines() if p]
            apps = []
            for p in paths:
                stem = Path(p).stem
                cat = subprocess.run(
                    ["distrobox", "enter", name, "--", "sh", "-c", f"grep -m1 '^Name=' {p}"],
                    capture_output=True, text=True,
                )
                label = cat.stdout.strip().removeprefix("Name=") or stem
                apps.append({"label": label, "id": stem})
            return apps, ""
        worker = ListWorker(task)

        def on_done(apps, _msg):
            self.exportListReady.emit(apps, name)
            self._workers.remove(worker)
        worker.finished_ok.connect(on_done)
        self._workers.append(worker)
        worker.start()

    @Slot(str, str)
    def exportApp(self, box_name, desktop_id):
        def task():
            result = subprocess.run(
                ["distrobox", "enter", box_name, "--", "distrobox-export", "--app", desktop_id],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return True, f'"{desktop_id}" exported to your app launcher.'
            return False, (result.stderr.strip() or "Could not export that app.")
        self._run_action(task)

    # -- environment sanity check -----------------------------------------

    @Slot(result=bool)
    def podmanReady(self):
        return subprocess.run(["podman", "info"], capture_output=True).returncode == 0


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Distrobox")
    app.setDesktopFileName("reyos-distrobox-gui")
    engine = QQmlApplicationEngine()

    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("baseImages", BASE_IMAGES)

    qml_file = APP_DIR / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        sys.exit(1)

    window = engine.rootObjects()[0]
    window.setIcon(QIcon.fromTheme("reyos-distrobox-gui"))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
