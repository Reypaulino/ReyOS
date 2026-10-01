#!/usr/bin/env python3
"""Look / Light-Dark helpers shared by Control Center (main.py imports these)
and the login-time Look reapply. Deliberately imports no Qt: run directly
with --reapply-look by /etc/xdg/plasma-workspace/env/reyos-reapply-look.sh at
every login, where going through main.py cost ~0.6 s just loading PySide6
(measured on the Dev VM and ReyOS-Test) before doing any real work."""
import colorsys
import configparser
import re
import shutil
import subprocess
import sys
from pathlib import Path

LOOKS_DIR = Path("/usr/share/reyos/looks")

# Light/Dark (the Appearance page's "Look and feel") and the Look (accent +
# wallpaper) are two independent choices. They used to each apply one fixed
# color scheme, so each silently undid the other: switching to Light reset
# the accent to copper, and applying any Look (every Look ships a dark
# scheme only) put the dark palette back. Both now resolve the one scheme
# that matches BOTH choices via _scheme_for(), and remember their own half
# in kdeglobals' [ReyOS] group so the other side can read it back.
LIGHT_LOOKANDFEEL = "org.reyos.light.desktop"
_COPPER_RGB = "201,121,50"
_LIGHT_BASE_SCHEME = Path("/usr/share/color-schemes/ReyOSLight.colors")
_PANEL_THEME_SRC = Path("/usr/share/plasma/desktoptheme/ReyOS")
_PANEL_FILL_DARK = "#14100d"
_PANEL_FILL_LIGHT = "#eff0f1"
PANEL_OPACITY_DEFAULT = 82
_PANEL_SEE_THROUGH = 0.6


def _kread(file, group, key, default=""):
    try:
        value = subprocess.check_output(
            ["kreadconfig6", "--file", file, "--group", group, "--key", key],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return value or default
    except (OSError, subprocess.CalledProcessError):
        return default


def _kwrite(file, group, key, value):
    subprocess.run(["kwriteconfig6", "--file", file, "--group", group, "--key", key, str(value)])


def _look_parser(look_id):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read(LOOKS_DIR / look_id / "colors.colors")
    return parser


def _is_light_mode():
    return _kread("kdeglobals", "KDE", "LookAndFeelPackage") == LIGHT_LOOKANDFEEL


def _current_look_id():
    look_id = _kread("kdeglobals", "ReyOS", "Look")
    if look_id and (LOOKS_DIR / look_id / "colors.colors").is_file():
        return look_id
    # Systems that picked a Look before [ReyOS] Look existed: recover it
    # from the active scheme name (dark ids come straight from each Look's
    # colors.colors; light ones are ReyOS<Look>Light, see _scheme_for()).
    current = _kread("kdeglobals", "General", "ColorScheme")
    if LOOKS_DIR.is_dir():
        for look_dir in LOOKS_DIR.iterdir():
            if not (look_dir / "colors.colors").is_file():
                continue
            if current in (_look_parser(look_dir.name).get("General", "ColorScheme", fallback=""),
                           f"ReyOS{look_dir.name.capitalize()}Light"):
                return look_dir.name
    return "copper"


def _look_accent_rgb(look_id):
    return _look_parser(look_id).get("Colors:Button", "DecorationFocus", fallback=_COPPER_RGB).strip()


def _scheme_for(look_id, light):
    """Return the registered color-scheme name for this Look in this mode,
    generating the light variant on demand (ReyOSLight's palette with every
    copper accent swapped for the Look's own) under the user's own
    ~/.local/share/color-schemes, where plasma-apply-colorscheme resolves
    it by name just like a system-installed one."""
    if not light:
        return _look_parser(look_id).get("General", "ColorScheme", fallback="ReyOS")
    accent = _look_accent_rgb(look_id)
    if look_id == "copper" or accent == _COPPER_RGB or not _LIGHT_BASE_SCHEME.is_file():
        return "ReyOSLight"
    scheme_id = f"ReyOS{look_id.capitalize()}Light"
    text = _LIGHT_BASE_SCHEME.read_text().replace(_COPPER_RGB, accent)
    text = re.sub(r"(?m)^ColorScheme=.*$", f"ColorScheme={scheme_id}", text)
    text = re.sub(r"(?m)^Name=.*$", f"Name=ReyOS {look_id.capitalize()} Light", text)
    out = Path.home() / ".local" / "share" / "color-schemes" / f"{scheme_id}.colors"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return scheme_id


def _panel_opacity():
    try:
        return max(10, min(100, int(_kread("kdeglobals", "ReyOS", "PanelOpacity", PANEL_OPACITY_DEFAULT))))
    except ValueError:
        return PANEL_OPACITY_DEFAULT


def _write_panel_theme():
    """reyos-themes' panel-background.svg hardcodes a dark fill, a copper rim
    and 0.82 opacity, so the panels stayed dark under Light and copper under
    every Look. Write a per-user copy of the ReyOS Plasma theme instead
    (~/.local/share wins over /usr/share per file, and it's user-owned, so no
    sudo helper needed) with the fill matching the mode, the rim matching the
    Look, and the translucent variant's opacity from the Appearance slider.
    Callers restart plasmashell afterwards; the caches cleared here are what
    would otherwise keep serving the previously rendered panel."""
    if not (_PANEL_THEME_SRC / "metadata.json").is_file():
        return
    light = _is_light_mode()
    opacity = _panel_opacity() / 100
    # A see-through bar shows the (dark) wallpaper, so a light Look's dark text
    # vanished on it (real report, slider at 15%). Below this opacity the bar
    # is tinted dark and the Plasma shell gets the Look's dark palette (the
    # theme's colors file below), so bar text is white.
    dark_bar = not light or opacity < _PANEL_SEE_THROUGH
    fill = _PANEL_FILL_DARK if dark_bar else _PANEL_FILL_LIGHT
    look_id = _current_look_id()
    rim = "#" + "".join(f"{int(c):02x}" for c in _look_accent_rgb(look_id).split(","))
    dest = Path.home() / ".local" / "share" / "plasma" / "desktoptheme" / "ReyOS"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_PANEL_THEME_SRC / "metadata.json", dest / "metadata.json")
    for rel, fill_opacity in (("widgets/panel-background.svg", opacity), ("solid/widgets/panel-background.svg", 1)):
        src = _PANEL_THEME_SRC / rel
        if not src.is_file():
            continue
        text = src.read_text()
        text = re.sub(r"\.reyos-panel-fill \{[^}]*\}",
                      f".reyos-panel-fill {{ fill:{fill}; fill-opacity:{fill_opacity:g}; }}", text)
        text = re.sub(r"(?<=\.reyos-panel-rim \{ fill:none; stroke:)#[0-9A-Fa-f]{6}", rim, text)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    colors = dest / "colors"
    dark_scheme = Path("/usr/share/color-schemes") / f"{_scheme_for(look_id, False)}.colors"
    if light and dark_bar and dark_scheme.is_file():
        shutil.copy2(dark_scheme, colors)
    else:
        colors.unlink(missing_ok=True)
    # The ReyOS Plasma theme only arrived with reyos-themes 1.0.0-55-ish
    # (2026-09-28), and reyos-apply-branding.sh selects it only once, at
    # first login -- so any install from an older ISO still runs stock
    # Breeze and ignores everything written above (confirmed live on
    # ReyOS-Test: slider at 90%, panels fully opaque). Select it here too.
    _kwrite("kdeglobals", "Theme", "name", "ReyOS")
    _kwrite("plasmarc", "Theme", "name", "ReyOS")
    cache = Path.home() / ".cache"
    for pattern in ("plasma_theme_*.kcache", "plasma-svgelements*", "ksvg-elements*"):
        for p in cache.glob(pattern):
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)


def _recolor_look_assets(look_id):
    """Recolor every file that bakes the accent in as a literal -- ReyOS
    icons, the app/launcher icons, the Aurorae window border, reyos-browser,
    Konsole and fastfetch -- to this Look's accent. Split out of applyLook()
    because those root-owned files are reset to copper by every package
    update that ships them (reported live: after an update the Control
    Center icon and the window border went back to copper), and Light/Dark
    never re-ran it. Now also called by applyLookAndFeel() and at login
    (--reapply-look, see main()) so the active Look always wins."""
    parser = _look_parser(look_id)
    # reyos-icons' own branded overrides -- the gear used for every
    # "preferences-*"-style sidebar icon, and the folder-shaped
    # Dolphin app icon -- bake their accent in as a literal
    # fill="#RRGGBB" -- a plain color-scheme switch never touches
    # these files, so they stayed copper under every Look until
    # this rewrites them to match. Each is anchored on its own
    # mask id (unique to the branded rect) so the mask definition's
    # own white/black fills are never touched.
    accent_hex = parser.get("Colors:Button", "DecorationFocus", fallback=None)
    if accent_hex:
        accent_hex = "#" + "".join(f"{int(c):02x}" for c in accent_hex.split(","))
        # Parsed once here so every patch below (gear/launcher icons,
        # Konsole, fastfetch) can use plain r/g/b ints without each
        # re-deriving them from accent_hex.
        accent_r = int(accent_hex[1:3], 16)
        accent_g = int(accent_hex[3:5], 16)
        accent_b = int(accent_hex[5:7], 16)
        # /usr/share/icons (and /usr/share/reyos/browser below) are
        # root-owned -- writing there directly (this process runs
        # unprivileged) fails with EACCES. Every patch in this
        # section only stages its recolored file under /tmp; a
        # single sudo call to the fixed reyos-apply-look-icons.sh
        # helper (below, after all staging is done) moves everything
        # into place in one privileged step. A raw "sudo cp"/"sudo
        # bash -c <built string>" was tried first and silently did
        # nothing when triggered from a real GUI click -- no NOPASSWD
        # rule covers arbitrary cp/bash -c (deliberately, per
        # shellprocess_sudoers_reyos_menu.conf's own comments on why
        # a wildcard cp/chown is never granted), and sudo has no
        # controlling terminal to prompt for a password from a GUI
        # subprocess, so it just failed with no visible error. The
        # fixed-path helper script can get an exact-match NOPASSWD
        # rule instead, same precedent as enable-multilib.sh.
        any_staged = False
        masked_icons = [
            ("gear-mask", "/usr/share/icons/ReyOS/apps/16/preferences-system.svg", "gear-16"),
            ("gear-mask", "/usr/share/icons/ReyOS/apps/32/preferences-system.svg", "gear-32"),
            ("gear-mask", "/usr/share/icons/ReyOS/apps/48/preferences-system.svg", "gear-48"),
            ("folder-mask", "/usr/share/icons/ReyOS/apps/48/org.kde.dolphin.svg", "dolphin-48"),
        ]
        for mask_id, svg_path, tmp_stem in masked_icons:
            svg_file = Path(svg_path)
            if not svg_file.is_file():
                continue
            pattern = re.compile(rf'(fill="#[0-9A-Fa-f]{{6}}"(?=[^>]*mask="url\(#{mask_id}\)"))')
            text = svg_file.read_text()
            new_text = pattern.sub(f'fill="{accent_hex}"', text)
            if new_text == text:
                continue
            Path(f"/tmp/reyos-look-{tmp_stem}.svg").write_text(new_text)
            any_staged = True

        # reyos-themes' Aurorae window decoration (usr/share/aurorae/
        # themes/ReyOS/decoration.svg) centralizes its one accent spot
        # in a named CSS class (.reyos-deco-rim) rather than a bare
        # fill/stroke attribute -- same anchor-on-stable-structure
        # reasoning as the masked_icons loop above (match by what the
        # element IS, not by diffing against whatever hex the last
        # Look happened to leave behind).
        deco_svg = Path("/usr/share/aurorae/themes/ReyOS/decoration.svg")
        if deco_svg.is_file():
            text = deco_svg.read_text()
            new_text = re.sub(
                r'(?<=\.reyos-deco-rim \{ fill:none; stroke:)#[0-9A-Fa-f]{6}',
                accent_hex, text,
            )
            # Straight edges draw the rim as a filled rect (see decoration.svg)
            new_text = re.sub(
                r'(?<=\.reyos-deco-rim-edge \{ stroke:none; fill:)#[0-9A-Fa-f]{6}',
                accent_hex, new_text,
            )
            if new_text != text:
                Path("/tmp/reyos-look-decoration.svg").write_text(new_text)
                any_staged = True

        # The Kickoff/taskbar app-launcher badge and every branded
        # app icon (Control Center, Browser, Reader, Distrobox GUI)
        # share the exact same two-stop-gradient badge template
        # (only the inner glyph and, for the launcher/browser, the
        # gradient's own <id> differ -- irrelevant here since the
        # regex below matches the <stop> elements directly, not the
        # id). All bake copper in as literal hex. Light stop uses
        # the same +39/+59/+56 lightening already applied to
        # reyos-system-menu.sh's YLW and reyos-terminal's Konsole
        # Color3Intense, so this stays visually consistent with the
        # rest of the accent family.
        light_hex = "#" + "".join(
            f"{min(255, c + d):02x}" for c, d in zip((accent_r, accent_g, accent_b), (39, 59, 56))
        )
        # (svg_path, tmp_stem, also_render_png) -- only reyos-launcher
        # also ships a competing fixed-size 256x256 PNG under the same
        # icon name (confirmed live 2026-09-25: KDE's icon-theme
        # resolution can prefer that PNG over this same-named
        # scalable SVG for panel/taskbar contexts, so the SVG alone
        # updating on disk didn't change the visible taskbar icon
        # until a matching PNG was regenerated too). The other four
        # ship SVG-only, so there's no competing raster to keep in
        # sync -- rendering one for them would just add a fallback
        # that never existed before, so they stay SVG-only.
        app_icons = [
            ("/usr/share/icons/hicolor/scalable/apps/reyos-launcher.svg", "launcher", True),
            ("/usr/share/icons/hicolor/scalable/apps/reyos-control-center.svg", "control-center", False),
            ("/usr/share/icons/hicolor/scalable/apps/reyos-browser.svg", "browser", False),
            ("/usr/share/icons/hicolor/scalable/apps/reyos-reader.svg", "reader", False),
            ("/usr/share/icons/hicolor/scalable/apps/reyos-distrobox-gui.svg", "distrobox-gui", False),
        ]
        for svg_path, tmp_stem, also_render_png in app_icons:
            svg_file = Path(svg_path)
            if not svg_file.is_file():
                continue
            text = svg_file.read_text()
            new_text = re.sub(
                r'(?<=<stop stop-color=")#[0-9A-Fa-f]{6}(?=")', light_hex, text, count=1,
            )
            new_text = re.sub(
                r'(?<=<stop offset="1" stop-color=")#[0-9A-Fa-f]{6}(?=")', accent_hex, new_text, count=1,
            )
            if new_text == text:
                continue
            svg_tmp = Path(f"/tmp/reyos-look-{tmp_stem}.svg")
            svg_tmp.write_text(new_text)
            any_staged = True
            if also_render_png:
                # rsvg-convert needs no root, so it runs here rather
                # than in the sudo helper script.
                subprocess.run(
                    ["rsvg-convert", "-w", "256", "-h", "256",
                     "-o", f"/tmp/reyos-look-{tmp_stem}.png", str(svg_tmp)],
                    capture_output=True,
                )

        # reyos-browser's accent palette used to be scattered as
        # literal hex through ~180 places across two files, patched
        # by scanning for whatever the *previous* accent's shades
        # looked like and string-replacing them. That approach
        # needed four separate bug fixes in one session (wrong
        # derivation source once the literals drifted out of sync
        # with each other; hue collapsing toward blue for any accent
        # whose dominant channel wasn't red like Copper's, since a
        # flat per-channel RGB offset doesn't preserve hue; an
        # over-broad match corrupting an unrelated field; and
        # floating-point rounding silently breaking the string match
        # entirely for some roles). Main.qml now centralizes its 9
        # accent-derived colors into named `readonly property color`
        # declarations at the top of the file (accentColor,
        # accentBorder, accentSurfaceHover, etc.) that every other
        # place in the file references by name -- QML's own binding
        # system propagates a change to every usage, so this only
        # ever has to patch those 9 declarations directly, by name,
        # never scan the file for scattered literals again.
        # home.html can't do the same (it's plain HTML/CSS loaded by
        # URL, not QML), so its few accent-derived spots stay
        # anchored on their own unique surrounding CSS instead --
        # still no value-diffing, just a direct overwrite of
        # whatever's at that anchor, which is what proved reliable
        # for the button/input/form spots below already.
        def _hsl_shade(rgb, s_pct, l_pct):
            r, g, b = (c / 255 for c in rgb)
            h, _l, _s = colorsys.rgb_to_hls(r, g, b)
            nr, ng, nb = colorsys.hls_to_rgb(h, l_pct / 100, s_pct / 100)
            return "#" + "".join(f"{round(c * 255):02X}" for c in (nr, ng, nb))

        accent_rgb = (accent_r, accent_g, accent_b)
        # (S%, L%) targets measured from Copper's own hand-tuned hex
        # values (e.g. border's #8E5A2E is H≈28° S≈51% L≈37%, versus
        # the Copper accent's own H≈28° S≈60% L≈49%) -- feeding
        # Copper's own accent through _hsl_shade with these targets
        # reproduces the original palette almost exactly, confirming
        # this is what the hand-picked palette was actually doing.
        ROLE_HSL = {
            "border": (51.1, 36.9),
            "surfaceHover": (35.6, 17.1),
            "surfaceRaised": (35.2, 13.9),
            "surfaceBase": (32.0, 9.8),
            "surfaceToolbar": (30.9, 10.8),
            "surfaceWindow": (20.0, 6.9),
            "hoverStrong": (39.6, 20.8),
            "glow": (81.7, 67.8),
        }
        shade = {name: _hsl_shade(accent_rgb, s, l) for name, (s, l) in ROLE_HSL.items()}

        main_qml = Path("/usr/share/reyos/browser/qml/Main.qml")
        if main_qml.is_file():
            text = main_qml.read_text()
            new_text = text
            for prop, value in (
                ("accentColor", accent_hex),
                ("accentBorder", shade["border"]),
                ("accentSurfaceHover", shade["surfaceHover"]),
                ("accentSurfaceRaised", shade["surfaceRaised"]),
                ("accentSurfaceBase", shade["surfaceBase"]),
                ("accentSurfaceToolbar", shade["surfaceToolbar"]),
                ("accentSurfaceWindow", shade["surfaceWindow"]),
                ("accentHoverStrong", shade["hoverStrong"]),
                ("accentGlow", shade["glow"]),
            ):
                new_text = re.sub(
                    rf'(?<=readonly property color {prop}: ")#[0-9A-Fa-f]{{6}}(?=")',
                    value, new_text,
                )
            # The reader-mode view's own HTML/CSS is built as a plain
            # JS string inside this file (readerHtml()-style
            # function), not a QML binding, so it can't reference the
            # properties above -- same small set of colors, patched
            # by anchoring on their own unique surrounding CSS.
            new_text = re.sub(
                r'linear-gradient\(145deg,#[0-9A-Fa-f]{6},#[0-9A-Fa-f]{6}\)',
                f'linear-gradient(145deg,{shade["surfaceWindow"]},{shade["surfaceToolbar"]})',
                new_text,
            )
            new_text = re.sub(
                r'(?<=border:1px solid )#[0-9A-Fa-f]{6}', shade["border"], new_text,
            )
            new_text = re.sub(
                r'background:linear-gradient\(135deg,#[0-9A-Fa-f]{6},#[0-9A-Fa-f]{6}\)',
                f'background:linear-gradient(135deg,{shade["surfaceHover"]},{shade["surfaceRaised"]})',
                new_text,
            )
            new_text = re.sub(
                r'(?<=letter-spacing:1\.2px;color:)#[0-9A-Fa-f]{6}', shade["glow"], new_text,
            )
            new_text = re.sub(
                r'(?<=article\{background:)#[0-9A-Fa-f]{6}', shade["surfaceBase"], new_text,
            )
            if new_text != text:
                Path("/tmp/reyos-look-browser-Main.qml").write_text(new_text)
                any_staged = True

        home_html = Path("/usr/share/reyos/browser/home.html")
        if home_html.is_file():
            text = home_html.read_text()
            # Anchored on ";color:white" (only the search button's
            # CSS rule uses that literal keyword -- everything else
            # in this file, including the form field right next to
            # it, uses a hex color) rather than a "background:#hex"
            # lookbehind, which also matched the form field's own
            # background:#211711E8 -- caught live-testing on the Dev
            # VM: an earlier Violet switch had turned the button,
            # the form container, AND the input field all solid
            # violet from exactly that over-broad match.
            new_text = re.sub(r'#[0-9A-Fa-f]{6}(?=;color:white)', accent_hex, text)
            new_text = re.sub(
                r'#[0-9A-Fa-f]{6}(?=;color:#FFF3E6;font:inherit)', shade["surfaceRaised"], new_text,
            )
            new_text = re.sub(
                r'#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?(?=;border:1px solid)',
                lambda m: shade["surfaceBase"] + (m.group(1) or ""),
                new_text,
            )
            bg_base = _hsl_shade(accent_rgb, 22.2, 3.5)
            bg_mid = _hsl_shade(accent_rgb, 31.4, 6.9)
            new_text = re.sub(
                r'linear-gradient\(145deg,#[0-9A-Fa-f]{6} 0%,#[0-9A-Fa-f]{6} 48%,#[0-9A-Fa-f]{6} 100%\)',
                f'linear-gradient(145deg,{bg_base} 0%,{bg_mid} 48%,{bg_base} 100%)',
                new_text,
            )
            new_text = re.sub(
                r'(?<=border:1px solid )#[0-9A-Fa-f]{6}', _hsl_shade(accent_rgb, 52.3, 43.5), new_text,
            )
            if new_text != text:
                Path("/tmp/reyos-look-browser-home.html").write_text(new_text)
                any_staged = True

        if any_staged:
            subprocess.run(["sudo", "/usr/share/reyos/bin/reyos-apply-look-icons.sh"])
            # Only when something changed -- this also runs at every login
            # (--reapply-look), where a full rebuild each time would just
            # slow the session start down for nothing.
            subprocess.run(["kbuildsycoca6", "--noincremental"], capture_output=True)

        # reyos-terminal's Konsole profile bakes its accent in as a
        # static [Color3]/[Color3Faint]/[Color3Intense] triple too
        # (the yellow/prompt slot -- same slot reyos-system-menu.sh's
        # own YLW derives from at launch). Unlike the browser/icon
        # patches above, this file lives under the user's own home
        # (~/.local/share/konsole), not a root-owned system path, so
        # no sudo/tmp-stage dance is needed -- write it directly.
        konsole_scheme = Path.home() / ".local" / "share" / "konsole" / "ReyOS.colorscheme"
        if konsole_scheme.is_file():
            def _shade(r, g, b, delta):
                return ",".join(str(max(0, min(255, c + delta))) for c in (r, g, b))
            text = konsole_scheme.read_text()
            text = re.sub(
                r"(?<=\[Color3\]\nColor=)[0-9]+,[0-9]+,[0-9]+",
                f"{accent_r},{accent_g},{accent_b}", text,
            )
            text = re.sub(
                r"(?<=\[Color3Faint\]\nColor=)[0-9]+,[0-9]+,[0-9]+",
                _shade(accent_r, accent_g, accent_b, -80), text,
            )
            text = re.sub(
                r"(?<=\[Color3Intense\]\nColor=)[0-9]+,[0-9]+,[0-9]+",
                _shade(accent_r, accent_g, accent_b, 25), text,
            )
            konsole_scheme.write_text(text)

        # fastfetch's ReyOS ASCII logo (shown on every new shell)
        # bakes the same copper RGB into its raw true-color escape
        # codes -- the tagline box itself is ivory (theme-invariant,
        # matches WHT in reyos-system-menu.sh) and must be left
        # alone. Matching on the specific copper value (like the
        # Konsole patch's section-anchored regex) would only work
        # once -- after the first Look switch the file no longer
        # contains "201;121;50" at all, so this instead matches
        # *any* "38;2;R;G;Bm" escape and skips whichever one is the
        # ivory tagline color, so repeated switches keep working.
        fastfetch_ascii = Path.home() / ".config" / "fastfetch" / "reyos-ascii.txt"
        if fastfetch_ascii.is_file():
            ivory = (255, 243, 230)
            def _retarget_logo_color(m):
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if (r, g, b) == ivory:
                    return m.group(0)
                return f"38;2;{accent_r};{accent_g};{accent_b}m"
            text = fastfetch_ascii.read_text()
            new_text = re.sub(
                r"38;2;([0-9]+);([0-9]+);([0-9]+)m", _retarget_logo_color, text,
            )
            if new_text != text:
                fastfetch_ascii.write_text(new_text)

        # fastfetch's own info panel (the "user@host" title line and
        # every "OS"/"Kernel"/"Uptime"/etc. label) is colored via
        # config.jsonc's display.color.keys/title -- a bare
        # "R;G;B"-style code, not a full escape sequence, and also
        # hardcoded copper. Same file, no sudo needed.
        fastfetch_config = Path.home() / ".config" / "fastfetch" / "config.jsonc"
        if fastfetch_config.is_file():
            accent_code = f"38;2;{accent_r};{accent_g};{accent_b}"
            text = fastfetch_config.read_text()
            new_text = re.sub(
                r'("(?:keys|title)"\s*:\s*")38;2;[0-9]+;[0-9]+;[0-9]+(")',
                rf"\g<1>{accent_code}\g<2>", text,
            )
            if new_text != text:
                fastfetch_config.write_text(new_text)

    # Unconditional: KWin
    # caches the parsed Aurorae decoration.svg in its own process,
    # separate from plasmashell -- this is what actually picks up
    # decoration.svg's freshly-repainted .reyos-deco-rim stroke
    # after the sudo helper above moves it into place. Safe to call
    # even when nothing decoration-related changed this time.
    #
    # Confirmed live (2026-09-28): reconfigure alone is NOT enough --
    # KSvg (the library backing Aurorae's FrameSvg rendering) keeps
    # its own on-disk element-geometry cache at ~/.cache/ksvg-elements
    # that does not invalidate just because decoration.svg's content
    # changed on disk. Without clearing it first, an existing window
    # kept showing the PREVIOUS Look's rim color indefinitely, even
    # across repeated reconfigure calls and even for freshly-opened
    # windows -- only removing this cache made KWin actually
    # re-parse the file. This is a per-user cache (not root-owned),
    # safe to remove outright; KSvg regenerates it. It's a plain
    # FILE, not a directory (confirmed live) -- shutil.rmtree()
    # silently no-ops on it via NotADirectoryError swallowed by
    # ignore_errors=True, which is exactly how this was missed the
    # first time: no exception, no error, just a cache that quietly
    # never cleared. Path.unlink() is the correct call here.
    ksvg_cache = Path.home() / ".cache" / "ksvg-elements"
    ksvg_cache.is_dir() and shutil.rmtree(ksvg_cache, ignore_errors=True)
    ksvg_cache.unlink(missing_ok=True)
    subprocess.run(["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"], capture_output=True)


def main():
    # Package updates reinstall the copper originals of the files
    # _recolor_look_assets() patches, so put the active Look's accent back
    # before KWin/plasmashell draw them. A no-op (no sudo, no writes) when
    # every file already matches.
    if "--reapply-look" in sys.argv:
        try:
            _recolor_look_assets(_current_look_id())
        except Exception as exc:
            print(f"reyos: could not reapply Look colors: {exc}", file=sys.stderr)
        # Refresh the per-user bar theme (if Control Center made one) so an
        # update to its rules reaches existing accounts; runs before plasmashell.
        if (Path.home() / ".local/share/plasma/desktoptheme/ReyOS/metadata.json").is_file():
            try:
                _write_panel_theme()
            except Exception as exc:
                print(f"reyos: could not refresh the bar theme: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
