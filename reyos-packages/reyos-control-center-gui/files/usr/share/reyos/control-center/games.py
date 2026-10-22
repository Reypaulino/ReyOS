#!/usr/bin/env python3
"""ReyOS Games: the emulation game library as its own app, so games can be
started from the app menu without opening Control Center. Setup (installing
emulators, controllers, BIOS) stays on Control Center's Gaming page."""
import os
import re
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
import game_shrink  # noqa: E402
import pc_games  # noqa: E402
from controller_setup import ControllerSetupWorker  # noqa: E402
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
                if system is pc_games.SYSTEM:  # rom: a Lutris game
                    cover, key = pc_games.fetch_cover(rom["name"], rom["slug"]), f"lutris:{rom['id']}"
                else:
                    cover, key = emulation.fetch_cover(system, rom), str(rom)
            except (OSError, ValueError):
                continue
            if cover:
                self.coverReady.emit(key, cover)


class AddGamesWorker(QThread):
    """Asks for game files (or takes a library game to shrink), installs the
    shrinking tool if needed (one password prompt), then adds and shrinks
    each game."""
    progress = Signal(str, float)
    finished_ok = Signal(bool, str, "QVariantList")

    def __init__(self, paths=None):
        super().__init__()
        self.paths = paths
        self.beside_original = paths is not None

    def run(self):
        paths = self.paths
        if paths is None:
            picked = subprocess.run(
                ["kdialog", "--title", "Add Games", "--getopenfilename", str(Path.home() / "Downloads"),
                 game_shrink.FILE_FILTER, "--multiple", "--separate-output"],
                capture_output=True, text=True)
            paths = [p for p in picked.stdout.splitlines() if p.strip()]
        if not paths:  # Cancel
            self.finished_ok.emit(True, "", [])
            return
        if not game_shrink.tool_installed():
            self.progress.emit("Installing the game shrinking tool (about 20 MB; ReyOS asks for your password)...", -1)
            rc = subprocess.run(["pkexec", str(game_shrink.INSTALL_HELPER), "shrink"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode
            if not game_shrink.tool_installed():
                self.finished_ok.emit(False, "Install cancelled -- the password prompt was closed." if rc in (126, 127)
                                      else "Couldn't install the game shrinking tool -- check your network connection.", [])
                return
        messages, originals, ok_all = [], [], True
        for n, path in enumerate(paths, 1):
            prefix = f"({n} of {len(paths)}) " if len(paths) > 1 else ""
            ok, message, done = game_shrink.add_game(path, lambda text, pct: self.progress.emit(prefix + text, pct),
                                                     beside_original=self.beside_original)
            ok_all &= ok
            messages.append(message)
            originals += done
        self.finished_ok.emit(ok_all, " ".join(messages), originals)


class AddPcGameWorker(QThread):
    """Adds a Windows game: installs Lutris if needed, asks for the .exe,
    runs it first if it's an installer, then adds the game to Lutris."""
    progress = Signal(str, float)
    finished_ok = Signal(bool, str, "QVariantList")

    def _ask(self, *args):
        out = subprocess.run(["kdialog", "--title", "Add PC Game", *args], capture_output=True, text=True)
        return out.returncode, out.stdout.strip()

    def run(self):
        if not pc_games.ready():
            self.progress.emit("Installing Lutris, which runs Windows games (about 300 MB)...", -1)
            if "#[multilib]" in Path("/etc/pacman.conf").read_text():
                subprocess.run(["sudo", "-n", "/usr/share/reyos/welcome/enable-multilib.sh"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["sudo", "-n", "/usr/share/reyos/bin/reyos-admin", "install-apps", *pc_games.PACKAGES],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not pc_games.ready():
                self.finished_ok.emit(False, "Couldn't install Lutris -- check your network connection and try again.", [])
                return
        self.progress.emit("Choose the game's .exe...", -1)
        rc, exe = self._ask("--getopenfilename", str(Path.home() / "Downloads"), "*.exe *.EXE|Windows programs (*.exe)")
        if rc != 0 or not exe:
            self.finished_ok.emit(True, "", [])
            return
        guess_installer = bool(re.search(r"(?i)setup|install", Path(exe).name))
        # kdialog's --default doesn't apply to --yesnocancel: "Yes" is always
        # the focused button, so the likelier answer goes on it.
        labels = ["Installer: install the game first", "The game itself (already installed)"]
        rc, _ = self._ask("--yesnocancel", f"Is {Path(exe).name} the game's installer, or the game itself?",
                          "--yes-label", labels[0 if guess_installer else 1],
                          "--no-label", labels[1 if guess_installer else 0])
        if rc == 2:
            self.finished_ok.emit(True, "", [])
            return
        installer = (rc == 0) == guess_installer
        rc, name = self._ask("--inputbox", "Name of the game:", pc_games.game_name(exe, installer))
        if rc != 0 or not name.strip():
            self.finished_ok.emit(True, "", [])
            return
        name = name.strip()
        prefix = pc_games.slug_dir(name)
        if installer:
            self.progress.emit(f"Running the {name} installer: follow its steps and keep the folder it suggests. "
                               "If the game itself starts instead, just close it: ReyOS then adds it as it is. "
                               "The first time, ReyOS also downloads Proton (about 2 GB), which takes a while.", -1)
            log_path = emulation.LAUNCH_LOG.with_name("pc-install.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w") as log:
                pc_games.run_installer(exe, prefix, log)
            programs = pc_games.find_programs(prefix)
            if not programs and not guess_installer:
                # Nothing was installed: it was the game itself (it ran as
                # the "installer"), so add that .exe where it is.
                programs = [Path(exe)]
            if not programs:
                self.finished_ok.emit(False, f"No game was found after the installer closed -- it may have been "
                                      f"cancelled. Its log: {log_path}", [])
                return
            game_exe = programs[0]
            if len(programs) > 1:
                drive = prefix / "drive_c"
                items = []
                for i, p in enumerate(programs[:15]):
                    items += [str(i), f"{p.relative_to(drive)}  ({p.stat().st_size // 1048576} MB)", "on" if i == 0 else "off"]
                rc, pick = self._ask("--radiolist", f"Which program starts {name}?", *items)
                if rc != 0:
                    self.finished_ok.emit(True, "", [])
                    return
                game_exe = programs[int(pick)]
            directory = prefix if game_exe != Path(exe) else game_exe.parent
        else:
            game_exe, directory = Path(exe), Path(exe).parent
        self.progress.emit(f"Adding {name} to Lutris...", -1)
        ok, result = pc_games.add_to_lutris(name, game_exe, prefix, directory)
        if not ok:
            self.finished_ok.emit(False, f"Couldn't add {name} to Lutris: {result}", [])
            return
        self.finished_ok.emit(True, f"{name} is in your library, under Windows games.", [f"lutris:{result}"])


class GamesBackend(QObject):
    coverReady = Signal(str, str)
    message = Signal(bool, str)
    gamesChanged = Signal()
    addProgress = Signal(str, float)
    addFinished = Signal(bool, str, "QVariantList")
    pcAddFinished = Signal(bool, str, str)
    controllerSetupStep = Signal(int, int, str, str, str, str)
    controllerSetupDone = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._cover_worker = None
        self._add_worker = None
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
            for folder in emulation.library_dirs(system):
                if not folder.is_dir():
                    continue
                dirs.add(str(folder))
                dirs.update(str(p) for p in folder.rglob("*") if p.is_dir() and not p.name.startswith("."))
        new = sorted(dirs - set(self._watcher.directories()))
        if new:
            self._watcher.addPaths(new)

    def _folders_changed(self):
        self._watch_folders()
        self.gamesChanged.emit()

    @Slot(result="QVariantList")
    def emulationSystems(self):
        systems = [{"id": s["id"], "name": s["name"], "short": s["short"],
                    "installed": emulation.system_installed(s),
                    "games": sum(1 for _ in emulation.scan_games(s))} for s in EMU_SYSTEMS]
        return systems + [dict(pc_games.SYSTEM, installed=pc_games.ready(), games=len(pc_games.list_games()))]

    @Slot(result="QVariantList")
    def emulationGames(self):
        games = []
        settings = emulation.load_settings()
        windowed = set(settings["windowed_games"])
        for system in EMU_SYSTEMS:
            playable = emulation.system_installed(system)
            for path in emulation.scan_games(system):
                games.append({
                    "title": emulation.game_title(path),
                    "system": system["name"], "short": system["short"], "systemId": system["id"],
                    "path": str(path), "playable": playable,
                    "windowed": str(path) in windowed,
                    "cover": emulation.local_cover(system, path),
                    "shrinkable": game_shrink.shrinkable(system["id"], path),
                    "has3d": system["id"] in emulation.THREE_D_SYSTEMS,
                    # PS2 follows ReyOS's resolution only with the Gaming
                    # page's "Use these for PlayStation 2 too" switch on.
                    "resolutionSettable": system["id"] in emulation.THREE_D_SYSTEMS
                                          and (system["id"] != "ps2" or settings["ps2_graphics"]),
                    "resolution": emulation.game_resolution(path, settings) or 0,
                    "gpu": "", "nvidiaAvailable": False,
                })
        # Windows games: every installed Lutris game.
        nvidia_available = emulation.nvidia_offload_ready()
        playable = pc_games.ready()
        for game in pc_games.list_games():
            games.append({
                "title": game["name"], "system": pc_games.SYSTEM["name"], "short": pc_games.SYSTEM["short"],
                "systemId": "pc", "path": f"lutris:{game['id']}", "playable": playable, "windowed": False,
                "cover": pc_games.cover(game["slug"]), "shrinkable": False, "has3d": False,
                "resolutionSettable": False, "resolution": 0,
                "gpu": pc_games.game_gpu(game["id"], settings), "nvidiaAvailable": nvidia_available,
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
        todo += [(pc_games.SYSTEM, g) for g in pc_games.list_games() if pc_games.cover_missing(g["slug"])]
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
        # A controller setup waits for a button press; cancelling ends it
        # (nothing is saved).
        setup = getattr(self, "_controller_worker", None)
        if setup is not None and setup.isRunning():
            setup.cancelled = True
            if not setup.wait(2000):
                os._exit(0)
        # Shrinking a game takes minutes; closing the window ends it. The
        # .part file is ignored and replaced on the next try.
        if self._add_worker is not None and self._add_worker.isRunning():
            game_shrink.cancel()
            os._exit(0)

    @Slot(str, bool)
    def setGameWindowed(self, path, windowed):
        emulation.set_game_windowed(path, windowed)

    @Slot(str, int)
    def setGameResolution(self, path, value):
        """0 = follow Control Center's 3D resolution."""
        emulation.set_game_resolution(path, value or None)

    @Slot(result=int)
    def defaultResolution(self):
        return emulation.load_settings()["resolution"]

    @Slot(str, str)
    def launchGame(self, system_id, path):
        if system_id == "pc":
            self.message.emit(*pc_games.launch(path))
        else:
            self.message.emit(*emulation.launch_game(system_id, path))

    @Slot()
    def addPcGame(self):
        if self._add_worker is not None and self._add_worker.isRunning():
            return
        self._add_worker = AddPcGameWorker()
        self._add_worker.progress.connect(self.addProgress.emit)
        self._add_worker.finished_ok.connect(self._pc_game_added)
        self._add_worker.start()

    def _pc_game_added(self, ok, message, added):
        self.pcAddFinished.emit(ok, message, added[0] if added else "")
        self.gamesChanged.emit()

    @Slot(str, str)
    def setGameGpu(self, path, value):
        """"" = follow the Gaming page's graphics card."""
        pc_games.set_game_gpu(path.split(":", 1)[1], value)

    @Slot(result=str)
    def defaultGpu(self):
        return emulation.load_settings()["game_gpu"]

    @Slot()
    def openLutris(self):
        subprocess.Popen(["lutris"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot(str)
    def openGamesFolder(self, system_id):
        emulation.prepare_folders()
        storage = emulation.load_settings()["game_storage"]
        if system_id == "pc":
            folder = pc_games.games_dir()
        elif storage and Path(storage).is_dir():
            folder = emulation.storage_system_dir(storage, system_id) if system_id else Path(storage)
        else:
            folder = emulation.GAMES_DIR / "ROMs" / system_id if system_id else emulation.GAMES_DIR / "ROMs"
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(folder)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot()
    def addGames(self):
        self._start_add(None)

    @Slot(str)
    def shrinkGame(self, path):
        """Right-click > Shrink to save space, for a game already listed."""
        self._start_add([path])

    def _start_add(self, paths):
        if self._add_worker is not None and self._add_worker.isRunning():
            return
        self._add_worker = AddGamesWorker(paths)
        self._add_worker.progress.connect(self.addProgress.emit)
        self._add_worker.finished_ok.connect(self._games_added)
        self._add_worker.start()

    def _games_added(self, ok, message, originals):
        self.addFinished.emit(ok, message, originals)
        self.gamesChanged.emit()

    @Slot("QVariantList", result=int)
    def deleteOriginals(self, paths):
        return game_shrink.delete_originals(paths)

    @Slot(result=str)
    def startWith(self):
        """What Control Center opened the library for: "add" (Add games),
        "shrink" (Shrink them) or ""."""
        return os.environ.pop("REYOS_GAMES_START", "")

    @Slot()
    def shrinkAll(self):
        paths = [g["path"] for g in game_shrink.shrinkable_games()]
        if paths:
            self._start_add(paths)

    @Slot(result="QVariantList")
    def controllers(self):
        return emulation.list_controllers()

    # The same step-by-step setup as Control Center's, run here so the
    # library's controller window doesn't have to open Control Center.
    @Slot(str)
    def startControllerSetup(self, path):
        worker = getattr(self, "_controller_worker", None)
        if worker is not None and worker.isRunning():
            return
        self._controller_worker = ControllerSetupWorker(path)
        self._controller_worker.step.connect(self.controllerSetupStep.emit)
        self._controller_worker.done.connect(self.controllerSetupDone.emit)
        self._controller_worker.start()

    @Slot()
    def skipControllerStep(self):
        if getattr(self, "_controller_worker", None) is not None:
            self._controller_worker.skip = True

    @Slot()
    def cancelControllerSetup(self):
        if getattr(self, "_controller_worker", None) is not None:
            self._controller_worker.cancelled = True

    @Slot(result="QVariantMap")
    def player1Controller(self):
        """The pad the setup and button names are for: player 1, else the first one."""
        pads = emulation.list_controllers()
        return emulation.player1_pad(pads) or (pads[0] if pads else {})

    @Slot(str, result="QVariantMap")
    def buttonLayout(self, system_id):
        """One system's buttons for the library's own button window."""
        pads = emulation.list_controllers()
        pad = emulation.player1_pad(pads) or (pads[0] if pads else None)
        brand = pad["brand"] if pad else emulation.saved_brand()
        layout = next((l for l in emulation.system_controls(brand) if l["id"] == system_id), None)
        return dict(layout, brand=brand) if layout else {}

    @Slot(str, str, str)
    def setButton(self, system_id, console_key, pad_key):
        emulation.set_button(system_id, console_key, pad_key)

    @Slot(str)
    def resetButtons(self, system_id):
        emulation.reset_buttons(system_id)

    @Slot(str)
    def openButtonLayout(self, system_id):
        """Control Center's "Button layout" for this game's system."""
        env = dict(os.environ, REYOS_CC_INITIAL_PAGE="GamingPage.qml", REYOS_CC_START="buttons:" + system_id)
        subprocess.Popen([str(APP_DIR / "main.py")], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot()
    def setUpController(self):
        """The step-by-step setup is Control Center's: open its Gaming page
        straight into it."""
        env = dict(os.environ, REYOS_CC_INITIAL_PAGE="GamingPage.qml", REYOS_CC_START="controller-setup")
        subprocess.Popen([str(APP_DIR / "main.py")], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

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
