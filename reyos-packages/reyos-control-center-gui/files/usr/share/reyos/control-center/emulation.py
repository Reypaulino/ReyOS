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
import struct
from pathlib import Path

EMU_SYSTEMS = [
    {"id": "nes", "name": "NES / Famicom", "core": "nestopia", "exts": [".nes", ".unf", ".fds"]},
    {"id": "snes", "name": "Super Nintendo", "core": "snes9x", "exts": [".sfc", ".smc"]},
    {"id": "gb", "name": "Game Boy / Color", "core": "gambatte", "exts": [".gb", ".gbc"]},
    {"id": "gba", "name": "Game Boy Advance", "core": "mgba", "exts": [".gba"]},
    {"id": "genesis", "name": "Genesis / Master System / Game Gear", "core": "genesis_plus_gx", "exts": [".md", ".gen", ".smd", ".sms", ".gg"]},
    {"id": "n64", "name": "Nintendo 64", "core": "mupen64plus_next", "exts": [".n64", ".z64", ".v64"]},
    {"id": "psx", "name": "PlayStation", "core": "mednafen_psx", "exts": [".cue", ".chd", ".pbp", ".m3u"]},
    {"id": "psp", "name": "PSP", "core": "ppsspp", "exts": [".iso", ".cso", ".pbp", ".chd"]},
    {"id": "nds", "name": "Nintendo DS", "core": "melonds", "exts": [".nds"]},
    {"id": "gamecube", "name": "GameCube / Wii (needs a fast PC)", "core": "dolphin", "exts": [".iso", ".gcm", ".rvz", ".wbfs", ".ciso", ".gcz"]},
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


def core_path(system):
    return LIBRETRO_DIR / f"{system['core']}_libretro.so"


def system_installed(system):
    # GameCube also needs dolphin-emu's data files (see link_system_files);
    # installs from before that was added show as not installed so the
    # user can tick it again to get them.
    if system["id"] == "gamecube" and not DOLPHIN_SYS.is_dir():
        return False
    return core_path(system).is_file()


# ---- Display settings -----------------------------------------------------
DEFAULT_SETTINGS = {"fullscreen": True, "picture": "fill", "resolution": 1}

# 3D internal resolution per core, keyed by ReyOS's 1x / 2x / 4x choice.
# Option names and values checked against the cores Arch ships.
RESOLUTION_OPTIONS = {
    1: {"mupen64plus-EnableNativeResFactor": "1", "beetle_psx_internal_resolution": "1x(native)",
        "ppsspp_internal_resolution": "480x272", "melonds_opengl_renderer": "disabled",
        "melonds_opengl_resolution": "1x native (256x192)", "dolphin_efb_scale": "1"},
    2: {"mupen64plus-EnableNativeResFactor": "2", "beetle_psx_internal_resolution": "2x",
        "ppsspp_internal_resolution": "960x544", "melonds_opengl_renderer": "enabled",
        "melonds_opengl_resolution": "2x native (512x384)", "dolphin_efb_scale": "2"},
    4: {"mupen64plus-EnableNativeResFactor": "4", "beetle_psx_internal_resolution": "4x",
        "ppsspp_internal_resolution": "1920x1088", "melonds_opengl_renderer": "enabled",
        "melonds_opengl_resolution": "4x native (1024x768)", "dolphin_efb_scale": "4"},
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
        (GAMES_DIR / "ROMs" / system["id"]).mkdir(parents=True, exist_ok=True)
    for sub in ("BIOS", "Saves", "Saves/states"):
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
            "BIOS files go in BIOS/. PlayStation needs one (scph5501.bin for US\n"
            "games); Control Center > Gaming > Check BIOS files shows what's there.\n")
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
    ("up", "Press D-pad up", ""),
    ("down", "Press D-pad down", ""),
    ("left", "Press D-pad left", ""),
    ("right", "Press D-pad right", ""),
    ("l", "Press the left shoulder button", "LB / L1 / L"),
    ("r", "Press the right shoulder button", "RB / R1 / R"),
    ("l2", "Pull the left trigger", "LT / L2 / ZL"),
    ("r2", "Pull the right trigger", "RT / R2 / ZR"),
    ("select", "Press Select", "View / Back on Xbox, Share / Create on PlayStation, − on Nintendo"),
    ("start", "Press Start", "Menu on Xbox, Options on PlayStation, + on Nintendo"),
    ("l3", "Click the left stick in", ""),
    ("r3", "Click the right stick in", ""),
    ("l_x", "Push the left stick all the way right", ""),
    ("l_y", "Push the left stick all the way down", ""),
    ("r_x", "Push the right stick all the way right", ""),
    ("r_y", "Push the right stick all the way down", ""),
    ("menu_toggle", "Press the Home button", "Xbox / PS / Home button -- opens the emulator menu in a game"),
]


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
