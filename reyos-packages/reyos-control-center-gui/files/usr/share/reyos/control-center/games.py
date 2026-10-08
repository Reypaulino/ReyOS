#!/usr/bin/env python3
"""ReyOS Games: the emulation game library as its own app, so games can be
started from the app menu without opening Control Center. Setup (installing
emulators, controllers, BIOS) stays on Control Center's Gaming page."""
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

try:
    import setproctitle
except ImportError:
    setproctitle = None

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
import emulation  # noqa: E402
from emulation import EMU_SYSTEMS  # noqa: E402


class CoverWorker(QThread):
    """Fetches box art for (system, rom) pairs; a network error just skips a
    game (it's retried next time, since nothing was cached for it)."""
    coverReady = Signal(str, str)

    def __init__(self, todo):
        super().__init__()
        self.todo = todo
        self.cancelled = False

    def run(self):
        for system, rom in self.todo:
            if self.cancelled:
                return
            try:
                cover = emulation.fetch_cover(system, rom)
            except (OSError, ValueError):
                continue
            if cover:
                self.coverReady.emit(str(rom), cover)


class GamesBackend(QObject):
    coverReady = Signal(str, str)
    message = Signal(bool, str)
    gamesChanged = Signal()

    def __init__(self):
        super().__init__()
        self._cover_worker = None
        # Games copied into ~/Games/ROMs show up by themselves: watch every
        # ROM folder (and their subfolders), and reload shortly after a
        # change, since a big copy fires many change events.
        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self, singleShot=True, interval=1500)
        self._debounce.timeout.connect(self._folders_changed)
        self._watcher.directoryChanged.connect(lambda _path: self._debounce.start())
        self._watch_folders()

    def _watch_folders(self):
        emulation.prepare_folders()
        dirs = {str(emulation.GAMES_DIR / "ROMs")}
        for system in EMU_SYSTEMS:
            for folder in emulation.rom_dirs(system):
                dirs.add(str(folder))
                dirs.update(str(p) for p in folder.rglob("*") if p.is_dir())
        new = sorted(dirs - set(self._watcher.directories()))
        if new:
            self._watcher.addPaths(new)

    def _folders_changed(self):
        self._watch_folders()
        self.gamesChanged.emit()

    @Slot(result="QVariantList")
    def emulationSystems(self):
        return [{"id": s["id"], "name": s["name"], "short": s["short"],
                 "installed": emulation.system_installed(s),
                 "games": sum(1 for _ in emulation.scan_games(s))} for s in EMU_SYSTEMS]

    @Slot(result="QVariantList")
    def emulationGames(self):
        games = []
        for system in EMU_SYSTEMS:
            playable = emulation.system_installed(system)
            for path in emulation.scan_games(system):
                games.append({
                    "title": emulation.game_title(path),
                    "system": system["name"], "short": system["short"], "systemId": system["id"],
                    "path": str(path), "playable": playable,
                    "cover": emulation.local_cover(system, path),
                })
        games.sort(key=lambda g: (g["title"].lower(), g["system"]))
        return games

    @Slot(result=bool)
    def boxartEnabled(self):
        return bool(emulation.load_settings()["boxart"])

    @Slot(bool)
    def setBoxart(self, enabled):
        emulation.save_settings({"boxart": bool(enabled)})

    @Slot()
    def fetchCovers(self):
        """Downloads missing box art in the background, one coverReady per
        game found, if box art downloads are on."""
        if not self.boxartEnabled():
            return
        if self._cover_worker is not None and self._cover_worker.isRunning():
            return
        todo = [(s, p) for s in EMU_SYSTEMS for p in emulation.scan_games(s)
                if not emulation.local_cover(s, p) and not emulation.cover_cached(s, p)]
        if todo:
            self._cover_worker = CoverWorker(todo)
            self._cover_worker.coverReady.connect(self.coverReady.emit)
            self._cover_worker.start()

    def stop(self):
        # A download can take up to its 30 s timeout. Every cache write is
        # atomic (.part + rename), so if it hasn't stopped after a moment,
        # leave without waiting -- destroying the still-running QThread
        # during normal shutdown would abort the process instead.
        worker = self._cover_worker
        if worker is not None and worker.isRunning():
            worker.cancelled = True
            if not worker.wait(2000):
                os._exit(0)

    @Slot(str, str)
    def launchGame(self, system_id, path):
        self.message.emit(*emulation.launch_game(system_id, path))

    @Slot(str)
    def openGamesFolder(self, system_id):
        emulation.prepare_folders()
        folder = emulation.GAMES_DIR / "ROMs" / system_id if system_id else emulation.GAMES_DIR / "ROMs"
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(folder)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot()
    def openSetup(self):
        """Control Center's Gaming page: install emulators, controllers, BIOS."""
        env = dict(os.environ, REYOS_CC_INITIAL_PAGE="GamingPage.qml")
        subprocess.Popen([str(APP_DIR / "main.py")], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def main():
    if setproctitle is not None:
        setproctitle.setproctitle("reyos-games")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Games")
    app.setDesktopFileName("reyos-games")
    app.setWindowIcon(QIcon.fromTheme("reyos-games", QIcon.fromTheme("applications-games")))
    engine = QQmlApplicationEngine()
    backend = GamesBackend()
    app.aboutToQuit.connect(backend.stop)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(APP_DIR / "qml" / "GamesMain.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
