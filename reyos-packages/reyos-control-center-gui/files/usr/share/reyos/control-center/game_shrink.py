"""Add a downloaded game to the library and shrink it to save space.

A PS2, PSP or PlayStation game (.7z/.zip/.rar archive, .iso or .cue) is
unpacked, recognised from the disc itself, converted to CHD (lossless: the
same game in a smaller file; PCSX2 and the PSP/PS1 cores play it directly),
checked, and stored in the game storage folder. When that folder isn't
~/Games/ROMs (a bigger partition, an external drive), the game is linked into
~/Games/ROMs/<system>/ so the library finds it.

Qt-free, like emulation.py. Converting uses chdman from Arch's mame-tools,
installed on first use through reyos-install-emulators.sh ("shrink")."""
import re
import shutil
import subprocess
from pathlib import Path

import emulation

ARCHIVES = (".7z", ".zip", ".rar")
DISCS = (".iso", ".cue")
FILE_FILTER = "Games (*.7z *.zip *.rar *.iso *.cue *.7Z *.ZIP *.RAR *.ISO *.CUE)"
INSTALL_HELPER = Path(__file__).resolve().parent / "reyos-install-emulators.sh"
SYSTEM_NAMES = {"ps2": "PlayStation 2", "psp": "PSP", "psx": "PlayStation"}
_running = None  # the chdman in progress, so cancel() can stop it


def tool_installed():
    return shutil.which("chdman") is not None


def storage_root(settings=None):
    """Where added games are kept: the Gaming page's "Added games are kept in"
    folder, or ~/Games/ROMs."""
    path = (settings or emulation.load_settings()).get("game_storage") or ""
    return Path(path) if path else emulation.GAMES_DIR / "ROMs"


def _cue_track(cue):
    m = re.search(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', Path(cue).read_text(errors="replace"), re.M | re.I)
    return Path(cue).parent / (m.group(1) or m.group(2)) if m else None


def detect(disc):
    """"ps2", "psp" or "psx" from the disc's ISO 9660 header ("PSP GAME" or
    "PLAYSTATION"); PS2 and PS1 CDs both say PLAYSTATION, so SYSTEM.CNF
    decides (BOOT2 = PS2). None for anything else."""
    path = Path(disc)
    if path.suffix.lower() == ".cue":
        path = _cue_track(path)
        if path is None or not path.is_file():
            return None
    with open(path, "rb") as f:
        geometry = None
        for sector, offset in ((2048, 0), (2352, 24), (2352, 16)):
            f.seek(16 * sector + offset)
            pvd = f.read(2048)
            if pvd[1:6] == b"CD001":
                geometry = (sector, offset)
                break
        if geometry is None:
            return None
        ident = pvd[8:40].decode(errors="replace").strip()
        if ident == "PSP GAME":
            return "psp"
        if ident != "PLAYSTATION":
            return None

        def read(lba, size):
            data = b""
            for i in range((size + 2047) // 2048):
                f.seek((lba + i) * geometry[0] + geometry[1])
                data += f.read(2048)
            return data[:size]

        root = pvd[156:190]
        data = read(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"))
        i = 0
        while i < len(data):
            n = data[i]
            if n == 0:  # records don't cross sectors: skip to the next one
                i = (i // 2048 + 1) * 2048
                continue
            rec = data[i:i + n]
            if rec[33:33 + rec[32]].upper().startswith(b"SYSTEM.CNF"):
                cnf = read(int.from_bytes(rec[2:6], "little"), int.from_bytes(rec[10:14], "little"))
                return "ps2" if b"BOOT2" in cnf else "psx"
            i += n
    return "psx"


def _disc_files(disc):
    """The disc plus the track files a .cue points to (to size or delete)."""
    disc = Path(disc)
    if disc.suffix.lower() != ".cue":
        return [disc]
    names = re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', disc.read_text(errors="replace"), re.M | re.I)
    return [disc] + [disc.parent / (a or b) for a, b in names]


def _run_chdman(args, on_percent):
    """chdman prints "Compressing, 42.1% complete..." with carriage returns."""
    global _running
    proc = _running = subprocess.Popen(["chdman", *args], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    buf, last = b"", ""
    while True:
        chunk = proc.stderr.read(256)
        if not chunk:
            break
        buf += chunk
        *lines, buf = re.split(rb"[\r\n]", buf)
        for line in lines:
            text = line.decode(errors="replace").strip()
            if text:
                last = text
            m = re.search(r"(\d+(?:\.\d+)?)% complete", text)
            if m:
                on_percent(float(m.group(1)))
    return proc.wait(), last


def shrinkable(system_id, path):
    """A library game "Shrink to save space" can handle."""
    return system_id in SYSTEM_NAMES and Path(path).suffix.lower() in DISCS


def shrinkable_games():
    """Library games that "Shrink to save space" can handle, with the space
    their disc files take now."""
    games = []
    for system in emulation.EMU_SYSTEMS:
        for path in emulation.scan_games(system):
            if shrinkable(system["id"], path):
                try:
                    real = Path(path).resolve()
                    size = sum(p.stat().st_size for p in _disc_files(real) if p.is_file())
                except OSError:
                    continue
                games.append({"path": str(path), "title": emulation.game_title(path), "size": size})
    return games


def add_game(source, emit, settings=None, beside_original=False):
    """Adds one game. emit(text, percent) reports progress (percent -1 =
    busy). Returns (ok, message, originals): the files the user may delete
    now that the shrunk copy is in the library.

    beside_original: shrinking a game already in the library -- the .chd
    goes next to the real file (same drive, so ~/Games/ROMs doesn't fill up
    when the game lives on another partition)."""
    source = Path(source)
    library = emulation.GAMES_DIR / "ROMs"
    # A game picked from the library (often a link to a file on another
    # drive) is shrunk where its real file is, and the real file is what
    # may be deleted afterwards -- not the link, and not onto this drive.
    if source.absolute().is_relative_to(library.absolute()) or source.is_symlink():
        beside_original = True
    if beside_original:
        source = source.resolve()
    if source.suffix.lower() == ".bin" and source.with_suffix(".cue").is_file():
        source = source.with_suffix(".cue")  # a link to a CD's track: shrink the whole CD
    settings = settings or emulation.load_settings()
    root = storage_root(settings)
    work = None
    try:
        if source.suffix.lower() in ARCHIVES:
            work = root / ".adding" / source.stem
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir(parents=True)
            emit(f"Unpacking {source.name}...", -1)
            rc = subprocess.run(["bsdtar", "-xf", str(source), "-C", str(work)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if rc.returncode != 0:
                return False, f"{source.name}: couldn't unpack it ({rc.stderr.strip()[-200:]}).", []
            found = sorted(work.rglob("*.cue")) or sorted(work.rglob("*.iso")) \
                or sorted(p for p in work.rglob("*") if p.suffix.lower() in DISCS)
            if not found:
                return False, f"{source.name}: there's no game disc (.iso or .cue) inside.", []
            disc = found[0]
        elif source.suffix.lower() in DISCS:
            disc = source
        else:
            return False, f"{source.name}: not a game file ReyOS can add (use .7z, .zip, .rar, .iso or .cue).", []

        system = detect(disc)
        if system is None:
            return False, f"{source.name}: not a PlayStation 2, PSP or PlayStation game.", []
        title = emulation.game_title(disc)
        out_dir = disc.parent if beside_original else root / system
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / (disc.stem + ".chd")

        if not out.exists():
            # The shrunk file is at most the size of the disc: don't start
            # (and fill the drive) without that much room.
            need = sum(p.stat().st_size for p in _disc_files(disc) if p.is_file())
            free = shutil.disk_usage(out_dir).free
            if free < need:
                return False, (f"{title}: not enough space on that drive ({_size(free)} free, up to {_size(need)} needed). "
                               "Choose a bigger folder under Control Center > Gaming > \"Added games are kept in\"."), []
            if system == "psp":
                kind = ["createdvd", "-hs", "2048"]  # one PSP sector per hunk: faster loading
            elif system == "ps2" and disc.suffix.lower() == ".iso":
                kind = ["createdvd"]
            else:
                kind = ["createcd"]
            part = out.with_name(out.name + ".part")
            part.unlink(missing_ok=True)
            emit(f"Shrinking {title} ({SYSTEM_NAMES[system]})...", 0)
            rc, last = _run_chdman([*kind, "-i", str(disc), "-o", str(part)],
                                   lambda pct: emit(f"Shrinking {title}...", pct))
            if rc != 0:
                part.unlink(missing_ok=True)
                return False, f"{title}: shrinking failed ({last}).", []
            emit(f"Checking {title}...", -1)
            rc, last = _run_chdman(["verify", "-i", str(part)], lambda pct: emit(f"Checking {title}...", pct))
            if rc != 0:
                part.unlink(missing_ok=True)
                return False, f"{title}: the shrunk file didn't check out ({last}).", []
            part.rename(out)

        before = sum(p.stat().st_size for p in _disc_files(disc) if p.is_file())
        after = out.stat().st_size

        # Into the library: the file itself, or a link to it.
        target = library / system / out.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if out.resolve() != target.resolve() and not target.exists():
            target.symlink_to(out)
        # Old links to the same game (.iso/.cue/.bin) would list it twice;
        # only links are removed, never game files. Its "Always play in a
        # window" choice and its own 3D resolution move to the new file.
        settings = emulation.load_settings()
        windowed, resolutions = settings["windowed_games"], dict(settings["game_resolution"])
        moved = False
        for ext in (".iso", ".cue", ".bin"):
            old = library / system / (disc.stem + ext)
            if old.is_symlink():
                old.unlink()
                if str(old) in windowed:
                    windowed = [str(target) if g == str(old) else g for g in windowed]
                    moved = True
                if str(old) in resolutions:
                    resolutions[str(target)] = resolutions.pop(str(old))
                    moved = True
        if moved:
            emulation.save_settings({"windowed_games": windowed, "game_resolution": resolutions})

        if system == "ps2" and emulation.flatpak_installed("net.pcsx2.PCSX2"):
            # PCSX2 (a Flatpak) can only read folders it's been given.
            emulation.prepare_flatpak(next(s for s in emulation.EMU_SYSTEMS if s["id"] == "ps2"))

        originals = [str(source)] if source.suffix.lower() in ARCHIVES else [str(p) for p in _disc_files(disc)]
        saved = f"{_size(before)} → {_size(after)}"
        return True, f"{title} ({SYSTEM_NAMES[system]}) added: {saved}.", originals
    except OSError as e:
        return False, f"{source.name}: {e}", []
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
            try:
                work.parent.rmdir()
            except OSError:
                pass


def cancel():
    """Stops a shrink in progress (the window is closing). Its .part file is
    replaced on the next try."""
    if _running is not None and _running.poll() is None:
        _running.terminate()


def delete_originals(paths):
    """Deletes downloaded files once their shrunk copy is in the library.
    Only plain files of the kinds add_game() takes (and .bin tracks)."""
    removed = 0
    for p in map(Path, paths):
        if p.suffix.lower() in ARCHIVES + DISCS + (".bin",) and p.is_file() and not p.is_symlink():
            p.unlink()
            removed += 1
    return removed


def _size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "bytes" else f"{n} bytes"
        n /= 1024
