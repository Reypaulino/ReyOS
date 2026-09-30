"""Qt-free emulation helpers for Control Center's Gaming page: the systems
table, ReyOS's RetroArch display settings, the BIOS checker, and the
controller setup (reads the pad straight from evdev and writes a RetroArch
udev autoconfig profile, since Arch ships no joypad-autoconfig package)."""
import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import struct
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Cartridge systems also list .zip/.7z: RetroArch opens the game inside the
# archive itself (the system comes from the folder the archive is in).
EMU_SYSTEMS = [
    {"id": "nes", "short": "NES", "thumbs": ["Nintendo - Nintendo Entertainment System"],
     "name": "NES / Famicom", "core": "nestopia", "exts": [".nes", ".unf", ".fds", ".zip", ".7z"]},
    {"id": "snes", "short": "SNES", "thumbs": ["Nintendo - Super Nintendo Entertainment System"],
     "name": "Super Nintendo", "core": "snes9x", "exts": [".sfc", ".smc", ".zip", ".7z"]},
    {"id": "gb", "short": "GB", "thumbs": ["Nintendo - Game Boy", "Nintendo - Game Boy Color"],
     "name": "Game Boy / Color", "core": "gambatte", "exts": [".gb", ".gbc", ".zip", ".7z"]},
    {"id": "gba", "short": "GBA", "thumbs": ["Nintendo - Game Boy Advance"],
     "name": "Game Boy Advance", "core": "mgba", "exts": [".gba", ".zip", ".7z"]},
    {"id": "genesis", "short": "MD", "thumbs": ["Sega - Mega Drive - Genesis", "Sega - Master System - Mark III", "Sega - Game Gear"],
     "name": "Genesis / Master System / Game Gear", "core": "genesis_plus_gx", "exts": [".md", ".gen", ".smd", ".sms", ".gg", ".zip", ".7z"]},
    {"id": "dreamcast", "short": "DC", "thumbs": ["Sega - Dreamcast"],
     "name": "Dreamcast", "core": "flycast", "exts": [".cdi", ".gdi", ".chd", ".cue", ".m3u"]},
    {"id": "n64", "short": "N64", "thumbs": ["Nintendo - Nintendo 64"],
     "name": "Nintendo 64", "core": "mupen64plus_next", "exts": [".n64", ".z64", ".v64", ".zip", ".7z"]},
    {"id": "psx", "short": "PS1", "thumbs": ["Sony - PlayStation"],
     "name": "PlayStation", "core": "mednafen_psx", "exts": [".cue", ".chd", ".pbp", ".m3u"]},
    # No PS2 or 3DS emulator in Arch's repos; these two are the maintained
    # standalone emulators from Flathub, installed per-user (no password).
    {"id": "ps2", "short": "PS2", "thumbs": ["Sony - PlayStation 2"],
     "name": "PlayStation 2 (needs a fast PC)", "flatpak": "net.pcsx2.PCSX2", "app": "PCSX2",
     "exts": [".iso", ".chd", ".cso", ".zso", ".cue", ".gz"]},
    {"id": "psp", "short": "PSP", "thumbs": ["Sony - PlayStation Portable"],
     "name": "PSP", "core": "ppsspp", "exts": [".iso", ".cso", ".pbp", ".chd"]},
    {"id": "nds", "short": "DS", "thumbs": ["Nintendo - Nintendo DS"],
     "name": "Nintendo DS", "core": "melonds", "exts": [".nds", ".zip", ".7z"]},
    {"id": "3ds", "short": "3DS", "thumbs": ["Nintendo - Nintendo 3DS"],
     "name": "Nintendo 3DS", "flatpak": "org.azahar_emu.Azahar", "app": "Azahar",
     "exts": [".3ds", ".cci", ".cxi", ".3dsx", ".app", ".z3ds", ".zcci", ".zcxi", ".z3dsx"]},
    {"id": "gamecube", "short": "GC", "thumbs": ["Nintendo - GameCube", "Nintendo - Wii"],
     "name": "GameCube / Wii (needs a fast PC)", "core": "dolphin", "dirs": ["gamecube", "wii"], "exts": [".iso", ".gcm", ".rvz", ".wbfs", ".ciso", ".gcz"]},
]
GAMES_DIR = Path.home() / "Games"
BIOS_DIR = GAMES_DIR / "BIOS"
LIBRETRO_DIR = Path("/usr/lib/libretro")
REYOS_CFG_DIR = Path.home() / ".config" / "reyos"
RETROARCH_REYOS_CFG = REYOS_CFG_DIR / "retroarch-reyos.cfg"
CORE_OPTIONS_CFG = REYOS_CFG_DIR / "retroarch-core-options.cfg"
SETTINGS_JSON = REYOS_CFG_DIR / "emulation.json"
AUTOCONFIG_DIR = Path.home() / ".config" / "retroarch" / "autoconfig" / "udev"
DOLPHIN_SYS = Path("/usr/share/dolphin-emu/sys")
FLATHUB_URL = "https://flathub.org/repo/flathub.flatpakrepo"
PCSX2_INI = Path.home() / ".var" / "app" / "net.pcsx2.PCSX2" / "config" / "PCSX2" / "inis" / "PCSX2.ini"


def rom_dirs(system):
    return [GAMES_DIR / "ROMs" / d for d in system.get("dirs", [system["id"]])]


def core_path(system):
    return LIBRETRO_DIR / f"{system.get('core', '')}_libretro.so"


def flatpak_installed(app_id):
    return any((base / app_id / "current").exists() for base in (
        Path.home() / ".local" / "share" / "flatpak" / "app", Path("/var/lib/flatpak/app")))


def system_installed(system):
    if "flatpak" in system:
        return flatpak_installed(system["flatpak"])
    # GameCube also needs dolphin-emu's data files (see link_system_files);
    # installs from before that was added show as not installed so the
    # user can tick it again to get them.
    if system["id"] == "gamecube" and not DOLPHIN_SYS.is_dir():
        return False
    return core_path(system).is_file()


# ---- Display settings -----------------------------------------------------
DEFAULT_SETTINGS = {"fullscreen": True, "picture": "fill", "resolution": 1, "expanded": None, "bios_expanded": False, "boxart": True}

# 3D internal resolution per core, keyed by ReyOS's 1x / 2x / 4x choice.
# Option names and values checked against the cores Arch ships.
RESOLUTION_OPTIONS = {
    1: {"mupen64plus-EnableNativeResFactor": "1", "beetle_psx_internal_resolution": "1x(native)",
        "ppsspp_internal_resolution": "480x272", "melonds_opengl_renderer": "disabled",
        "melonds_opengl_resolution": "1x native (256x192)", "dolphin_efb_scale": "1",
        "reicast_internal_resolution": "640x480"},
    2: {"mupen64plus-EnableNativeResFactor": "2", "beetle_psx_internal_resolution": "2x",
        "ppsspp_internal_resolution": "960x544", "melonds_opengl_renderer": "enabled",
        "melonds_opengl_resolution": "2x native (512x384)", "dolphin_efb_scale": "2",
        "reicast_internal_resolution": "1280x960"},
    4: {"mupen64plus-EnableNativeResFactor": "4", "beetle_psx_internal_resolution": "4x",
        "ppsspp_internal_resolution": "1920x1088", "melonds_opengl_renderer": "enabled",
        "melonds_opengl_resolution": "4x native (1024x768)", "dolphin_efb_scale": "4",
        "reicast_internal_resolution": "2560x1920"},
}


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        settings.update(json.loads(SETTINGS_JSON.read_text()))
    except (OSError, ValueError):
        pass
    if settings["picture"] not in ("sharp", "fill", "smooth"):
        settings["picture"] = "fill"
    if settings["resolution"] not in RESOLUTION_OPTIONS:
        settings["resolution"] = 1
    return settings


def save_settings(settings):
    merged = load_settings()
    merged.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    REYOS_CFG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_JSON.write_text(json.dumps(merged, indent=1))
    write_retroarch_cfg(merged)
    return load_settings()


def _set_cfg_values(path, values):
    """Update `key = "value"` lines in a RetroArch cfg, keeping every other
    line (RetroArch itself writes the rest of the core options here)."""
    lines = path.read_text().splitlines() if path.is_file() else []
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values:
            lines[i] = f'{key} = "{values[key]}"'
            seen.add(key)
    lines += [f'{k} = "{v}"' for k, v in values.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n")


def write_retroarch_cfg(settings=None):
    """The small config ReyOS appends at launch (--appendconfig), so the
    user's own ~/.config/retroarch/retroarch.cfg is never rewritten. Core
    options go to a ReyOS-owned file for the same reason."""
    settings = settings or load_settings()
    REYOS_CFG_DIR.mkdir(parents=True, exist_ok=True)
    picture = settings["picture"]
    values = {
        "system_directory": BIOS_DIR,
        "savefile_directory": GAMES_DIR / "Saves",
        "savestate_directory": GAMES_DIR / "Saves" / "states",
        "rgui_browser_directory": GAMES_DIR / "ROMs",
        "video_fullscreen": "true" if settings["fullscreen"] else "false",
        "video_scale_integer": "true" if picture == "sharp" else "false",
        "video_smooth": "true" if picture == "smooth" else "false",
        "input_joypad_driver": "udev",
        # Start + Select opens RetroArch's menu (Quit is in there) so a
        # controller alone can leave a game; the Home button does too once
        # it's been set up.
        "input_menu_toggle_gamepad_combo": "4",
        "global_core_options": "true",
        "core_options_path": CORE_OPTIONS_CFG,
    }
    RETROARCH_REYOS_CFG.write_text("".join(f'{k} = "{v}"\n' for k, v in values.items()))
    _set_cfg_values(CORE_OPTIONS_CFG, RESOLUTION_OPTIONS[settings["resolution"]])


def prepare_folders():
    """~/Games/ROMs/<id>/, ~/Games/BIOS/ and saves, a short README, the
    RetroArch config, and links to system files some cores need."""
    for system in EMU_SYSTEMS:
        for folder in rom_dirs(system):
            folder.mkdir(parents=True, exist_ok=True)
    for sub in ("BIOS", "BIOS/ps2", "BIOS/dc", "Saves", "Saves/states"):
        (GAMES_DIR / sub).mkdir(parents=True, exist_ok=True)
    readme = GAMES_DIR / "README.txt"
    if not readme.exists():
        readme.write_text(
            "ReyOS Emulation\n\n"
            "Put your games in ROMs/<system>/ (for example ROMs/snes/) and open\n"
            "Control Center > Gaming to play them.\n\n"
            "ReyOS does not include any games or BIOS files. Only use games and\n"
            "BIOS files you have the right to use, for example dumped from\n"
            "cartridges, discs and consoles you own.\n\n"
            "BIOS files go in BIOS/ (PlayStation 2: BIOS/ps2/, Dreamcast: BIOS/dc/).\n"
            "PlayStation and PlayStation 2 need one; Control Center > Gaming >\n"
            "BIOS files shows what's there and what's missing.\n")
    link_system_files()
    write_retroarch_cfg()


def link_system_files():
    # The Dolphin core looks for its data (fonts, game fixes) in
    # <system dir>/dolphin-emu/Sys; Arch's libretro-dolphin doesn't ship
    # it, the standalone dolphin-emu package does.
    target = BIOS_DIR / "dolphin-emu" / "Sys"
    if DOLPHIN_SYS.is_dir() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.symlink_to(DOLPHIN_SYS)


def prepare_flatpak(system):
    """PCSX2's Flatpak has no access to your files: give it ~/Games (the BIOS
    folder needs write access, PCSX2 keeps its NVRAM next to the BIOS), and
    on first use point it at ~/Games/BIOS/ps2 so the setup wizard is skipped."""
    if system["id"] != "ps2":
        return
    subprocess.run(["flatpak", "override", "--user", f"--filesystem={GAMES_DIR}", system["flatpak"]],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if not PCSX2_INI.exists():
        PCSX2_INI.parent.mkdir(parents=True, exist_ok=True)
        PCSX2_INI.write_text(f"[UI]\nSetupWizardIncomplete = false\n\n[Folders]\nBios = {BIOS_DIR / 'ps2'}\n")


def launch_command(system, rom):
    settings = load_settings()
    if system["id"] == "ps2":
        return ["flatpak", "run", system["flatpak"], "-batch",
                "-fullscreen" if settings["fullscreen"] else "-nofullscreen", "--", rom]
    if system["id"] == "3ds":
        return ["flatpak", "run", system["flatpak"], "-f" if settings["fullscreen"] else "-w", rom]
    cmd = ["retroarch", f"--appendconfig={RETROARCH_REYOS_CFG}", "-L", str(core_path(system)), rom]
    # GameMode (installed with Steam on this page) for the RetroArch cores;
    # the PCSX2/Azahar Flatpaks ask for it themselves through the portal.
    return (["gamemoderun"] if shutil.which("gamemoderun") else []) + cmd


def launch_game(system_id, path):
    """Starts a game detached from the caller. Returns (ok, message)."""
    system = next((s for s in EMU_SYSTEMS if s["id"] == system_id), None)
    if system is None or not Path(path).is_file():
        return False, "That game file couldn't be found."
    if not system_installed(system):
        return False, f"The {system['name']} emulator isn't installed yet -- set it up in Control Center > Gaming."
    if not RETROARCH_REYOS_CFG.is_file():
        prepare_folders()
    if "flatpak" in system:
        prepare_flatpak(system)
    subprocess.Popen(launch_command(system, path), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return True, f"Starting {game_title(Path(path))}..."


# ---- BIOS checker ---------------------------------------------------------
# Checksums from the libretro core documentation. `need` is "one" (at least
# one file of the group is required), "optional", or "system" (installed
# with the emulator, not supplied by the user).
BIOS_TABLE = {
    "psx": {"need": "one", "files": [
        ("scph5501.bin", "490f666e1afb15b7362b406ed1cea246", "North America"),
        ("scph5500.bin", "8dd7d5296a650fac7319bce665a6a53c", "Japan"),
        ("scph5502.bin", "32736f17079d0b2b7024407c39bd3050", "Europe"),
    ]},
    "gba": {"need": "optional", "files": [
        ("gba_bios.bin", "a860e8c0b6d573d191e4ec7db1b1e4f6", "real boot logo; games run without it"),
    ]},
    "nds": {"need": "optional", "files": [
        ("bios7.bin", "df692a80a5b1bc90728bc3dfc76cd948", "ARM7 BIOS"),
        ("bios9.bin", "a392174eb3e572fed6447e956bde4b25", "ARM9 BIOS"),
        ("firmware.bin", None, "firmware; without these a free replacement is used"),
    ]},
    "dreamcast": {"need": "optional", "files": [
        ("dc/dc_boot.bin", "e10c53c2f8b90bab96ead2d368858623", "boot ROM; most games run without it"),
    ]},
    # PS2 BIOS dumps come in many versions per region, so any 4 MiB file in
    # the folder counts; PCSX2 itself shows which version it found.
    "ps2": {"need": "folder", "dir": "ps2", "size": 4 * 1024 * 1024, "files": []},
    "gamecube": {"need": "system", "files": []},
}
_BIOS_MAX_SIZE = 4 * 1024 * 1024


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _bios_dir_hashes():
    hashes = {}
    if BIOS_DIR.is_dir():
        for path in BIOS_DIR.iterdir():
            try:
                if path.is_file() and path.stat().st_size <= _BIOS_MAX_SIZE:
                    hashes.setdefault(_md5(path), []).append(path.name)
            except OSError:
                pass
    return hashes


def bios_report(installed_ids):
    """One entry per installed system that has BIOS or system files, each
    with a verdict and per-file status: ok, rename (right file under another
    name), wrong (right name, wrong contents), missing."""
    hashes = _bios_dir_hashes()
    report = []
    for system in EMU_SYSTEMS:
        sid = system["id"]
        if sid not in BIOS_TABLE or sid not in installed_ids:
            continue
        spec = BIOS_TABLE[sid]
        if spec["need"] == "folder":
            folder = BIOS_DIR / spec["dir"]
            found = [p.name for p in folder.iterdir() if p.is_file() and p.stat().st_size == spec["size"]] if folder.is_dir() else []
            report.append({"id": sid, "name": system["name"], "need": "folder", "ok": bool(found),
                           "files": [{"name": n, "note": "PS2 BIOS", "status": "ok", "source": ""} for n in found],
                           "summary": (f"Found {len(found)} PS2 BIOS file(s) in ~/Games/BIOS/ps2." if found else
                                       "Needs a PS2 BIOS dumped from your console in ~/Games/BIOS/ps2 (any file name) -- games won't start without it.")})
            continue
        if spec["need"] == "system":
            ok = (BIOS_DIR / "dolphin-emu" / "Sys").is_dir()
            report.append({"id": sid, "name": system["name"], "need": "system", "ok": ok, "files": [],
                           "summary": "Emulator data files are in place." if ok else
                           "Emulator data files are missing -- tick GameCube / Wii above and press Install selected."})
            continue
        files, found = [], 0
        for name, md5, note in spec["files"]:
            path = BIOS_DIR / name
            status, source = "missing", ""
            if path.is_file():
                status = "ok" if md5 is None or _md5(path) == md5 else "wrong"
            if status != "ok" and md5 and md5 in hashes:
                status, source = "rename", hashes[md5][0]
            found += status == "ok"
            files.append({"name": name, "note": note, "status": status, "source": source})
        if spec["need"] == "one":
            ok = found > 0
            summary = ("Ready." if ok else
                       "Needs one of these files in ~/Games/BIOS -- games won't start without it.")
        else:
            ok = True
            summary = "Optional -- games work without these." if found < len(files) else "All optional files present."
        report.append({"id": sid, "name": system["name"], "need": spec["need"], "ok": ok,
                       "files": files, "summary": summary})
    return report


def bios_fix_name(source, name):
    """Copy a BIOS the checker recognised by checksum to the name the core
    looks for. Copy, not rename, in case the user needs the original too."""
    valid = {f[0] for spec in BIOS_TABLE.values() for f in spec["files"]}
    src, dst = BIOS_DIR / Path(source).name, BIOS_DIR / name
    if name not in valid or not src.is_file() or dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return True


# ---- Controllers (evdev) ----------------------------------------------------
EV_KEY, EV_ABS = 0x01, 0x03
KEY_UP, KEY_DOWN, BTN_MISC, KEY_MAX = 103, 108, 0x100, 0x2FF
BTN_JOYSTICK, BTN_GAMEPAD = 0x120, 0x130
ABS_HAT0X, ABS_HAT3Y, ABS_MISC, ABS_MAX = 0x10, 0x17, 0x28, 0x3F
_EVENT = struct.Struct("llHHi")


def _ioc_read(nr, size):
    return (2 << 30) | (size << 16) | (ord("E") << 8) | nr


def _ioctl_bytes(fd, nr, size):
    return fcntl.ioctl(fd, _ioc_read(nr, size), bytes(size))


def _bits(buf):
    return {i for i in range(len(buf) * 8) if buf[i // 8] >> (i % 8) & 1}


def _absinfo(fd, code):
    value, minimum, maximum, _fuzz, _flat, _res = struct.unpack(
        "6i", _ioctl_bytes(fd, 0x40 + code, 24))
    return value, minimum, maximum


def _norm(value, minimum, maximum):
    # Same centring as RetroArch's udev_compute_axis, as -1.0 .. 1.0.
    if maximum <= minimum:
        return 0.0
    return (2.0 * (value - minimum) / (maximum - minimum)) - 1.0


def _open_pad(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        name = _ioctl_bytes(fd, 0x06, 256).split(b"\0", 1)[0].decode(errors="replace")
        _bus, vendor, product, _ver = struct.unpack("4H", _ioctl_bytes(fd, 0x02, 8))
        keys = _bits(_ioctl_bytes(fd, 0x20 + EV_KEY, (KEY_MAX + 1) // 8))
        axes = _bits(_ioctl_bytes(fd, 0x20 + EV_ABS, (ABS_MAX + 1) // 8))
    except OSError:
        os.close(fd)
        raise
    return fd, {"name": name, "vendor": vendor, "product": product, "keys": keys, "axes": axes}


def _is_gamepad(info):
    keys, axes = info["keys"], info["axes"]
    if not any(BTN_JOYSTICK <= k < BTN_JOYSTICK + 0x20 for k in keys):
        return False
    # Motion-sensor and touchpad nodes of PlayStation pads have no buttons
    # in this range; the Steam Deck-style "virtual" mice don't either.
    return 0 in axes or ABS_HAT0X in axes or bool(keys & {0x220, 0x221, 0x222, 0x223})


def _button_indices(info, fd):
    """Button and axis numbering exactly as RetroArch's udev joypad driver
    assigns it (udev_add_pad in input/drivers_joypad/udev_joypad.c)."""
    keys, buttons = info["keys"], {}
    for rng in (range(KEY_UP, KEY_DOWN + 1), range(BTN_MISC, KEY_MAX),
                range(0, KEY_UP), range(KEY_DOWN + 1, BTN_MISC)):
        for code in rng:
            if code in keys and len(buttons) < 64:
                buttons[code] = len(buttons)
    axes, n = {}, 0
    for code in range(ABS_MISC):
        if ABS_HAT0X <= code <= ABS_HAT3Y or code not in info["axes"]:
            continue
        try:
            _value, minimum, maximum = _absinfo(fd, code)
        except OSError:
            continue
        if maximum > minimum and n < 32:
            axes[code] = n
            n += 1
    return buttons, axes


def list_controllers():
    pads = []
    for path in sorted(Path("/dev/input").glob("event*"), key=lambda p: int(p.name[5:])):
        try:
            fd, info = _open_pad(str(path))
        except OSError:
            continue
        os.close(fd)
        if _is_gamepad(info):
            pads.append({"path": str(path), "name": info["name"],
                         "vendor": info["vendor"], "product": info["product"],
                         "brand": controller_brand(info["vendor"]),
                         "configured": profile_path(info["name"]).is_file()})
    return pads


def profile_path(name):
    safe = re.sub(r"[^A-Za-z0-9 ._-]+", "_", name).strip() or "Controller"
    return AUTOCONFIG_DIR / f"ReyOS - {safe}.cfg"


# RetroArch's RetroPad is laid out like a SNES pad: b = bottom face button,
# a = right, y = left, x = top.
CONTROLLER_STEPS = [
    ("b", "Press the bottom face button", "A on Xbox, ✕ on PlayStation, B on Nintendo"),
    ("a", "Press the right face button", "B on Xbox, ○ on PlayStation, A on Nintendo"),
    ("y", "Press the left face button", "X on Xbox, □ on PlayStation, Y on Nintendo"),
    ("x", "Press the top face button", "Y on Xbox, △ on PlayStation, X on Nintendo"),
    ("up", "Press up on the D-pad", "The D-pad is the cross-shaped arrow pad, lower left."),
    ("down", "Press down on the D-pad", "The D-pad is the cross-shaped arrow pad, lower left."),
    ("left", "Press left on the D-pad", "The D-pad is the cross-shaped arrow pad, lower left."),
    ("right", "Press right on the D-pad", "The D-pad is the cross-shaped arrow pad, lower left."),
    ("l", "Press the left shoulder button", "LB / L1 / L -- the top edge, above the left trigger"),
    ("r", "Press the right shoulder button", "RB / R1 / R -- the top edge, above the right trigger"),
    ("l2", "Pull the left trigger", "LT / L2 / ZL -- under your left index finger"),
    ("r2", "Pull the right trigger", "RT / R2 / ZR -- under your right index finger"),
    ("select", "Press Select", "The small button left of centre: View on Xbox, Share / Create on PlayStation, − on Nintendo"),
    ("start", "Press Start", "The small button right of centre: Menu on Xbox, Options on PlayStation, + on Nintendo"),
    ("l3", "Click the left stick in", "Press straight down on the left stick until it clicks"),
    ("r3", "Click the right stick in", "Press straight down on the right stick until it clicks"),
    ("l_x", "Push the left stick all the way right", ""),
    ("l_y", "Push the left stick all the way down", ""),
    ("r_x", "Push the right stick all the way right", ""),
    ("r_y", "Push the right stick all the way down", ""),
    ("menu_toggle", "Press the Home button", "Xbox / PS / Home button -- opens the emulator menu in a game"),
]

# USB vendor ids of the pads whose buttons have well-known names.
PAD_BRANDS = {0x045E: "xbox", 0x054C: "playstation", 0x057E: "nintendo"}

# (title, hint) per brand, replacing the generic text above.
BRAND_STEP_TEXT = {
    "xbox": {
        "b": ("Press A", "The green A button, bottom of the four on the right"),
        "a": ("Press B", "The red B button, right of the four"),
        "y": ("Press X", "The blue X button, left of the four"),
        "x": ("Press Y", "The yellow Y button, top of the four"),
        "l": ("Press LB", "The left bumper, the top edge above the left trigger"),
        "r": ("Press RB", "The right bumper, the top edge above the right trigger"),
        "l2": ("Pull LT", "The left trigger, under your left index finger"),
        "r2": ("Pull RT", "The right trigger, under your right index finger"),
        "select": ("Press View", "The small button with two squares, left of centre -- works as Select"),
        "start": ("Press Menu", "The small button with three lines, right of centre -- works as Start"),
        "menu_toggle": ("Press the Xbox button", "The glowing Xbox logo at the top -- opens the emulator menu in a game"),
    },
    "playstation": {
        "b": ("Press ✕", "Cross, bottom of the four on the right"),
        "a": ("Press ○", "Circle, right of the four"),
        "y": ("Press □", "Square, left of the four"),
        "x": ("Press △", "Triangle, top of the four"),
        "l": ("Press L1", "The top edge, above the left trigger"),
        "r": ("Press R1", "The top edge, above the right trigger"),
        "l2": ("Pull L2", "The left trigger, under your left index finger"),
        "r2": ("Pull R2", "The right trigger, under your right index finger"),
        "select": ("Press Share / Create", "The small button left of the touchpad -- works as Select"),
        "start": ("Press Options", "The small button right of the touchpad -- works as Start"),
        "menu_toggle": ("Press the PS button", "The PS logo between the sticks -- opens the emulator menu in a game"),
    },
    "nintendo": {
        "b": ("Press B", "Bottom of the four on the right"),
        "a": ("Press A", "Right of the four"),
        "y": ("Press Y", "Left of the four"),
        "x": ("Press X", "Top of the four"),
        "l": ("Press L", "The top edge, above ZL"),
        "r": ("Press R", "The top edge, above ZR"),
        "l2": ("Press ZL", "The left trigger, under your left index finger"),
        "r2": ("Press ZR", "The right trigger, under your right index finger"),
        "select": ("Press −", "The minus button, left of centre -- works as Select"),
        "start": ("Press +", "The plus button, right of centre -- works as Start"),
        "menu_toggle": ("Press Home", "The round house button -- opens the emulator menu in a game"),
    },
}


def controller_brand(vendor):
    return PAD_BRANDS.get(vendor, "generic")


def step_text(key, title, hint, brand):
    return BRAND_STEP_TEXT.get(brand, {}).get(key, (title, hint))


# What each button on the player's pad does per system, as RetroPad keys
# (the CONTROLLER_STEPS keys, plus "dpad", "lstick" and "rstick"). Taken from
# each core's own input descriptors (the table RetroArch shows under Quick
# Menu > Controls), with the core's default options.
_PS_PAD = [("b", "✕"), ("a", "○"), ("y", "□"), ("x", "△"), ("dpad", "D-pad"),
           ("l", "L1"), ("r", "R1"), ("l2", "L2"), ("r2", "R2"), ("l3", "L3"), ("r3", "R3"),
           ("lstick", "Left stick"), ("rstick", "Right stick"), ("select", "Select"), ("start", "Start")]
SYSTEM_CONTROLS = {
    "nes": {"pad": "NES controller", "map": [
        ("b", "B"), ("a", "A"), ("y", "Turbo B"), ("x", "Turbo A"), ("dpad", "D-pad"),
        ("select", "Select"), ("start", "Start")]},
    "snes": {"pad": "Super Nintendo controller", "map": [
        ("b", "B"), ("a", "A"), ("y", "Y"), ("x", "X"), ("dpad", "D-pad"),
        ("l", "L"), ("r", "R"), ("select", "Select"), ("start", "Start")]},
    "gb": {"pad": "Game Boy", "map": [
        ("b", "B"), ("a", "A"), ("y", "Turbo B"), ("x", "Turbo A"), ("dpad", "D-pad"),
        ("select", "Select"), ("start", "Start")]},
    "gba": {"pad": "Game Boy Advance", "map": [
        ("b", "B"), ("a", "A"), ("y", "Turbo B"), ("x", "Turbo A"), ("dpad", "D-pad"),
        ("l", "L"), ("r", "R"), ("l2", "Turbo L"), ("r2", "Turbo R"),
        ("select", "Select"), ("start", "Start")]},
    "genesis": {"pad": "Genesis / Mega Drive 6-button pad", "map": [
        ("y", "A"), ("b", "B"), ("a", "C"), ("l", "X"), ("x", "Y"), ("r", "Z"), ("dpad", "D-pad"),
        ("select", "Mode"), ("start", "Start")],
     "note": "Master System and Game Gear use B as button 1 and C as button 2."},
    "dreamcast": {"pad": "Dreamcast controller", "map": [
        ("b", "A"), ("a", "B"), ("y", "X"), ("x", "Y"), ("dpad", "D-pad"), ("lstick", "Analog stick"),
        ("l2", "L trigger"), ("r2", "R trigger"), ("start", "Start")]},
    "n64": {"pad": "Nintendo 64 controller", "map": [
        ("b", "A"), ("y", "B"), ("l2", "Z"), ("l", "L"), ("r", "R"), ("dpad", "D-pad"),
        ("lstick", "Analog stick"), ("rstick", "C buttons"), ("r2", "Hold for C buttons"), ("start", "Start")],
     "note": "The C buttons are on the right stick. Holding the right trigger also turns the face buttons into C buttons."},
    "psx": {"pad": "PlayStation DualShock", "map": _PS_PAD},
    "ps2": {"pad": "PlayStation 2 DualShock 2", "map": _PS_PAD,
     "note": "PlayStation 2 runs in PCSX2, which sets these up on its own. Change them in Open PCSX2 settings."},
    "psp": {"pad": "PSP", "map": [
        ("b", "✕"), ("a", "○"), ("y", "□"), ("x", "△"), ("dpad", "D-pad"), ("lstick", "Analog stick"),
        ("l", "L"), ("r", "R"), ("select", "Select"), ("start", "Start")]},
    "nds": {"pad": "Nintendo DS", "map": [
        ("b", "B"), ("a", "A"), ("y", "Y"), ("x", "X"), ("dpad", "D-pad"), ("l", "L"), ("r", "R"),
        ("rstick", "Touch pointer"), ("r3", "Touch the screen"), ("r2", "Swap screens"),
        ("l2", "Blow into the microphone"), ("l3", "Close the lid"), ("select", "Select"), ("start", "Start")],
     "note": "You can also touch the screen with the mouse."},
    "gamecube": {"pad": "GameCube controller", "map": [
        ("b", "B"), ("a", "A"), ("y", "Y"), ("x", "X"), ("dpad", "D-pad"), ("lstick", "Control stick"),
        ("rstick", "C-stick"), ("l2", "L"), ("r2", "R"), ("r", "Z"), ("start", "Start")]},
    "3ds": {"pad": "Nintendo 3DS", "map": [],
     "note": "3DS runs in Azahar, which has its own button setup. Change it in Open Azahar settings."},
}

# The player's own button names, per brand.
PAD_BUTTON_NAMES = {
    "xbox": {"b": "A", "a": "B", "y": "X", "x": "Y", "l": "LB", "r": "RB", "l2": "LT", "r2": "RT",
             "select": "View", "start": "Menu", "menu_toggle": "Xbox button"},
    "playstation": {"b": "✕", "a": "○", "y": "□", "x": "△", "l": "L1", "r": "R1", "l2": "L2", "r2": "R2",
                    "select": "Share / Create", "start": "Options", "menu_toggle": "PS button"},
    "nintendo": {"b": "B", "a": "A", "y": "Y", "x": "X", "l": "L", "r": "R", "l2": "ZL", "r2": "ZR",
                 "select": "−", "start": "+", "menu_toggle": "Home"},
    "generic": {"b": "Bottom button", "a": "Right button", "y": "Left button", "x": "Top button",
                "l": "Left shoulder", "r": "Right shoulder", "l2": "Left trigger", "r2": "Right trigger",
                "select": "Select", "start": "Start", "menu_toggle": "Home"},
}
_COMMON_NAMES = {"dpad": "D-pad", "lstick": "Left stick", "rstick": "Right stick",
                 "l3": "Left stick click", "r3": "Right stick click"}


def saved_brand():
    """Brand of a controller set up earlier, for when none is connected."""
    for cfg in sorted(AUTOCONFIG_DIR.glob("ReyOS - *.cfg")):
        m = re.search(r'^input_vendor_id = "(\d+)"', cfg.read_text(errors="replace"), re.M)
        if m and controller_brand(int(m.group(1))) != "generic":
            return controller_brand(int(m.group(1)))
    return "generic"


def system_controls(brand):
    """Per-system button layout for the Gaming page: which button on the
    player's pad does what on each console."""
    names = {**_COMMON_NAMES, **PAD_BUTTON_NAMES.get(brand, PAD_BUTTON_NAMES["generic"])}
    out = []
    for system in EMU_SYSTEMS:
        spec = SYSTEM_CONTROLS.get(system["id"])
        if not spec:
            continue
        rows = [{"key": key, "console": label, "yours": names[key]} for key, label in spec["map"]]
        out.append({"id": system["id"], "name": system["name"], "pad": spec["pad"],
                    "note": spec.get("note", ""), "rows": rows,
                    "labels": {key: label for key, label in spec["map"]}})
    return out


class ControllerReader:
    """Reads one pad and turns the next press into a RetroArch bind:
    ("btn", "3"), ("btn", "h0up"), or ("axis", "+2")."""

    def __init__(self, path):
        self.fd, self.info = _open_pad(path)
        self.buttons, self.axes = _button_indices(self.info, self.fd)
        self.absinfo, self.rest = {}, {}
        for code in list(self.axes) + [c for c in range(ABS_HAT0X, ABS_HAT3Y + 1) if c in self.info["axes"]]:
            value, minimum, maximum = _absinfo(self.fd, code)
            self.absinfo[code] = (minimum, maximum)
            # A trigger rests at one end of its range, a stick in the middle.
            self.rest[code] = _norm(value, minimum, maximum) if code in self.axes else 0.0
        self.held = set()

    def close(self):
        os.close(self.fd)

    def _drain(self):
        events = []
        while True:
            try:
                data = os.read(self.fd, _EVENT.size * 64)
            except BlockingIOError:
                return events
            if not data:
                return events
            for off in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _s, _us, etype, code, value = _EVENT.unpack_from(data, off)
                events.append((etype, code, value))

    def _update_held(self, etype, code, value):
        if etype == EV_KEY:
            (self.held.add if value else self.held.discard)(("k", code))
        elif etype == EV_ABS and code in self.absinfo:
            if ABS_HAT0X <= code <= ABS_HAT3Y:
                moved = value != 0
            else:
                moved = abs(_norm(value, *self.absinfo[code]) - self.rest[code]) > 0.35
            (self.held.add if moved else self.held.discard)(("a", code))

    def wait_bind(self, stop, timeout=0.2):
        """Block until a fresh press (with everything else released first),
        `stop()` returns True, or the device goes away (OSError)."""
        armed = not self.held
        while not stop():
            ready, _, _ = select.select([self.fd], [], [], timeout)
            if not ready:
                continue
            for etype, code, value in self._drain():
                self._update_held(etype, code, value)
                if not armed:
                    armed = not self.held
                    continue
                bind = self._bind_for(etype, code, value)
                if bind:
                    return bind
        return None

    def _bind_for(self, etype, code, value):
        if etype == EV_KEY and value == 1 and code in self.buttons:
            return ("btn", str(self.buttons[code]))
        if etype != EV_ABS or code not in self.absinfo:
            return None
        if ABS_HAT0X <= code <= ABS_HAT3Y and value != 0:
            hat, vertical = divmod(code - ABS_HAT0X, 2)
            direction = ("up" if value < 0 else "down") if vertical else ("left" if value < 0 else "right")
            return ("btn", f"h{hat}{direction}")
        if code in self.axes:
            delta = _norm(value, *self.absinfo[code]) - self.rest[code]
            if abs(delta) > 0.6:
                return ("axis", f"{'+' if delta > 0 else '-'}{self.axes[code]}")
        return None


def write_profile(info, binds):
    """RetroArch udev autoconfig profile, matched on vendor/product id and
    device name. `binds` maps a CONTROLLER_STEPS key to (kind, value)."""
    lines = [
        "# Written by ReyOS Control Center > Gaming > Set up controller",
        'input_driver = "udev"',
        f'input_device = "{info["name"]}"',
        f'input_vendor_id = "{info["vendor"]}"',
        f'input_product_id = "{info["product"]}"',
    ]
    for key, (kind, value) in binds.items():
        if key in ("l_x", "l_y", "r_x", "r_y"):
            if kind != "axis":
                continue
            flipped = ("-" if value[0] == "+" else "+") + value[1:]
            lines.append(f'input_{key}_plus_axis = "{value}"')
            lines.append(f'input_{key}_minus_axis = "{flipped}"')
        else:
            lines.append(f'input_{key}_{kind} = "{value}"')
    path = profile_path(info["name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


# ---- Game library and box art ------------------------------------------------
BOXART_CACHE = Path.home() / ".cache" / "reyos" / "boxart"
THUMBNAILS_URL = "https://thumbnails.libretro.com"
_COVER_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def scan_games(system):
    for folder in rom_dirs(system):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in system["exts"]:
                yield path


def game_title(path):
    # "Rayman 2_ The Great Escape (USA) (En,Fr)" -> "Rayman 2 The Great Escape";
    # the system is shown next to the title anyway.
    title = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", path.stem)
    title = re.sub(r"\s+", " ", re.sub(r"[_.]+", " ", title)).strip()
    return title or path.stem


def local_cover(system, rom):
    """A cover the user supplied (same name as the game, next to it or in
    ~/Games/Covers/<system>/) wins; then the downloaded box art."""
    rom = Path(rom)
    for base in (rom.with_suffix(""), GAMES_DIR / "Covers" / system["id"] / rom.stem):
        for ext in _COVER_EXTS:
            if base.with_name(base.name + ext).is_file():
                return str(base.with_name(base.name + ext))
    cached = BOXART_CACHE / system["id"] / (rom.stem + ".png")
    return str(cached) if cached.is_file() and cached.stat().st_size > 0 else ""


def _norm_title(name):
    name = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", name)
    name = re.sub(r"^the\s+|,\s*the\b", " ", name.lower())
    return re.sub(r"[^a-z0-9]+", "", name)


def _thumb_index(folder):
    """File names in one libretro-thumbnails Named_Boxarts folder, cached
    for 30 days (one listing request per system instead of guessing)."""
    cache = BOXART_CACHE / "_index" / (folder + ".txt")
    if cache.is_file() and time.time() - cache.stat().st_mtime < 30 * 86400:
        return cache.read_text().splitlines()
    url = f"{THUMBNAILS_URL}/{urllib.parse.quote(folder)}/Named_Boxarts/"
    with urllib.request.urlopen(url, timeout=30) as resp:
        html = resp.read().decode("utf-8", "replace")
    names = [urllib.parse.unquote(n) for n in re.findall(r'href="([^"/?]+\.png)"', html)]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n".join(names))
    return names


_REGION_ORDER = ("(USA)", "(USA, Europe)", "(World)", "(Europe)", "(Japan)")


def _best_match(title, names):
    key = _norm_title(title)
    if not key:
        return None
    hits = [n for n in names if _norm_title(n[:-4]) == key]
    if not hits:
        return None
    # Prefer the release sharing the file's own tags (region, revision),
    # then a plain regional release over demos, betas and revisions.
    own = set(re.findall(r"\([^)]*\)", title))
    def rank(n):
        shared = len(own & set(re.findall(r"\([^)]*\)", n)))
        region = next((i for i, r in enumerate(_REGION_ORDER) if r in n), len(_REGION_ORDER))
        return (-shared, region, n.count("("), len(n))
    return min(hits, key=rank)


def fetch_cover(system, rom):
    """Download box art for one game into the cache. Returns the cover path,
    or "" when none was found (remembered with an empty file, so a game
    with no box art isn't looked up again on every visit)."""
    rom = Path(rom)
    target = BOXART_CACHE / system["id"] / (rom.stem + ".png")
    if target.exists():
        return str(target) if target.stat().st_size > 0 else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    for folder in system.get("thumbs", []):
        match = _best_match(rom.stem, _thumb_index(folder))
        if match:
            url = f"{THUMBNAILS_URL}/{urllib.parse.quote(folder)}/Named_Boxarts/{urllib.parse.quote(match)}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                tmp = target.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.replace(target)
                return str(target)
    target.write_bytes(b"")
    return ""
