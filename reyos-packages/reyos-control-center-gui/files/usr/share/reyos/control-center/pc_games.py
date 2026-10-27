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
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emulation  # noqa: E402

HELPER = Path(__file__).resolve()
LUTRIS_DB = Path.home() / ".local" / "share" / "lutris" / "pga.db"
UNINSTALL_LOG = Path.home() / ".cache" / "reyos" / "pc-uninstall.log"
COVERS = emulation.GAMES_DIR / "Covers" / "pc"
LUTRIS_COVERS = Path.home() / ".local" / "share" / "lutris" / "coverart"
LUTRIS_SEARCH = "https://lutris.net/api/games?search="
# Download sites and repackers that put their name on the game's folder.
RELEASE_TAGS = (r"(?i)\b(ankergames|fitgirl|dodi|elamigos|kaoskrew|steamrip|igg ?games|gog|repack|"
                r"codex|plaza|skidrow|tenoke|empress|razor1911|portable)\b")
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
    """Where the games' Wine prefixes go: always ~/Games/PC on the system
    disk, never the "Added games are kept in" folder. A game kept on an
    external drive gets that drive as a Windows drive letter, and every
    prefix on the same drive has links (dosdevices) pointing back at it, so
    a launcher that searches its own drive looped forever (Prince of
    Persia: The Two Thrones on the laptop's SD card, 2026-10-25). Prefixes
    are small; an already-installed game's own files stay where they are."""
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


def game_exe(game_id):
    """A Lutris game's .exe path ("" if unknown), read from its config."""
    try:
        con = sqlite3.connect(f"file:{LUTRIS_DB}?mode=ro", uri=True, timeout=2)
        row = con.execute("SELECT configpath FROM games WHERE id = ?", (int(game_id),)).fetchone()
        con.close()
        import yaml  # python-yaml comes with Lutris
        config = yaml.safe_load((Path.home() / ".local/share/lutris/games" / f"{row[0]}.yml").read_text())
        return str((config.get("game") or {}).get("exe") or "")
    except Exception:
        return ""


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


def _norm(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _real_cover(game):
    # Some entries point at one generic placeholder image.
    return "/cover_big/" in (game.get("coverart") or "")


def lutris_match(name):
    """The game's entry in Lutris's database (official name, box art), or
    None. When the full name finds nothing, up to three words are dropped
    from the end (a download-site tag, "Deluxe Edition"), but then only an
    exact name counts, so "Prince of Persia" alone never picks the 1989 game."""
    words = name.split()
    for n in range(len(words), max(len(words) - 4, 0), -1):
        query = " ".join(words[:n])
        req = urllib.request.Request(LUTRIS_SEARCH + urllib.parse.quote(query), headers={"User-Agent": "ReyOS-Games"})
        with urllib.request.urlopen(req, timeout=20) as r:
            results = json.load(r).get("results", [])
        exact = [g for g in results if _norm(g.get("name")) == _norm(query)]
        if exact:
            return next((g for g in exact if _real_cover(g)), exact[0])
        if n == len(words) and results:
            return next((g for g in results if _real_cover(g)), results[0])
    return None


def fetch_cover(name, slug):
    """Box art from Lutris's game database (the covers Lutris itself shows),
    saved in Lutris's coverart folder so Lutris uses it too. Returns its
    path, or "" when none was found (remembered, so it isn't searched again)."""
    out = LUTRIS_COVERS / f"{slug}.jpg"
    if out.is_file():
        return str(out)
    pick = lutris_match(name)
    if pick is None or not _real_cover(pick):
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
    file name without "setup"/version/download-site noise, then the official
    name from Lutris's database when it knows the game (so the box art is
    found too). Runs in Add PC game's worker thread: the lookup may wait."""
    exe = Path(exe)
    raw = exe.stem if installer else exe.parent.name
    def clean(text):
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"(?i)\bv?\d+(\.\d+)+\b", " ", text)  # versions, before dots become spaces
        text = text.replace(".", " ")
        text = re.sub(RELEASE_TAGS, " ", text)
        return " ".join(re.sub(r"(?i)\b(setup|install(er)?|x64|x86|win(64|32)?)\b", " ", text).split())
    name = clean(raw)
    if not name and installer:  # just "setup.exe": its folder's name
        name = clean(exe.parent.name)
    if not name:
        return exe.stem
    try:
        match = lutris_match(name)
    except (OSError, ValueError):  # offline: the cleaned-up name
        match = None
    return match["name"] if match else name.title()


def slug_dir(name):
    """A new folder for the game's Wine prefix under games_dir()."""
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


def run_installer(setup, prefix, log, watch=None):
    """Runs a Windows installer in the game's own prefix and waits for it,
    calling watch() every two seconds meanwhile."""
    prefix.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["umu-run", str(setup)], cwd=str(Path(setup).parent), env=proton_env(prefix),
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    while True:
        try:
            return proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if watch:
                log.flush()
                watch()


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


# ---- Old Ubisoft controller lists -----------------------------------------
# Ubisoft games of 2003–2008 (Prince of Persia: Sands of Time, Warrior Within,
# The Two Thrones) only accept the pads in their own Gamepads.DAT: 21 PC pads
# of the time, no PlayStation or Xbox pad. Without the file they take any pad.

def gamepad_list(exe):
    """The game's Gamepads.DAT next to its .exe, or None."""
    try:
        folder = Path(exe).parent
        return next((f for f in folder.iterdir() if f.name.lower() == "gamepads.dat" and f.is_file()), None)
    except OSError:
        return None


def disable_gamepad_list(exe):
    """Renamed, not deleted (rename it back to undo). Returns (ok, message)."""
    found = gamepad_list(exe)
    if found is None:
        return True, "This game has no controller list to turn off."
    try:
        found.rename(found.with_name(found.name + ".original"))
    except OSError as e:
        return False, f"Couldn't turn off the game's controller list: {e.strerror}."
    return True, (f"Any controller works in this game now ({found.name} was renamed to {found.name}.original). "
                  "Set its buttons in the game's own Options → Controls. If the controller stops "
                  "once your saved profile loads, make a new profile in the game.")


# ---- Proton downloads ------------------------------------------------------
STEAM_COMPAT = Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d"
GE_PROTON = re.compile(r"^GE-Proton(\d+)-(\d+)")


def proton_download(log_path):
    """The Proton build umu is downloading for this launch/install ("" if
    none). umu fetches a new GE-Proton the first time and after each GE-Proton
    release, before the game starts, and only logs it."""
    try:
        text = Path(log_path).read_text(errors="replace")
    except OSError:
        return ""
    found = re.findall(r"Downloading (GE-Proton[\w.-]+?)\.tar\.gz", text)
    if not found:
        return ""
    # Done once umu says which Proton it uses.
    return "" if "Using " in text.rsplit(f"Downloading {found[-1]}.tar.gz", 1)[1] else found[-1]


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def _in_use(path):
    """A running program uses this path (its command line or WINEPREFIX)."""
    needle = re.compile(re.escape(str(path).encode()) + rb"(/|\0|$)")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        for what in ("cmdline", "environ"):
            try:
                if needle.search((proc / what).read_bytes()):
                    return True
            except OSError:
                pass
    return False


def old_protons():
    """GE-Proton builds umu left behind: every GE-Proton folder but the
    newest, unless Lutris, Steam or a running program still names it (a
    version picked by hand in Lutris or Steam stays)."""
    try:
        builds = [p for p in STEAM_COMPAT.iterdir() if p.is_dir() and GE_PROTON.match(p.name)]
    except OSError:
        return []
    if len(builds) < 2:
        return []
    builds.sort(key=lambda p: tuple(int(n) for n in GE_PROTON.match(p.name).groups()))
    named = ""
    lutris = Path.home() / ".local" / "share" / "lutris"
    for f in [*(lutris / "games").glob("*.yml"), lutris / "system.yml", lutris / "runners" / "wine.yml",
              *(Path.home() / ".config" / "lutris").rglob("*.yml"),
              Path.home() / ".local" / "share" / "Steam" / "config" / "config.vdf"]:
        try:
            named += f.read_text(errors="replace")
        except OSError:
            pass
    return [p for p in builds[:-1] if p.name not in named and not _in_use(p)]


def remove_old_protons():
    """Deletes old_protons(). Returns (names, bytes freed)."""
    names, freed = [], 0
    for path in old_protons():
        size = _dir_size(path)
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            names.append(path.name)
            freed += size
    return names, freed


# ---- Uninstall -------------------------------------------------------------
# Beside RetroArch's own save folders (one per core) in ~/Games/Saves.
SAVES = emulation.GAMES_DIR / "Saves" / "PC"
# Folders named like this are a library or a binaries folder, never one
# game's own folder.
GENERIC_DIRS = {"games", "game", "pc", "pc games", "windows games", "downloads", "desktop", "documents",
                "roms", "steamlibrary", "steamapps", "common", "program files", "program files (x86)",
                "drive_c", "lutris", "media", "mnt", "run", "home"}
BIN_DIRS = {"bin", "bin32", "bin64", "binaries", "win32", "win64", "x64", "x86", "system", "retail", "exe"}
# Inside the prefix: where Windows games keep saves (Proton's user is steamuser).
SAVE_DIRS = ("Documents", "My Documents", "Saved Games", "AppData/Roaming", "AppData/Local", "AppData/LocalLow")
# Wine's own folders there, not the game's.
WINE_USER_DIRS = {"temp", "microsoft", "openxr", "wine", "mesa_shader_cache", "dxvk", "vkd3d"}
SAVE_NAME = re.compile(r"save|profile", re.I)


def _game_config(game_id):
    """(pga.db row as a dict, the game's Lutris yml as a dict)."""
    import yaml  # python-yaml comes with Lutris
    con = sqlite3.connect(f"file:{LUTRIS_DB}?mode=ro", uri=True, timeout=2)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM games WHERE id = ?", (int(game_id),)).fetchone()
    others = [r[0] for r in con.execute("SELECT configpath FROM games WHERE id != ? AND configpath != ''", (int(game_id),))]
    con.close()
    if row is None:
        return None, {}, []
    row = dict(row)
    config = {}
    path = Path.home() / ".local/share/lutris/games" / f"{row.get('configpath')}.yml"
    if row.get("configpath") and path.is_file():
        config = yaml.safe_load(path.read_text()) or {}
    return row, config, others


def _game_folder(exe, prefix):
    """The game's own folder for "Also delete the game files", or None: the
    .exe's folder (up from bin/Win64...), never a library folder, $HOME or
    above it, a drive's top folder, or anything holding a Wine prefix."""
    if not exe:
        return None
    folder = Path(exe).parent
    while folder.name.lower() in BIN_DIRS and folder.parent != folder:
        folder = folder.parent
    home = Path.home()
    try:
        folder = folder.resolve()
    except OSError:
        return None
    if (not folder.is_dir() or folder.name.lower() in GENERIC_DIRS or folder in (home, *home.parents)
            or folder.is_mount() or len(folder.parts) < 4 or (prefix and Path(prefix).resolve().is_relative_to(folder))
            or (folder / "drive_c").exists() or folder == games_dir().resolve()):
        return None
    return folder


def _prefix_saves(prefix):
    """Folders in the prefix's user profile that the game wrote."""
    users = Path(prefix) / "drive_c" / "users"
    found = []
    for user in (users.iterdir() if users.is_dir() else []):
        if user.name in ("Public",) or user.is_symlink():
            continue
        for rel in SAVE_DIRS:
            base = user / rel
            if not base.is_dir() or base.is_symlink():
                continue
            for entry in base.iterdir():
                if entry.is_symlink() or entry.name.lower() in WINE_USER_DIRS or entry.name.startswith("."):
                    continue
                if entry.is_file() or any(f.is_file() for f in entry.rglob("*")):
                    found.append(entry)
    return found


def uninstall_info(game_id):
    """What Uninstall… would remove, with sizes, for its confirm window."""
    row, config, others = _game_config(game_id)
    if row is None:
        return {"ok": False, "message": "That game isn't in Lutris any more."}
    game = config.get("game") or {}
    exe, prefix = str(game.get("exe") or ""), str(game.get("prefix") or "")
    prefix_path = Path(prefix) if prefix else None
    # Only a real Wine prefix, not $HOME or a folder another game shares.
    shared = []
    if prefix_path:
        import yaml
        for configpath in others:
            try:
                other = yaml.safe_load((Path.home() / ".local/share/lutris/games" / f"{configpath}.yml").read_text()) or {}
            except (OSError, yaml.YAMLError):
                continue
            if str((other.get("game") or {}).get("prefix") or "") == prefix:
                shared.append(configpath)
    prefix_ok = bool(prefix_path and (prefix_path / "drive_c").is_dir() and not shared
                     and prefix_path.resolve() not in (Path.home(), *Path.home().parents))
    inside = bool(prefix_ok and exe and Path(exe).resolve().is_relative_to(prefix_path.resolve()))
    folder = None if inside else _game_folder(exe, prefix)
    saves = [str(p) for p in _prefix_saves(prefix_path)] if prefix_ok else []
    if folder:
        saves += [str(p) for p in folder.iterdir() if p.is_dir() and SAVE_NAME.search(p.name)]
    return {
        "ok": True, "id": int(game_id), "name": row.get("name") or row.get("slug"), "slug": row.get("slug"),
        "running": bool((prefix_ok and _in_use(prefix_path)) or (exe and _in_use(exe))),
        "prefix": prefix if prefix_ok else "", "prefixSize": _dir_size(prefix_path) if prefix_ok else 0,
        "prefixShared": bool(shared), "installedInPrefix": inside,
        "gameDir": str(folder) if folder else "", "gameDirSize": _dir_size(folder) if folder else 0,
        "saves": saves, "savesDir": str(SAVES / (row.get("slug") or "game")),
    }


def _keep_saves(info, paths):
    """Copies save folders to ~/Games/Saves/<slug>/, beside earlier copies."""
    target = Path(info["savesDir"])
    if target.exists():
        n = 2
        while target.with_name(f"{target.name}-{n}").exists():
            n += 1
        target = target.with_name(f"{target.name}-{n}")
    for path in map(Path, paths):
        # Keep where it came from: Documents/<Game>, AppData/Roaming/<Game>, <folder>/POP3Profiles.
        parts = path.parts
        rel = Path(*parts[parts.index("users") + 2:]) if "users" in parts and "drive_c" in parts else Path("Game folder", path.name)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, dest, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(path, dest)
    return target


def uninstall(game_id, remove_prefix, remove_files, keep_saves):
    """Removes the game from Lutris and ReyOS (always), its Wine prefix and
    its own folder (if asked), saves copied first. Returns (ok, message)."""
    info = uninstall_info(game_id)
    if not info["ok"]:
        return False, info["message"]
    if info["running"]:
        return False, f"{info['name']} is running. Close it first."
    remove_prefix = remove_prefix and bool(info["prefix"])
    remove_files = remove_files and bool(info["gameDir"])
    kept = None
    if keep_saves and info["saves"] and (remove_prefix or remove_files):
        doomed = [s for s in info["saves"]
                  if (remove_prefix and Path(s).is_relative_to(info["prefix"]))
                  or (remove_files and Path(s).is_relative_to(info["gameDir"]))]
        if doomed:
            try:
                kept = _keep_saves(info, doomed)
            except OSError as e:
                return False, f"Nothing was removed: your saves couldn't be copied ({e.strerror})."
    rc, _out, err = _helper("remove", str(game_id))
    if rc != 0:
        time.sleep(1)  # Lutris may have had its database open for a moment
        rc, _out, err = _helper("remove", str(game_id))
    if rc != 0:
        try:
            UNINSTALL_LOG.parent.mkdir(parents=True, exist_ok=True)
            with UNINSTALL_LOG.open("a") as log:
                log.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} remove {game_id} ({info['name']}): rc {rc}\n{err}\n")
        except OSError:
            pass
        if kept:  # nothing else was removed, so a retry shouldn't leave a second copy
            shutil.rmtree(kept, ignore_errors=True)
        return False, ("Couldn't remove the game from Lutris, nothing was deleted: "
                       + ((err.splitlines() or ["unknown error"])[-1]) + " (details in ~/.cache/reyos/pc-uninstall.log)")
    freed = 0
    for wanted, path, size in ((remove_prefix, info["prefix"], info["prefixSize"]),
                               (remove_files, info["gameDir"], info["gameDirSize"])):
        if wanted:
            shutil.rmtree(path, ignore_errors=True)
            freed += size - (_dir_size(path) if Path(path).exists() else 0)
    slug = info["slug"]
    if not any(g["slug"] == slug for g in list_games()):
        for art in (LUTRIS_COVERS / f"{slug}.jpg", COVERS / f"{slug}.png", COVERS / f"{slug}.nocover",
                    Path.home() / ".local/share/lutris/banners" / f"{slug}.jpg",
                    Path.home() / ".local/share/icons/hicolor/128x128/apps" / f"lutris_{slug}.png"):
            art.unlink(missing_ok=True)
    settings = emulation.load_settings()
    gid = str(game_id)
    emulation.save_settings({"pc_gpu": {k: v for k, v in settings["pc_gpu"].items() if k != gid},
                             "pc_builtin_gpu": [g for g in settings["pc_builtin_gpu"] if g != gid]})
    home = lambda p: str(p).replace(str(Path.home()), "~", 1)
    message = f"{info['name']} uninstalled" + (f" (freed {human_size(freed)})." if freed else ".")
    if kept:
        message += f" Your saves are in {home(kept)}."
    if info["gameDir"] and not remove_files:
        message += f" The game's files are still in {home(info['gameDir'])}."
    return True, message


# ---- Drives that aren't there after a restart --------------------------------
# A drive opened in Dolphin (or an SD card) is mounted under /run/media/<you>/
# only until the next restart; /etc/fstab mounts are there at startup.

def _mount_point(path):
    path = Path(path).absolute()
    while not os.path.ismount(path) and path != path.parent:
        path = path.parent
    return path


def _fstab_mounts():
    points = set()
    try:
        for line in Path("/etc/fstab").read_text().splitlines():
            fields = line.split()
            if len(fields) >= 2 and not fields[0].startswith("#"):
                points.add(fields[1])
    except OSError:
        pass
    return points


def temporary_drive(path):
    """The drive's name when `path` is on a drive that's only mounted until
    the next restart (opened in Dolphin, an SD card or USB drive), else ""."""
    mount = _mount_point(path)
    if str(mount) in _fstab_mounts() or not (str(mount).startswith(("/run/media/", "/media/"))):
        return ""
    return mount.name


def _drive_of_missing(path):
    """For a path under /run/media/<user>/<name>/ that's missing: <name>
    (a disk label or UUID, which is what udisks names the folder)."""
    parts = Path(path).parts
    if len(parts) > 4 and parts[1] == "run" and parts[2] == "media":
        return parts[4]
    if len(parts) > 3 and parts[1] == "media":
        return parts[3] if parts[2] == os.environ.get("USER", "") and len(parts) > 4 else parts[2]
    return ""


def mount_drive_for(path):
    """Tries to mount the drive a missing game was on (udisks, no password
    for the logged-in user's internal and removable drives). Returns the
    drive's name ("" when the path isn't on such a drive)."""
    name = _drive_of_missing(path)
    if not name:
        return ""
    for link in (Path("/dev/disk/by-label") / name, Path("/dev/disk/by-uuid") / name):
        if link.exists():
            subprocess.run(["udisksctl", "mount", "--no-user-interaction", "-b", str(link.resolve())],
                           capture_output=True, timeout=30)
            break
    return name


# ---- Saves kept by Uninstall, back into a re-added game -------------------------

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def kept_saves_for(name):
    """The newest ~/Games/Saves/PC/<slug>[-N] folder Uninstall left for a
    game with this name, or None. The name may have grown or shrunk since
    ("…-most-wanted" vs "…-most-wanted-black-edition"), so a whole-word
    prefix of two words or more either way counts; the user confirms it."""
    new = _slug(name)
    if not new or not SAVES.is_dir():
        return None
    found = []
    for folder in SAVES.iterdir():
        if not folder.is_dir() or folder.is_symlink():
            continue
        old = re.sub(r"-\d+$", "", folder.name)
        shorter = min(old, new, key=len)
        if old == new or (shorter.count("-") >= 1 and (new.startswith(old + "-") or old.startswith(new + "-"))):
            if any(f.is_file() for f in folder.rglob("*")):
                found.append(folder)
    return max(found, key=lambda f: f.stat().st_mtime) if found else None


def prefix_user_dir(prefix):
    """The prefix's Windows user folder (Proton's user is steamuser)."""
    users = Path(prefix) / "drive_c" / "users"
    if (users / "steamuser").is_dir():
        return users / "steamuser"
    return next((u for u in (users.iterdir() if users.is_dir() else [])
                 if u.is_dir() and not u.is_symlink() and u.name != "Public"), None)


def init_prefix(prefix, log):
    """Creates the game's Wine prefix now (it's normally made at the first
    start), so kept saves can go into it before the game runs."""
    Path(prefix).mkdir(parents=True, exist_ok=True)
    # cwd: the runtime container can't enter /usr (where ReyOS Games runs from).
    subprocess.run(["umu-run", "wineboot", "-u"], env=proton_env(prefix), cwd=str(prefix), stdin=subprocess.DEVNULL,
                   stdout=log, stderr=subprocess.STDOUT, timeout=900)
    return prefix_user_dir(prefix)


def restore_saves(kept, prefix, game_exe):
    """Copies a kept saves folder back: Documents/…, AppData/… into the
    prefix's user folder, "Game folder/<name>" next to the game. Never
    overwrites a file that's already there. Returns the number of files."""
    user = prefix_user_dir(prefix)
    folder = _game_folder(str(game_exe), str(prefix))
    copied = 0
    for src in Path(kept).rglob("*"):
        if not src.is_file() or src.is_symlink():
            continue
        rel = src.relative_to(kept)
        if rel.parts[0] == "Game folder":
            if folder is None:
                continue
            dest = folder / Path(*rel.parts[1:])
        elif user is not None:
            dest = user / rel
        else:
            continue
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("bytes", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def _helper(*args):
    out = subprocess.run([sys.executable, "-I", str(HELPER), *args], capture_output=True, text=True)
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def options(game_id=None):
    """The Lutris options that follow ReyOS: GameMode, the overlay (Gaming
    page switch), on a laptop the NVIDIA card, and at a game's start the
    PC button layout."""
    settings = emulation.load_settings()
    opts = {"gamemode": bool(shutil.which("gamemoderun")),
            "mangohud": bool(settings["overlay"] and shutil.which("mangohud")),
            "nvidia": uses_nvidia(game_id, settings) if game_id is not None else emulation.games_use_nvidia(settings)}
    if game_id is not None:
        opts["pad_env"] = controller_env(settings)
    return opts


# Lutris "env" entries ReyOS owns: set while the PC button layout is changed.
PAD_ENV_KEYS = ("PROTON_PREFER_SDL", "SDL_GAMECONTROLLERCONFIG")


def controller_env(settings=None):
    """Proton environment for the PC button layout (Gaming page / library
    right-click > Controller buttons): SDL input with the player 1 pad's
    buttons moved. {} with the usual layout, or no set-up pad connected
    (then Proton reads the pad as it always does)."""
    m = emulation.button_map("pc", settings)
    if all(k == v for k, v in m.items()):
        return {}
    pads = emulation.list_controllers()
    pad = emulation.player1_pad(pads) or next((p for p in pads if p["configured"]), None)
    mapping = emulation.sdl_mapping(pad, m) if pad else None
    return {"PROTON_PREFER_SDL": "1", "SDL_GAMECONTROLLERCONFIG": mapping} if mapping else {}


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
    # The game's drive may not be mounted (opened in Dolphin before the last
    # restart): mount it, else say so instead of Lutris's "file not found".
    exe = game_exe(game_id)
    if exe and not Path(exe).exists():
        drive = mount_drive_for(exe)
        if not Path(exe).exists():
            if drive:
                return False, (f"{game['name']} is on the drive \"{drive}\", which isn't connected. Connect it "
                               "(or open it in Dolphin), then press Play again.")
            return False, f"{game['name']} isn't where it was added from any more: {exe}"
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
    if "pad_env" in options:
        env = {k: v for k, v in (system.get("env") or {}).items() if k not in PAD_ENV_KEYS}
        env.update(options["pad_env"])
        if env:
            system["env"] = env
        else:
            system.pop("env", None)


# DLLs that mod loaders (Ultimate ASI Loader: widescreen fixes, input mods…)
# and ReShade put next to a game's .exe. Windows loads them from there; Wine
# uses its own unless told "native, then builtin".
MOD_DLLS = ("dinput8", "dinput", "dsound", "version", "winmm", "d3d8", "d3d9", "d3d10", "d3d11",
            "ddraw", "dxgi", "xinput1_3", "xinput1_4", "winhttp", "wininet")


def _mod_overrides(config):
    """Native-then-builtin for each MOD_DLLS file next to the game's .exe;
    an override already set (by hand, or in Lutris) is left alone."""
    exe = (config.get("game") or {}).get("exe")
    if not exe:
        return
    folder = Path(exe).parent
    try:
        present = {f.stem.lower() for f in folder.iterdir() if f.suffix.lower() == ".dll"}
    except OSError:
        return
    found = [d for d in MOD_DLLS if d in present]
    if found:
        wine = config.setdefault("wine", {}) or {}
        config["wine"] = wine
        overrides = wine.setdefault("overrides", {}) or {}
        wine["overrides"] = overrides
        for dll in found:
            overrides.setdefault(dll, "n,b")


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
    _mod_overrides(config)
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


def _cmd_remove(game_id):
    """The game's Lutris entry and config file (Lutris's own "Remove")."""
    from lutris.database import games as games_db
    game = games_db.get_game_by_field(game_id, "id")
    if not game:
        return
    path = _lutris_config_file(game["configpath"]) if game.get("configpath") else None
    if path and path.is_file():
        path.unlink()
    games_db.delete_game(game_id)


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
        _mod_overrides(config)  # again: a mod may have been added since
        write_yaml_to_file(config, str(path))
    os.execvp("lutris", ["lutris", f"lutris:rungameid/{game_id}"])


if __name__ == "__main__":
    commands = {"add": _cmd_add, "icon": _cmd_icon, "launch": _cmd_launch, "defaults": _cmd_defaults,
                "remove": _cmd_remove}
    commands[sys.argv[1]](*sys.argv[2:])
