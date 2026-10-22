#!/usr/bin/env python3
"""PC (Windows) games in ReyOS Games. They live in Lutris, which runs them
with Proton (GE-Proton through umu, Lutris's default): ReyOS adds the game
to Lutris's own database and per-game config, lists every installed Lutris
game, and starts them through Lutris. Before each start it sets three of
the game's Lutris options to follow ReyOS: GameMode, the MangoHud overlay
(Gaming page switch) and, on a laptop with a usable NVIDIA card, which GPU.

Lutris is GTK; its Python code runs here only as a separate process
(`python3 pc_games.py add|launch|icon ...`), never inside the Qt apps."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emulation  # noqa: E402

HELPER = Path(__file__).resolve()
LUTRIS_DB = Path.home() / ".local" / "share" / "lutris" / "pga.db"
COVERS = emulation.GAMES_DIR / "Covers" / "pc"
LUTRIS_COVERS = Path.home() / ".local" / "share" / "lutris" / "coverart"
LUTRIS_SEARCH = "https://lutris.net/api/games?search="
# lutris: the launcher; umu-launcher: runs Proton outside Steam (Lutris uses
# it, and ReyOS runs installers with it); python-pefile: Lutris's icon reader.
PACKAGES = ["lutris", "umu-launcher", "python-pefile"]
SYSTEM = {"id": "pc", "name": "PC (Windows)", "short": "PC"}
# Not the game: installers, uninstallers, runtimes and crash reporters.
NOT_GAME = re.compile(r"unins|uninst|setup|install|redist|vcredist|vc_redist|dxsetup|dotnet|directx|"
                      r"crash|report|update|patch|config|settings|helper|easyanticheat|be_service|"
                      r"unitycrashhandler|ue4prereq|physx", re.I)
# Inside a Wine prefix: not where installers put games (top level), and
# Wine's own programs and shared runtimes (any level; found in the test:
# WordPad and Internet Explorer were offered as the game).
SKIP_DIRS = {"windows", "programdata", "users"}
WINE_DIRS = {"windows nt", "internet explorer", "windows media player", "windows photo viewer",
             "windows mail", "windows defender", "windows sidebar", "common files", "microsoft.net"}


def ready():
    return bool(shutil.which("lutris")) and bool(shutil.which("umu-run"))


def games_dir():
    """Where new PC games go: the Gaming page's "Added games are kept in"
    folder (an external SSD works), else ~/Games/PC."""
    storage = emulation.load_settings()["game_storage"]
    if storage and Path(storage).is_dir():
        return emulation.storage_system_dir(storage, "pc")
    return emulation.GAMES_DIR / "PC"


def list_games():
    """Every installed Lutris game: [{id, name, slug, runner}]. Read-only;
    an empty list without Lutris or before its first run."""
    if not LUTRIS_DB.is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{LUTRIS_DB}?mode=ro", uri=True, timeout=2)
        rows = con.execute("SELECT id, name, slug, runner FROM games WHERE installed = 1 AND runner != ''").fetchall()
        con.close()
    except sqlite3.Error:
        return []
    return [{"id": r[0], "name": r[1] or r[2], "slug": r[2], "runner": r[3]} for r in rows]


def cover(slug):
    """Box art (Lutris's coverart, downloaded by fetch_cover or Lutris), else
    the icon from the game's .exe, else Lutris's small banner."""
    for path in (LUTRIS_COVERS / f"{slug}.jpg", COVERS / f"{slug}.png",
                 Path.home() / ".local/share/lutris/banners" / f"{slug}.jpg"):
        if path.is_file():
            return str(path)
    return ""


def cover_missing(slug):
    """No box art yet, and no earlier search that found none."""
    return not (LUTRIS_COVERS / f"{slug}.jpg").is_file() and not (COVERS / f"{slug}.nocover").exists()


def fetch_cover(name, slug):
    """Box art from Lutris's game database (the covers Lutris itself shows),
    saved in Lutris's coverart folder so Lutris uses it too. Returns its
    path, or "" when none was found (remembered, so it isn't searched again)."""
    out = LUTRIS_COVERS / f"{slug}.jpg"
    if out.is_file():
        return str(out)
    req = urllib.request.Request(LUTRIS_SEARCH + urllib.parse.quote(name), headers={"User-Agent": "ReyOS-Games"})
    with urllib.request.urlopen(req, timeout=20) as r:
        results = json.load(r).get("results", [])
    # Real covers only: some entries point at one generic placeholder image.
    covers = [g for g in results if "/cover_big/" in (g.get("coverart") or "")]
    norm = lambda text: re.sub(r"[^a-z0-9]+", "", (text or "").lower())  # noqa: E731
    pick = next((g for g in covers if norm(g.get("name")) == norm(name)), covers[0] if covers else None)
    if pick is None:
        COVERS.mkdir(parents=True, exist_ok=True)
        (COVERS / f"{slug}.nocover").touch()
        return ""
    with urllib.request.urlopen(urllib.request.Request(pick["coverart"], headers={"User-Agent": "ReyOS-Games"}),
                                timeout=30) as r:
        data = r.read()
    LUTRIS_COVERS.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(".part")
    part.write_bytes(data)
    part.replace(out)
    return str(out)


def game_gpu(game_id, settings=None):
    """One game's own graphics card: "nvidia", "builtin", or "" for the
    Gaming page's choice (like PS2 games' own 3D resolution). pc_builtin_gpu
    is 1.0.0-138's on/off list."""
    settings = settings or emulation.load_settings()
    gid = str(game_id)
    if gid in settings["pc_gpu"]:
        return settings["pc_gpu"][gid]
    return "builtin" if gid in settings["pc_builtin_gpu"] else ""


def uses_nvidia(game_id, settings=None):
    settings = settings or emulation.load_settings()
    return emulation.nvidia_offload_ready() and (game_gpu(game_id, settings) or settings["game_gpu"]) == "nvidia"


def set_game_gpu(game_id, value):
    settings = emulation.load_settings()
    gid = str(game_id)
    chosen = {k: v for k, v in settings["pc_gpu"].items() if k != gid}
    if value in ("nvidia", "builtin"):
        chosen[gid] = value
    emulation.save_settings({"pc_gpu": chosen, "pc_builtin_gpu": [g for g in settings["pc_builtin_gpu"] if g != gid]})


def game_name(exe, installer):
    """A first guess for the name: the folder of a game, or an installer's
    file name without "setup"/version noise."""
    exe = Path(exe)
    raw = exe.stem if installer else exe.parent.name
    def clean(text):
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"(?i)\bv?\d+(\.\d+)+\b", " ", text)  # versions, before dots become spaces
        text = text.replace(".", " ")
        return " ".join(re.sub(r"(?i)\b(setup|install(er)?|x64|x86|win(64|32)?)\b", " ", text).split())
    name = clean(raw)
    if not name and installer:  # just "setup.exe": its folder's name
        name = clean(exe.parent.name)
    return name.title() if name else exe.stem


def slug_dir(name):
    """A new folder for the game's Windows files under games_dir()."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "game"
    root = games_dir()
    path, n = root / base, 2
    while path.exists():
        path, n = root / f"{base}-{n}", n + 1
    return path


def proton_env(prefix):
    # GE-Proton is Lutris's default too, so the game later runs on the same
    # Proton its installer ran on. umu downloads it the first time.
    return dict(os.environ, WINEPREFIX=str(prefix), GAMEID="umu-default", PROTONPATH="GE-Proton")


def run_installer(setup, prefix, log):
    """Runs a Windows installer in the game's own prefix and waits for it."""
    prefix.mkdir(parents=True, exist_ok=True)
    return subprocess.run(["umu-run", str(setup)], cwd=str(Path(setup).parent), env=proton_env(prefix),
                          stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT).returncode


def find_programs(prefix):
    """.exe files an installer left in the prefix that could be the game,
    likeliest (biggest, not an uninstaller/runtime) first."""
    drive = Path(prefix) / "drive_c"
    found = []
    for path in drive.rglob("*"):
        try:
            rel = path.relative_to(drive)
        except ValueError:
            continue
        if not rel.parts or rel.parts[0].lower() in SKIP_DIRS or any(d.lower() in WINE_DIRS for d in rel.parts):
            continue
        if path.suffix.lower() == ".exe" and path.is_file() and not NOT_GAME.search(path.name):
            found.append(path)
    return sorted(found, key=lambda p: p.stat().st_size, reverse=True)


def _helper(*args):
    out = subprocess.run([sys.executable, "-I", str(HELPER), *args], capture_output=True, text=True)
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def options(game_id=None):
    """The Lutris options that follow ReyOS: GameMode, the overlay (Gaming
    page switch) and, on a laptop, the NVIDIA card."""
    settings = emulation.load_settings()
    return {"gamemode": bool(shutil.which("gamemoderun")),
            "mangohud": bool(settings["overlay"] and shutil.which("mangohud")),
            "nvidia": uses_nvidia(game_id, settings) if game_id is not None else emulation.games_use_nvidia(settings)}


def apply_lutris_defaults():
    """The same options as Lutris-wide defaults (its system.yml), so games
    started from Lutris itself, or added there, get them too. (ok, message)"""
    opts = options()
    rc, _out, err = _helper("defaults", json.dumps(opts))
    if rc != 0:
        return False, "Couldn't change Lutris's settings: " + ((err.splitlines() or ["unknown error"])[-1])
    names = [n for n, on in (("GameMode", opts["gamemode"]), ("the performance overlay", opts["mangohud"]),
                             ("the NVIDIA graphics card", opts["nvidia"])) if on]
    what = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else (names[0] if names else "nothing extra")
    return True, f"Lutris games now start with {what}. Restart Lutris if it's open."


def add_to_lutris(name, exe, prefix, directory):
    """Returns (ok, Lutris game id or error text)."""
    rc, out, err = _helper("add", name, str(exe), str(prefix), str(directory), json.dumps(options()))
    if rc != 0:
        return False, (err.splitlines() or ["Lutris couldn't add the game."])[-1]
    game_id = json.loads(out)["id"]
    COVERS.mkdir(parents=True, exist_ok=True)
    _helper("icon", str(exe), str(COVERS / f"{json.loads(out)['slug']}.png"))
    return True, game_id


def launch(path):
    """path: "lutris:<id>". Returns (ok, message)."""
    game_id = path.split(":", 1)[1]
    game = next((g for g in list_games() if str(g["id"]) == game_id), None)
    if game is None:
        return False, "That game isn't in Lutris any more."
    log = emulation.LAUNCH_LOG.with_name("lutris-last.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as f:
        subprocess.Popen([sys.executable, "-I", str(HELPER), "launch", game_id, json.dumps(options(game_id))],
                         stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    return True, f"Starting {game['name']}..."


# ---- Run as a separate process, with Lutris's own Python code ---------------

def _lutris_config_file(configpath):
    from lutris import settings
    return Path(settings.GAME_CONFIG_DIR) / f"{configpath}.yml"


def _apply_system(system, options):
    """GameMode, MangoHud and the GPU in a Lutris "system" options dict."""
    from lutris.util.graphics.gpu import GPUS
    system["gamemode"] = options["gamemode"]
    system["mangohud"] = options["mangohud"]
    nvidia = next((card for card, gpu in GPUS.items() if gpu.driver == "nvidia"), None)
    if options["nvidia"] and nvidia:
        system["gpu"] = nvidia
    elif nvidia and system.get("gpu") == nvidia:
        del system["gpu"]  # Lutris's default: the built-in graphics


def _cmd_defaults(options):
    from lutris import settings
    from lutris.util.yaml import read_yaml_from_file, write_yaml_to_file
    os.makedirs(settings.CONFIG_DIR, exist_ok=True)
    path = os.path.join(settings.CONFIG_DIR, "system.yml")
    config = (read_yaml_from_file(path) if os.path.exists(path) else {}) or {}
    config["system"] = config.get("system") or {}
    _apply_system(config["system"], json.loads(options))
    write_yaml_to_file(config, path)


def _cmd_add(name, exe, prefix, directory, options="{}"):
    from lutris.config import write_game_config
    from lutris.database import games as games_db
    from lutris.database import schema
    from lutris import settings
    from lutris.util.strings import slugify
    # Lutris may never have been opened: no data folder or database yet.
    # (lutris.startup.init_dirs does this too, but importing it loads GTK.)
    for folder in (settings.CONFIG_DIR, settings.GAME_CONFIG_DIR, settings.DATA_DIR,
                   settings.COVERART_PATH, settings.BANNER_PATH):
        os.makedirs(folder, exist_ok=True)
    schema.syncdb()
    slug = slugify(name)
    config = {"game": {"exe": exe, "prefix": prefix, "arch": "win64", "working_dir": str(Path(exe).parent)},
              "system": {}}
    # Here as well as at each ReyOS Games start, for starts from Lutris itself.
    if options != "{}":
        _apply_system(config["system"], json.loads(options))
    configpath = write_game_config(slug, config)
    game_id = games_db.add_game(name=name, runner="wine", slug=slug, platform="Windows",
                                directory=directory, installed=1, configpath=configpath)
    print(json.dumps({"id": game_id, "slug": slug}))


def _cmd_icon(exe, out):
    try:
        from lutris.util.wine.extract_icon import IconExtractor
        icon = IconExtractor(exe).get_best_icon(256)
        if icon is not None:
            icon.save(out, "PNG")
    except Exception as e:  # no icon is fine: the card shows "PC"
        print(f"no icon: {e}", file=sys.stderr)


def _cmd_launch(game_id, options):
    from lutris.database import games as games_db
    from lutris.util.yaml import read_yaml_from_file, write_yaml_to_file
    options = json.loads(options)
    game = games_db.get_game_by_field(game_id, "id")
    path = _lutris_config_file(game["configpath"]) if game.get("configpath") else None
    if path and path.is_file():
        config = read_yaml_from_file(str(path)) or {}
        config["system"] = config.get("system") or {}
        _apply_system(config["system"], options)
        write_yaml_to_file(config, str(path))
    os.execvp("lutris", ["lutris", f"lutris:rungameid/{game_id}"])


if __name__ == "__main__":
    commands = {"add": _cmd_add, "icon": _cmd_icon, "launch": _cmd_launch, "defaults": _cmd_defaults}
    commands[sys.argv[1]](*sys.argv[2:])
