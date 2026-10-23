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
import threading
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
# RetroArch's slang shaders (Arch: libretro-shaders-slang). Slang shaders run on
# the glcore video driver, so shader looks switch the driver to glcore; plain
# looks and all 3D systems stay on gl, the driver known to work everywhere.
SHADER_DIR = Path("/usr/share/libretro/shaders/shaders_slang")
PICTURE_SHADERS = {"clean": "pixel-art-scaling/sharp-bilinear.slangp", "lcd": "handheld/lcd3x.slangp"}
TWO_D_SYSTEMS = {"nes", "snes", "gb", "gba", "genesis"}
LAUNCH_LOG = Path.home() / ".cache" / "reyos" / "retroarch-last.log"
MANGOHUD_USER_CFG = Path.home() / ".config" / "MangoHud" / "MangoHud.conf"
MANGOHUD_COMPACT = ("legacy_layout=0,hud_compact,position=top-right,font_size=18,background_alpha=0.3,"
                    "fps,cpu_stats,gpu_stats,frame_timing=0,custom_text=Right Shift+F12 hides this")
AUTOCONFIG_DIR = Path.home() / ".config" / "retroarch" / "autoconfig" / "udev"
DOLPHIN_SYS = Path("/usr/share/dolphin-emu/sys")
FLATHUB_URL = "https://flathub.org/repo/flathub.flatpakrepo"
PCSX2_INI = Path.home() / ".var" / "app" / "net.pcsx2.PCSX2" / "config" / "PCSX2" / "inis" / "PCSX2.ini"
PCSX2_LAUNCHER = "/usr/share/reyos/control-center/reyos-pcsx2"
PCSX2_DESKTOP = "net.pcsx2.PCSX2.desktop"
PCSX2_EXPORTS = [Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
                 Path("/var/lib/flatpak/exports/share/applications")]
PCSX2_OVERRIDE = Path.home() / ".local" / "share" / "applications" / PCSX2_DESKTOP


def rom_dirs(system):
    return [GAMES_DIR / "ROMs" / d for d in system.get("dirs", [system["id"]])]


def storage_system_dir(root, folder):
    """A console's folder inside the "Added games are kept in" folder. When
    that folder is itself a console's folder (…/Games/ps2), it's used as is
    and the other consoles get a folder next to it, never …/ps2/ps2."""
    root = Path(root)
    name = root.name.lower()
    if name == folder.lower():
        return root
    if name in {d.lower() for s in EMU_SYSTEMS for d in s.get("dirs", [s["id"]])}:
        return root.parent / folder
    return root / folder


def library_dirs(system, settings=None):
    """~/Games/ROMs/<system> plus the same console's folder in the "Added
    games are kept in" folder, so games already there show up too."""
    dirs = list(rom_dirs(system))
    storage = (settings or load_settings())["game_storage"]
    if storage:
        dirs += [storage_system_dir(storage, d) for d in system.get("dirs", [system["id"]])]
    return dirs


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
DEFAULT_SETTINGS = {"fullscreen": True, "overlay": True, "picture": "clean", "resolution": 1, "ps2_graphics": True, "windowed_games": [], "expanded": None, "bios_expanded": False, "boxart": True, "game_storage": "", "game_resolution": {}, "pad_types": {}, "player1": "", "button_maps": {}, "ps2_pad_written": {}, "azahar_written": {}, "ps2_vulkan_written": False, "pc_builtin_gpu": [], "game_gpu": "nvidia", "pc_gpu": {}}

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
    # Only per game (library right-click): Control Center offers 1x/2x/4x.
    # Beetle PSX has no 3x, so PS1 gets 2x there.
    3: {"mupen64plus-EnableNativeResFactor": "3", "beetle_psx_internal_resolution": "2x",
        "ppsspp_internal_resolution": "1440x816", "melonds_opengl_renderer": "enabled",
        "melonds_opengl_resolution": "3x native (768x576)", "dolphin_efb_scale": "3",
        "reicast_internal_resolution": "1920x1440"},
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
    if settings["picture"] not in ("clean", "sharp", "fill", "smooth", "lcd"):
        settings["picture"] = "fill"
    if settings["resolution"] not in RESOLUTION_OPTIONS:
        settings["resolution"] = 1
    if not isinstance(settings["windowed_games"], list):
        settings["windowed_games"] = []
    if not isinstance(settings["game_resolution"], dict):
        settings["game_resolution"] = {}
    if settings["game_gpu"] not in ("nvidia", "builtin"):
        settings["game_gpu"] = "nvidia"
    if not isinstance(settings["pc_gpu"], dict):
        settings["pc_gpu"] = {}
    if not isinstance(settings["pc_builtin_gpu"], list):
        settings["pc_builtin_gpu"] = []
    for key in ("pad_types", "button_maps", "ps2_pad_written", "azahar_written"):
        if not isinstance(settings[key], dict):
            settings[key] = {}
    return settings


# Systems whose games have a 3D resolution (the library's per-game choice).
THREE_D_SYSTEMS = {"n64", "psx", "ps2", "psp", "nds", "dreamcast", "gamecube"}


def game_resolution(path, settings=None):
    """This game's own 3D resolution from the library's right-click menu,
    or None to follow Control Center's."""
    value = (settings or load_settings())["game_resolution"].get(str(path))
    return value if value in RESOLUTION_OPTIONS else None


def set_game_resolution(path, value):
    games = dict(load_settings()["game_resolution"])
    games.pop(str(path), None)
    if value in RESOLUTION_OPTIONS:
        games[str(path)] = value
    save_settings({"game_resolution": games})


def game_fullscreen(path, settings=None):
    """Full screen for this game: the Display switch, unless the game is in
    the library's "Always play in a window" list."""
    settings = settings or load_settings()
    return bool(settings["fullscreen"]) and str(path) not in settings["windowed_games"]


def set_game_windowed(path, windowed):
    games = [g for g in load_settings()["windowed_games"] if g != str(path)]
    if windowed:
        games.append(str(path))
    save_settings({"windowed_games": games})


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


def shader_for(system_id, settings=None):
    """Absolute shader preset for this system, or None (plain picture)."""
    settings = settings or load_settings()
    rel = PICTURE_SHADERS.get(settings["picture"])
    if rel and system_id in TWO_D_SYSTEMS and (SHADER_DIR / rel).is_file():
        return SHADER_DIR / rel
    return None


# What prime-run sets: start a program on a laptop's NVIDIA card.
NVIDIA_OFFLOAD_ENV = {"__NV_PRIME_RENDER_OFFLOAD": "1", "__VK_LAYER_NV_optimus": "NVIDIA_only",
                      "__GLX_VENDOR_LIBRARY_NAME": "nvidia"}


def nvidia_present():
    """A laptop with an NVIDIA card next to built-in Intel/AMD graphics."""
    vendors = set()
    for dev in Path("/sys/bus/pci/devices").glob("*"):
        try:
            if int((dev / "class").read_text(), 16) >> 16 == 0x03:
                vendors.add((dev / "vendor").read_text().strip())
        except (OSError, ValueError):
            pass
    return "0x10de" in vendors and bool(vendors & {"0x8086", "0x1002"})


def nvidia_offload_ready():
    """nvidia_present() and the card runs NVIDIA's driver: a game can be
    started on the NVIDIA card."""
    return Path("/sys/module/nvidia").exists() and nvidia_present()


def games_use_nvidia(settings=None):
    """Games go to the NVIDIA card: it's usable and the Gaming page's
    "Graphics card for games" isn't set to the built-in graphics."""
    return nvidia_offload_ready() and (settings or load_settings())["game_gpu"] != "builtin"


def nvidia_flatpak_extensions():
    """Flatpak's copies of the loaded NVIDIA driver (64- and 32-bit), e.g.
    org.freedesktop.Platform.GL.nvidia-580-178-04; [] without the driver.
    A Flatpak app can only use the NVIDIA card when these match the host's."""
    try:
        version = Path("/sys/module/nvidia/version").read_text().strip().replace(".", "-")
    except OSError:
        return []
    return [f"org.freedesktop.Platform.{gl}.nvidia-{version}" for gl in ("GL", "GL32")]


def pcsx2_on_nvidia():
    ext = nvidia_flatpak_extensions()
    return games_use_nvidia() and bool(ext) and any(
        (d / "runtime" / ext[0]).is_dir() for d in (Path.home() / ".local/share/flatpak", Path("/var/lib/flatpak")))


def gpu_is_weak():
    """True without a dedicated GPU the 3D cores can lean on: only integrated
    Intel graphics, a VM, or an NVIDIA card too old for the current driver
    (it runs on nouveau). 4x internal resolution is capped to 2x there."""
    try:
        out = subprocess.run(["/usr/share/reyos/bin/reyos-gpu-detect", "--json"],
                             capture_output=True, text=True, timeout=10).stdout
        gpus = json.loads(out)
    except Exception:
        return False
    return not any(g["vendor"] == "amd" or (g["vendor"] == "nvidia" and g.get("nvidiaOpenSupported")) for g in gpus)


def write_retroarch_cfg(settings=None, system_id=None, fullscreen=None, resolution=None):
    """The small config ReyOS appends at launch (--appendconfig), so the
    user's own ~/.config/retroarch/retroarch.cfg is never rewritten. Core
    options go to a ReyOS-owned file for the same reason. resolution: the
    game's own 3D resolution (library right-click), used as chosen."""
    settings = settings or load_settings()
    REYOS_CFG_DIR.mkdir(parents=True, exist_ok=True)
    picture = settings["picture"]
    use_shader = system_id is not None and shader_for(system_id, settings) is not None
    values = {
        "system_directory": BIOS_DIR,
        "savefile_directory": GAMES_DIR / "Saves",
        "savestate_directory": GAMES_DIR / "Saves" / "states",
        "rgui_browser_directory": GAMES_DIR / "ROMs",
        "video_fullscreen": "true" if (settings["fullscreen"] if fullscreen is None else fullscreen) else "false",
        "video_scale_integer": "true" if picture in ("sharp", "lcd") else "false",
        "video_smooth": "true" if picture == "smooth" else "false",
        # A windowed game opens at 3x the core's picture size, and cores that
        # render above native (PSP at 960x544, N64/PS1 at 2x/4x) then ask for
        # more than the screen and fill it. Cap the window at 1280x720; the
        # aspect ratio is kept and it can still be resized or maximised.
        "video_window_auto_width_max": "1280",
        "video_window_auto_height_max": "720",
        # Always set: a Vulkan driver picked once in RetroArch's own menu is
        # saved on exit, and on a machine without a Vulkan device every game
        # then dies on launch (found on the first real-hardware install).
        "video_driver": "glcore" if use_shader else "gl",
        "video_shader_enable": "true" if use_shader else "false",
        "input_joypad_driver": "udev",
        # Start + Select opens RetroArch's menu (Quit is in there) so a
        # controller alone can leave a game; the Home button does too once
        # it's been set up.
        "input_menu_toggle_gamepad_combo": "4",
        "global_core_options": "true",
        "core_options_path": CORE_OPTIONS_CFG,
        # Player 1 = the controller chosen on the Gaming page, matched by
        # vendor:product, whatever order the pads were connected in
        # ("Preferred": another pad takes over when it isn't connected).
        # Button layouts are Control Center's (per-core remap files it
        # writes). RetroArch saving the remap it has loaded on exit wrote a
        # just-reset swap back, unmarked, which then counted as "made in
        # RetroArch" and blocked every later change.
        "remap_save_on_exit": "false",
        "input_player1_device_reservation_type": "0",
        "input_player1_reserved_device": "",
    }
    # Player 1's controller buttons come from the Control Center setup
    # (the autoconfig profile). A controller bind left in retroarch.cfg
    # (RetroArch saves its whole config on exit) would override it -- seen
    # as a swapped A/B on a PlayStation-mode pad. Keyboard keys are other
    # settings and stay.
    for key in ("b", "y", "select", "start", "up", "down", "left", "right", "a", "x", "l", "r",
                "l2", "r2", "l3", "r3", "l_x_plus", "l_x_minus", "l_y_plus", "l_y_minus",
                "r_x_plus", "r_x_minus", "r_y_plus", "r_y_minus"):
        values[f"input_player1_{key}_btn"] = "nul"
        values[f"input_player1_{key}_axis"] = "nul"
    pad = player1_pad()
    if pad is not None:
        values["input_player1_device_reservation_type"] = "1"
        values["input_player1_reserved_device"] = f'{pad["vendor"]:04x}:{pad["product"]:04x} {pad["name"]}'
    RETROARCH_REYOS_CFG.write_text("".join(f'{k} = "{v}"\n' for k, v in values.items()))
    if resolution in RESOLUTION_OPTIONS:
        _set_cfg_values(CORE_OPTIONS_CFG, RESOLUTION_OPTIONS[resolution])
        return
    resolution = settings["resolution"]
    options = dict(RESOLUTION_OPTIONS[2 if resolution > 2 and gpu_is_weak() else resolution])
    # PSP keeps the chosen resolution: PPSSPP at 4x ran God of War at a
    # steady 60 FPS with the Intel HD 630 about half busy.
    options["ppsspp_internal_resolution"] = RESOLUTION_OPTIONS[resolution]["ppsspp_internal_resolution"]
    _set_cfg_values(CORE_OPTIONS_CFG, options)


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


def prepare_flatpak(system, resolution=None):
    """PCSX2's Flatpak has no access to your files: give it ~/Games (the BIOS
    folder needs write access, PCSX2 keeps its NVRAM next to the BIOS), and
    point it at ~/Games/BIOS/ps2 and ~/Games/ROMs/ps2 so the setup wizard is
    skipped. Only adds settings that are missing, so changes made in PCSX2
    itself are kept."""
    _grant_game_folders(system)
    if system["id"] == "3ds":
        _write_azahar_controls()
        return
    if system["id"] != "ps2":
        return
    new = not PCSX2_INI.exists()
    lines = [] if new else PCSX2_INI.read_text(errors="replace").splitlines()
    before = list(lines)
    # Without SettingsVersion PCSX2 calls the file invalid and offers to reset
    # it, which throws away the BIOS folder (ReyOS wrote files like that
    # before 1.0.0-117).
    _ini_default(lines, "UI", "SettingsVersion", "1")
    if new:
        _ini_default(lines, "UI", "SetupWizardIncomplete", "false")
    _ini_default(lines, "Folders", "Bios", str(BIOS_DIR / "ps2"))
    # After a reset PCSX2 is back on its own empty "bios" folder and runs the
    # setup wizard; point it at ReyOS's folder again.
    own_bios = PCSX2_INI.parent.parent / "bios"
    if _ini_get(lines, "Folders", "Bios") == "bios" and not (own_bios.is_dir() and any(own_bios.iterdir())):
        _ini_set(lines, "Folders", "Bios", str(BIOS_DIR / "ps2"))
        _ini_set(lines, "UI", "SetupWizardIncomplete", "false")
    _ini_default(lines, "GameList", "RecursivePaths", str(GAMES_DIR / "ROMs" / "ps2"))
    # MangoHud can't reach into the Flatpak; PCSX2's own on-screen display
    # shows the same numbers and follows the overlay switch.
    settings = load_settings()
    overlay = "true" if settings["overlay"] else "false"
    for key in ("OsdShowFPS", "OsdShowSpeed", "OsdShowCPU", "OsdShowGPU"):
        _ini_set(lines, "EmuCore/GS", key, overlay)
    if settings["ps2_graphics"]:
        _apply_pcsx2_graphics(lines, settings, resolution)
    _apply_pcsx2_gpu(lines, settings)
    _map_pcsx2_controller(lines)
    if lines != before:
        PCSX2_INI.parent.mkdir(parents=True, exist_ok=True)
        PCSX2_INI.write_text("\n".join(lines) + "\n")
    sync_pcsx2_launcher()


def _grant_game_folders(system):
    """A Flatpak emulator only sees folders it's been given: ~/Games, the
    "Added games are kept in" folder, and wherever the library's links
    point (another partition, an external drive), read-only."""
    folders = {f"{GAMES_DIR}"}
    storage = load_settings()["game_storage"]
    if storage and not Path(storage).is_relative_to(GAMES_DIR):
        folders.add(f"{storage}:ro")
    for folder in rom_dirs(system):
        for link in (folder.iterdir() if folder.is_dir() else []):
            if link.is_symlink():
                target = Path(os.path.realpath(link)).parent
                if not target.is_relative_to(GAMES_DIR):
                    while not os.path.ismount(target) and target.parent != target:
                        target = target.parent
                    if target != Path("/"):
                        folders.add(f"{target}:ro")
    subprocess.run(["flatpak", "override", "--user", *[f"--filesystem={f}" for f in sorted(folders)], system["flatpak"]],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def sync_pcsx2_launcher():
    """PCSX2 opened from its own menu entry skipped prepare_flatpak (setup
    wizard, no BIOS). A same-named entry in ~/.local/share/applications hides
    Flathub's and runs PCSX2 through reyos-pcsx2, which prepares it first.
    Removed again when PCSX2 is gone. An entry the user made is left alone."""
    ours = PCSX2_OVERRIDE.exists() and "X-ReyOS-Launcher=true" in PCSX2_OVERRIDE.read_text(errors="replace")
    if PCSX2_OVERRIDE.exists() and not ours:
        return
    exported = next((d / PCSX2_DESKTOP for d in PCSX2_EXPORTS if (d / PCSX2_DESKTOP).exists()), None)
    if exported is None:
        if ours:
            PCSX2_OVERRIDE.unlink()
        return
    text = re.sub(r"^(Exec=).*?net\.pcsx2\.PCSX2(?=\s|$)", lambda m: m.group(1) + PCSX2_LAUNCHER,
                  exported.read_text(errors="replace"), flags=re.M)
    text = re.sub(r"^TryExec=.*\n", "", text, flags=re.M)
    text = text.replace("[Desktop Entry]\n", "[Desktop Entry]\nX-ReyOS-Launcher=true\n", 1)
    if not ours or PCSX2_OVERRIDE.read_text(errors="replace") != text:
        PCSX2_OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
        PCSX2_OVERRIDE.write_text(text)


def _apply_pcsx2_graphics(lines, settings, resolution=None):
    """Control Center's Display settings replace PCSX2's own graphics
    settings ("Also use for PlayStation 2" switch): 3D resolution, sharp
    (integer) scaling and full screen when PCSX2 is opened on its own. The
    aspect ratio stays PCSX2's (stretching PS2 games to 16:9 distorts them).
    No 4x -> 2x cap here: PCSX2 runs 4x fine on Intel HD 630, and the
    resolution the user picked is what they expect to see in PCSX2."""
    picture = settings["picture"]
    # A game's own resolution (library right-click) is written here at its
    # launch; PCSX2's per-game files need a CRC known only once it runs.
    _ini_set(lines, "EmuCore/GS", "upscale_multiplier", str(resolution or settings["resolution"]))
    _ini_set(lines, "EmuCore/GS", "IntegerScaling", "true" if picture in ("sharp", "lcd") else "false")
    _ini_set(lines, "UI", "StartFullscreen", "true" if settings["fullscreen"] else "false")


def _apply_pcsx2_gpu(lines, settings):
    """On a laptop with a usable NVIDIA card PCSX2 runs on Vulkan, where the
    offload variables (launch_command) put it on the NVIDIA card; Automatic
    picks OpenGL, which stays on the built-in graphics. Only Automatic or
    OpenGL is changed, and it goes back to Automatic when the card isn't
    usable any more. An adapter picked in PCSX2 that isn't the NVIDIA card
    is cleared: with the offload on, Vulkan lists the NVIDIA card first and
    PCSX2's default adapter is the first one (checked inside the Flatpak)."""
    renderer = _ini_get(lines, "EmuCore/GS", "Renderer")
    if pcsx2_on_nvidia():
        if renderer in (None, "", "-1", "12"):  # Automatic, OpenGL
            _ini_set(lines, "EmuCore/GS", "Renderer", "14")  # Vulkan
            save_settings({"ps2_vulkan_written": True})
        adapter = _ini_get(lines, "EmuCore/GS", "Adapter") or ""
        if adapter and "nvidia" not in adapter.lower():
            _ini_set(lines, "EmuCore/GS", "Adapter", "")
    elif settings["ps2_vulkan_written"] and renderer == "14":
        _ini_set(lines, "EmuCore/GS", "Renderer", "-1")
        save_settings({"ps2_vulkan_written": False})


def pcsx2_run_args():
    """`flatpak run` options that start PCSX2 on the NVIDIA card when it's usable."""
    return [f"--env={k}={v}" for k, v in NVIDIA_OFFLOAD_ENV.items()] if pcsx2_on_nvidia() else []


# Pad 1 bound to the first controller the way PCSX2's own "Automatic
# Mapping" does it for a standard pad. Binding names checked against
# pcsx2-qt v2.8.2; Pad 1 key names from a PCSX2-written PCSX2.ini.
PCSX2_PAD_SDL = {
    "Up": "DPadUp", "Down": "DPadDown", "Left": "DPadLeft", "Right": "DPadRight",
    "Cross": "FaceSouth", "Circle": "FaceEast", "Square": "FaceWest", "Triangle": "FaceNorth",
    "L1": "LeftShoulder", "R1": "RightShoulder", "L2": "+LeftTrigger", "R2": "+RightTrigger",
    "L3": "LeftStick", "R3": "RightStick", "Select": "Back", "Start": "Start", "Analog": "Guide",
    "LUp": "-LeftY", "LDown": "+LeftY", "LLeft": "-LeftX", "LRight": "+LeftX",
    "RUp": "-RightY", "RDown": "+RightY", "RLeft": "-RightX", "RRight": "+RightX",
    "LargeMotor": "LargeMotor", "SmallMotor": "SmallMotor",
}


def controller_connected():
    return any(Path("/sys/class/input").glob("js*"))


def _map_pcsx2_controller(lines):
    """PCSX2 keeps Pad 1 on the keyboard even with a controller connected
    (seen with an Xbox pad on the real laptop). When a controller is plugged
    in and Pad 1 is still on the keyboard or bound the way ReyOS binds it
    (nothing remapped in PCSX2), bind Pad 1 to the player 1 controller.
    PCSX2 only knows controllers by number (SDL-<n>, in connection order),
    so the chosen pad's place among the connected ones is used. Without a
    controller the keyboard keys stay."""
    pads = list_controllers()
    if not pads:
        return
    settings = load_settings()
    current = {key: _ini_get(lines, "Pad1", key) for key in PCSX2_PAD_SDL}
    keyboard = all(not v or v.startswith("Keyboard/") for v in current.values())
    written = settings["ps2_pad_written"]
    ours = any(current == _pcsx2_pad_binds(i, m) for i in range(4) for m in (written, {}))
    if not (keyboard or ours):
        return  # remapped in PCSX2 itself: leave it
    pad = player1_pad(pads)
    index = pads.index(pad) if pad is not None else 0
    m = {k: v for k, v in button_map("ps2", settings).items() if k != v}
    _ini_default(lines, "InputSources", "SDL", "true")
    _ini_default(lines, "Pad1", "Type", "DualShock2")
    for key, value in _pcsx2_pad_binds(index, m).items():
        _ini_set(lines, "Pad1", key, value)
    if m != written:
        save_settings({"ps2_pad_written": m})


# ---- Azahar (3DS) controls from the ReyOS controller setup ---------------
AZAHAR_INI = Path.home() / ".var" / "app" / "org.azahar_emu.Azahar" / "config" / "azahar-emu" / "qt-config.ini"
# Azahar's button names by the RetroPad key whose bind they take.
AZAHAR_BUTTONS = {"button_a": "a", "button_b": "b", "button_x": "x", "button_y": "y", "button_l": "l",
                  "button_r": "r", "button_zl": "l2", "button_zr": "r2", "button_start": "start",
                  "button_select": "select", "button_home": "menu_toggle", "button_up": "up",
                  "button_down": "down", "button_left": "left", "button_right": "right"}


def sdl_guid(pad):
    """The GUID SDL gives a Linux joystick (Azahar matches pads by it): bus,
    CRC-16 of the name, vendor, product, version, little-endian."""
    crc = 0
    for byte in pad["name"].encode():
        r, c = (crc ^ byte) & 0xFF, 0
        for _ in range(8):
            c = (0xA001 if (c ^ r) & 1 else 0) ^ (c >> 1)
            r >>= 1
        crc = c ^ (crc >> 8)
    return struct.pack("<8H", pad["bus"], crc, pad["vendor"], 0, pad["product"], 0, pad["version"], 0).hex()


def _profile_binds(name):
    try:
        text = profile_path(name).read_text(errors="replace")
    except OSError:
        return {}
    return dict(re.findall(r'^input_(\w+) = "(.*)"', text, re.M))


def _azahar_bind(binds, key, guid):
    """One Azahar input string from the ReyOS profile's bind for RetroPad key."""
    base = f"engine:sdl,guid:{guid},port:0"
    if f"{key}_btn" in binds:
        value = binds[f"{key}_btn"]
        m = re.fullmatch(r"h(\d)(up|down|left|right)", value)
        return f"direction:{m.group(2)},{base},hat:{m.group(1)}" if m else f"button:{value},{base}"
    if f"{key}_axis" in binds:
        value = binds[f"{key}_axis"]
        return f"axis:{value[1:]},direction:{value[0]},{base},threshold:0.500000"
    return None


def _write_azahar_controls():
    """Player 1 of Azahar = the player 1 controller, bound the way it was set
    up in Control Center, with the Gaming page's 3DS button layout. Only
    while Azahar's controls are its keyboard defaults or what ReyOS wrote
    last: a layout made in Azahar itself is kept."""
    pads = list_controllers()
    pad = player1_pad(pads) or next((p for p in pads if p["configured"]), None)
    if pad is None or not AZAHAR_INI.exists():
        return
    binds = _profile_binds(pad["name"])
    if not binds:
        return
    guid = sdl_guid(pad)
    m = button_map("3ds")
    want = {}
    for name, key in AZAHAR_BUTTONS.items():
        value = _azahar_bind(binds, m.get(key, key), guid)
        if value:
            want[name] = value
    for name, (x, y) in (("circle_pad", ("l_x_plus_axis", "l_y_plus_axis")), ("c_stick", ("r_x_plus_axis", "r_y_plus_axis"))):
        if x in binds and y in binds:
            want[name] = f"axis_x:{binds[x][1:]},axis_y:{binds[y][1:]},deadzone:0.100000,{f'engine:sdl,guid:{guid},port:0'}"
    lines = AZAHAR_INI.read_text(errors="replace").splitlines()
    settings = load_settings()
    written = settings["azahar_written"]

    def get(key):
        for line in lines:
            if line.startswith(f"profiles\\1\\{key}="):
                return line.split("=", 1)[1].strip('"')
        return None

    def is_default(key):
        return f"profiles\\1\\{key}\\default=true" in lines
    for name in want:
        if not (is_default(name) or get(name) in (None, written.get(name))):
            return  # changed in Azahar itself
    for name, value in want.items():
        for suffix, text in (("", f'"{value}"'), ("\\default", "false")):
            key = f"profiles\\1\\{name}{suffix}"
            idx = next((i for i, l in enumerate(lines) if l.startswith(key + "=")), None)
            if idx is None:
                section = lines.index("[Controls]") if "[Controls]" in lines else None
                if section is None:
                    lines += ["", "[Controls]"]
                    section = len(lines) - 1
                lines.insert(section + 1, f"{key}={text}")
            else:
                lines[idx] = f"{key}={text}"
    AZAHAR_INI.write_text("\n".join(lines) + "\n")
    if want != written:
        save_settings({"azahar_written": want})


# ---- Windows games: SDL controller mapping from the ReyOS controller setup -
# SDL's names for the RetroPad keys (SDL's "a" is the bottom face button).
SDL_BUTTONS = {"b": "a", "a": "b", "y": "x", "x": "y", "l": "leftshoulder", "r": "rightshoulder",
               "l2": "lefttrigger", "r2": "righttrigger", "select": "back", "start": "start",
               "l3": "leftstick", "r3": "rightstick", "menu_toggle": "guide",
               "up": "dpup", "down": "dpdown", "left": "dpleft", "right": "dpright"}
SDL_STICKS = {"leftx": "l_x_plus_axis", "lefty": "l_y_plus_axis", "rightx": "r_x_plus_axis", "righty": "r_y_plus_axis"}
_SDL_HAT = {"up": 1, "right": 2, "down": 4, "left": 8}


def sdl_mapping(pad, m):
    """An SDL_GAMECONTROLLERCONFIG line for this pad from its ReyOS profile
    (the setup's button/axis numbers are the ones SDL uses on Linux, as for
    Azahar), with layout m ({console key: pad key}) applied: the game's
    button k comes from the pad's button m[k]. None without a profile."""
    binds = _profile_binds(pad["name"])
    if not binds:
        return None
    sticks = {binds[k][1:] for k in SDL_STICKS.values() if k in binds}
    parts = [sdl_guid(pad), pad["name"].replace(",", " "), "platform:Linux"]
    for key, target in SDL_BUTTONS.items():
        source = m.get(key, key)
        if f"{source}_btn" in binds:
            value = binds[f"{source}_btn"]
            hat = re.fullmatch(r"h(\d)(up|down|left|right)", value)
            parts.append(f"{target}:h{hat.group(1)}.{_SDL_HAT[hat.group(2)]}" if hat else f"{target}:b{value}")
        elif f"{source}_axis" in binds and binds[f"{source}_axis"][1:] not in sticks:
            # (A stick axis here is a setup slip, e.g. the stick moved while clicking it.)
            parts.append(f"{target}:a{binds[f'{source}_axis'][1:]}")
    for target, key in SDL_STICKS.items():
        if key in binds:
            value = binds[key]
            parts.append(f"{target}:a{value[1:]}{'~' if value[0] == '-' else ''}")
    return ",".join(parts) + ","


# PS2 pad buttons by RetroPad key (how SYSTEM_CONTROLS names them).
PS2_PAD_KEYS = {"b": "Cross", "a": "Circle", "y": "Square", "x": "Triangle", "l": "L1", "r": "R1",
                "l2": "L2", "r2": "R2", "select": "Select", "start": "Start", "l3": "L3", "r3": "R3"}


def _pcsx2_pad_binds(index, m):
    """PCSX2 Pad 1 bindings for controller SDL-<index>, with the Gaming
    page's button layout m ({console key: pad key}) applied."""
    binds = {key: f"SDL-{index}/{control}" for key, control in PCSX2_PAD_SDL.items()}
    for console, pad in m.items():
        if console in PS2_PAD_KEYS and pad in PS2_PAD_KEYS:
            binds[PS2_PAD_KEYS[console]] = f"SDL-{index}/{PCSX2_PAD_SDL[PS2_PAD_KEYS[pad]]}"
    return binds


def _ini_find(lines, section, key):
    """(index of the [section] header or None, index of the key line or None)."""
    header, start = f"[{section}]", None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
        elif start is not None and line.startswith("["):
            break
        elif start is not None and line.split("=", 1)[0].strip() == key:
            return start, i
    return start, None


def _ini_get(lines, section, key):
    _, i = _ini_find(lines, section, key)
    return None if i is None else lines[i].split("=", 1)[1].strip()


def _ini_set(lines, section, key, value):
    _, i = _ini_find(lines, section, key)
    if i is None:
        _ini_default(lines, section, key, value)
    else:
        lines[i] = f"{key} = {value}"


def _ini_default(lines, section, key, value):
    """Add `key = value` to [section] of an INI file's lines unless the key
    is already there, creating the section if needed."""
    start, found = _ini_find(lines, section, key)
    if found is not None:
        return
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"[{section}]", f"{key} = {value}"]
    else:
        lines.insert(start + 1, f"{key} = {value}")


def _ps2_disc(rom):
    """PCSX2 can't open a .cue ("Unable to identify the ISO image type") but
    reads the .bin it points to, so hand it the first FILE of the cue. The
    library still lists the .cue, so a bin/cue game shows up once."""
    rom = Path(rom)
    if rom.suffix.lower() != ".cue":
        return str(rom)
    try:
        text = rom.read_text(errors="replace")
    except OSError:
        return str(rom)
    match = re.search(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', text, re.MULTILINE | re.IGNORECASE)
    if match:
        disc = rom.parent / (match.group(1) or match.group(2))
        if disc.is_file():
            return str(disc)
    return str(rom)


def launch_command(system, rom):
    settings = load_settings()
    # GameMode (installed with Steam on this page) for every game. For the
    # Flatpaks it registers the `flatpak run` process, which lives as long as
    # the game does.
    gamemode = ["gamemoderun"] if shutil.which("gamemoderun") else []
    fullscreen = game_fullscreen(rom, settings)
    if system["id"] == "ps2":
        return gamemode + ["flatpak", "run", *pcsx2_run_args(), system["flatpak"], "-batch",
                           "-fullscreen" if fullscreen else "-nofullscreen", "--", _ps2_disc(rom)]
    if system["id"] == "3ds":
        return gamemode + ["flatpak", "run", system["flatpak"], "-f" if fullscreen else "-w", rom]
    cmd = ["retroarch", f"--appendconfig={RETROARCH_REYOS_CFG}", "-L", str(core_path(system)), rom]
    shader = shader_for(system["id"], settings)
    if shader:
        # Only the command line loads a preset at start-up; a video_shader
        # line in the config is ignored.
        cmd.insert(1, f"--set-shader={shader}")
    # MangoHud performance overlay (also installed with Steam); Right
    # Shift+F12 hides it during a game. Compact, in PCSX2's corner, with the
    # hide key on screen (no emulator can toggle it from a controller;
    # custom_text only shows with legacy_layout=0). A
    # user's own MangoHud.conf wins: MANGOHUD_CONFIG would replace it.
    mangohud = ["mangohud"] if settings["overlay"] and shutil.which("mangohud") else []
    if mangohud and not MANGOHUD_USER_CFG.is_file():
        mangohud = ["env", f"MANGOHUD_CONFIG={MANGOHUD_COMPACT}"] + mangohud
    return gamemode + mangohud + cmd


def _launch_failure_reason():
    try:
        lines = [l.strip() for l in LAUNCH_LOG.read_text(errors="replace").splitlines() if l.strip()]
    except OSError:
        lines = []
    errors = [l for l in lines if "[ERROR]" in l or "Cannot" in l or "Failed" in l]
    reason = (errors or lines or ["it exited with an error."])[-1]
    return f"{reason} (full log: {LAUNCH_LOG})"


def running_game():
    """Title of the game an emulator has open right now ("" if none), so
    the Gaming page can say a changed setting needs a restart of it."""
    exts = {e for s in EMU_SYSTEMS for e in s["exts"]} | {".bin"}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        names = [os.path.basename(a.decode(errors="replace")) for a in args[:2]]
        if not any(n in ("retroarch", "pcsx2-qt", "azahar", "azahar-qt") for n in names):
            continue
        for arg in reversed(args):
            path = Path(arg.decode(errors="replace"))
            if path.suffix.lower() in exts:
                return game_title(path)
    return ""


def launch_game(system_id, path):
    """Starts a game detached from the caller. Returns (ok, message)."""
    system = next((s for s in EMU_SYSTEMS if s["id"] == system_id), None)
    if system is None or not Path(path).is_file():
        return False, "That game file couldn't be found."
    if not system_installed(system):
        return False, f"The {system['name']} emulator isn't installed yet -- set it up in Control Center > Gaming."
    if not RETROARCH_REYOS_CFG.is_file():
        prepare_folders()
    resolution = game_resolution(path) if system["id"] in THREE_D_SYSTEMS else None
    write_retroarch_cfg(system_id=system["id"], fullscreen=game_fullscreen(path), resolution=resolution)
    if "flatpak" in system:
        prepare_flatpak(system, resolution)
    LAUNCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LAUNCH_LOG.open("w") as log:
        proc = subprocess.Popen(launch_command(system, path), stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
    # Reap it when it exits so a finished game doesn't linger as a zombie.
    threading.Thread(target=proc.wait, daemon=True).start()
    # A launch that dies straight away (no usable video driver, missing core
    # file...) used to be invisible. Wait briefly and say why it failed.
    for _ in range(15):
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if proc.poll() not in (None, 0):
        return False, "The game couldn't start: " + _launch_failure_reason()
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


def _is_ps2_bios(data):
    # Every PS2 BIOS starts with a ROMDIR table whose first entry is "RESET";
    # PCSX2 looks for the same marker.
    return len(data) == BIOS_TABLE["ps2"]["size"] and b"RESET\0" in data[:0x10000]


def bios_import(paths):
    """Copy BIOS files the user picked into ~/Games/BIOS under the name and
    folder each emulator expects. Files are recognised by checksum (or, for
    the PS2, by size and ROMDIR marker); anything else is left alone.
    Returns (imported, messages)."""
    known = {md5: name for spec in BIOS_TABLE.values() for name, md5, _ in spec["files"] if md5}
    imported, messages = 0, []
    for raw in paths:
        src = Path(raw)
        label = src.name
        try:
            if not src.is_file() or src.stat().st_size > _BIOS_MAX_SIZE:
                messages.append(f"{label}: not a BIOS file.")
                continue
            data = src.read_bytes()
        except OSError as e:
            messages.append(f"{label}: couldn't read it ({e.strerror}).")
            continue
        md5 = hashlib.md5(data).hexdigest()
        if md5 in known:
            dst, kind = BIOS_DIR / known[md5], known[md5]
        elif _is_ps2_bios(data):
            dst, kind = BIOS_DIR / "ps2" / src.name, "PS2 BIOS"
        elif src.name == "firmware.bin":
            dst, kind = BIOS_DIR / "firmware.bin", "DS firmware"
        else:
            messages.append(f"{label}: not a BIOS ReyOS recognises.")
            continue
        try:
            if dst.is_file() and dst.read_bytes() == data:
                messages.append(f"{label}: already there.")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(dst)
        except OSError as e:
            messages.append(f"{label}: couldn't copy it ({e.strerror}).")
            continue
        imported += 1
        messages.append(f"{label}: imported as {kind}.")
    return imported, messages


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
        bus, vendor, product, version = struct.unpack("4H", _ioctl_bytes(fd, 0x02, 8))
        keys = _bits(_ioctl_bytes(fd, 0x20 + EV_KEY, (KEY_MAX + 1) // 8))
        axes = _bits(_ioctl_bytes(fd, 0x20 + EV_ABS, (ABS_MAX + 1) // 8))
    except OSError:
        os.close(fd)
        raise
    return fd, {"name": name, "vendor": vendor, "product": product, "bus": bus, "version": version,
                "keys": keys, "axes": axes}


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
                         "bus": info["bus"], "version": info["version"],
                         "brand": controller_brand(info["vendor"], info["name"]),
                         "detected": controller_brand(info["vendor"]),
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


PAD_TYPES = ("xbox", "playstation", "nintendo", "generic")


def controller_brand(vendor, name=None):
    """The controller's type (button names, picture): the one chosen for it
    on the Gaming page, else from its USB vendor id. 8BitDo pads, clones and
    many Bluetooth pads report other vendors, so they need the choice."""
    if name is not None:
        chosen = load_settings()["pad_types"].get(name)
        if chosen in PAD_TYPES:
            return chosen
    return PAD_BRANDS.get(vendor, "generic")


def set_pad_type(name, brand):
    """brand "" = back to the type detected from the vendor id."""
    types = dict(load_settings()["pad_types"])
    types.pop(name, None)
    if brand in PAD_TYPES:
        types[name] = brand
    save_settings({"pad_types": types})


def player1_pad(pads=None):
    """The connected controller chosen as player 1 (Gaming page), or None."""
    name = load_settings()["player1"]
    return next((p for p in (pads if pads is not None else list_controllers()) if p["name"] == name), None) if name else None


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
    "3ds": {"pad": "Nintendo 3DS", "map": [
        ("b", "B"), ("a", "A"), ("y", "Y"), ("x", "X"), ("dpad", "D-pad"), ("l", "L"), ("r", "R"),
        ("l2", "ZL"), ("r2", "ZR"), ("lstick", "Circle Pad"), ("rstick", "C-Stick"),
        ("select", "Select"), ("start", "Start")],
     "note": "Azahar (the 3DS emulator) gets these buttons from your controller setup when a game starts. Touch the bottom screen with the mouse."},
    "pc": {"pad": "Xbox controller (Windows games see every controller as one)", "map": [
        ("b", "A"), ("a", "B"), ("y", "X"), ("x", "Y"), ("dpad", "D-pad"),
        ("l", "LB"), ("r", "RB"), ("l2", "LT"), ("r2", "RT"), ("l3", "Left stick click"), ("r3", "Right stick click"),
        ("lstick", "Left stick"), ("rstick", "Right stick"), ("select", "View / Back"), ("start", "Menu / Start")],
     "note": "For every Windows game, from its next start. A changed layout makes Proton read the controller through SDL, as an Xbox controller: games with their own PlayStation support then show Xbox buttons."},
}
# Windows games in the button layouts (they aren't an EMU_SYSTEMS entry).
PC_SYSTEM = {"id": "pc", "name": "PC (Windows)"}

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
        text = cfg.read_text(errors="replace")
        m = re.search(r'^input_vendor_id = "(\d+)"', text, re.M)
        n = re.search(r'^input_device = "(.*)"', text, re.M)
        brand = controller_brand(int(m.group(1)), n.group(1) if n else None) if m else "generic"
        if brand != "generic":
            return brand
    return "generic"


# ---- Button layout per system (Gaming page / library right-click) --------
# A console button can be moved to another button of the player's pad; the
# choice is a swap within the buttons that system uses, so nothing is
# doubled. RetroArch systems get a per-core remap file (loaded by itself,
# auto_remaps_enable); PS2 gets PCSX2's Pad 1 bindings at launch.
REMAPPABLE = ("b", "a", "y", "x", "l", "r", "l2", "r2", "select", "start", "l3", "r3")
RETROPAD_ID = {"b": 0, "y": 1, "select": 2, "start": 3, "a": 8, "x": 9, "l": 10, "r": 11,
               "l2": 12, "r2": 13, "l3": 14, "r3": 15}
REMAP_DIR = Path.home() / ".config" / "retroarch" / "config" / "remaps"
CORE_INFO_DIR = Path("/usr/share/libretro/info")
_REMAP_MARK = "# Written by ReyOS Control Center > Gaming > Button layout"


def _remappable_keys(system_id):
    spec = SYSTEM_CONTROLS.get(system_id) or {"map": []}
    return [key for key, _label in spec["map"] if key in REMAPPABLE]


def button_map(system_id, settings=None):
    """{console button key: pad button key} for every button the system can
    move; unchanged ones map to themselves."""
    saved = (settings or load_settings())["button_maps"].get(system_id, {})
    keys = _remappable_keys(system_id)
    m = {k: k for k in keys}
    m.update({k: v for k, v in saved.items() if k in m and v in keys})
    return m if sorted(m.values()) == sorted(keys) else {k: k for k in keys}


def set_button(system_id, console_key, pad_key):
    """Moves a console button to another pad button, swapping with the one
    that had it."""
    m = button_map(system_id)
    if console_key not in m or pad_key not in m:
        return
    other = next(k for k, v in m.items() if v == pad_key)
    m[other], m[console_key] = m[console_key], pad_key
    _save_button_map(system_id, m)


def reset_buttons(system_id):
    _save_button_map(system_id, {})


def _save_button_map(system_id, m):
    maps = dict(load_settings()["button_maps"])
    changed = {k: v for k, v in m.items() if k != v}
    if changed:
        maps[system_id] = changed
    else:
        maps.pop(system_id, None)
    save_settings({"button_maps": maps})
    _write_remap(system_id)


def _core_name(system):
    try:
        text = (CORE_INFO_DIR / f"{system['core']}_libretro.info").read_text(errors="replace")
    except (OSError, KeyError):
        return None
    m = re.search(r'^corename\s*=\s*"(.*)"', text, re.M)
    return m.group(1) if m else None


def _write_remap(system_id):
    """The per-core remap RetroArch loads for this system's emulator; ours
    is removed again when the layout is back to default. A remap file made
    in RetroArch's own menu is left alone."""
    system = next((s for s in EMU_SYSTEMS if s["id"] == system_id), None)
    if system is None or "core" not in system:
        return
    name = _core_name(system)
    if not name:
        return
    path = REMAP_DIR / name / f"{name}.rmp"
    ours = not path.exists() or _REMAP_MARK in path.read_text(errors="replace")
    if not ours:
        return
    m = button_map(system_id)
    if all(k == v for k, v in m.items()):
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_REMAP_MARK] + [f'input_player1_btn_{pad} = "{RETROPAD_ID[console]}"' for console, pad in m.items()]
    path.write_text("\n".join(lines) + "\n")


def system_controls(brand):
    """Per-system button layout for the Gaming page: which button on the
    player's pad does what on each console, and what it can be moved to."""
    names = {**_COMMON_NAMES, **PAD_BUTTON_NAMES.get(brand, PAD_BUTTON_NAMES["generic"])}
    settings = load_settings()
    out = []
    for system in EMU_SYSTEMS + [PC_SYSTEM]:
        spec = SYSTEM_CONTROLS.get(system["id"])
        if not spec:
            continue
        m = button_map(system["id"], settings)
        rows = [{"key": key, "console": label, "yours": names[m.get(key, key)],
                 "pad": m.get(key, key), "movable": key in m and ("core" in system or system["id"] in ("ps2", "3ds", "pc"))}
                for key, label in spec["map"]]
        out.append({"id": system["id"], "name": system["name"], "pad": spec["pad"],
                    "note": spec.get("note", ""), "rows": rows,
                    "choices": [{"key": k, "label": names[k]} for k in m],
                    "custom": any(k != v for k, v in m.items()),
                    # Where each console button now sits on the pad picture.
                    "labels": {m.get(key, key): label for key, label in spec["map"]}})
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
    """Each game once: a link in ~/Games/ROMs and the file it points to in
    the games folder are the same game. Hidden folders (.adding, a half
    done "Add games") are skipped."""
    seen = set()
    for folder in library_dirs(system):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if any(part.startswith(".") for part in path.relative_to(folder).parts):
                continue
            if path.is_file() and path.suffix.lower() in system["exts"]:
                real = os.path.realpath(path)
                if real in seen:
                    continue
                seen.add(real)
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
    tmp = cache.with_suffix(".part")
    tmp.write_text("\n".join(names))
    tmp.replace(cache)
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


_MISSING_COVER_TTL = 30 * 86400


def cover_cached(system, rom):
    """Box art is cached, or was looked up within the last 30 days and not
    found (an empty file); after that the lookup runs again, in case the
    libretro-thumbnails project has added it since."""
    try:
        st = (BOXART_CACHE / system["id"] / (Path(rom).stem + ".png")).stat()
    except OSError:
        return False
    return st.st_size > 0 or time.time() - st.st_mtime < _MISSING_COVER_TTL


def fetch_cover(system, rom):
    """Download box art for one game into the cache. Returns the cover path,
    or "" when none was found (remembered with an empty file, so a game
    with no box art isn't looked up again on every visit)."""
    rom = Path(rom)
    target = BOXART_CACHE / system["id"] / (rom.stem + ".png")
    if cover_cached(system, rom):
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
