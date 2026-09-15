#!/usr/bin/env python3
"""ReyOS Shortcuts Cheatsheet -- a global-hotkey popup listing every
keybinding actually active on the system right now: KWin/kglobalaccel
bindings from kglobalshortcutsrc, plus the user's own xbindkeys-based
custom shortcuts from Control Center's Keyboard page. Read-only -- this
never writes either file, it only reflects what's already bound.
"""
import configparser
import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

APP_DIR = Path(__file__).resolve().parent
KGLOBALSHORTCUTS = Path.home() / ".config" / "kglobalshortcutsrc"
CUSTOM_SHORTCUTS = Path.home() / ".config" / "reyos" / "custom-shortcuts.json"


def _reyos_accent_color():
    # Same fallback pattern used by the other branded ReyOS apps -- see
    # reyos-control-center-gui's main.py for why this exists.
    try:
        out = subprocess.run(
            ["kreadconfig6", "--file", "kdeglobals", "--group", "Colors:Selection", "--key", "DecorationFocus"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        r, g, b = (int(x) for x in out.split(","))
        return QColor(r, g, b)
    except Exception:
        return QColor("#C97932")


def _first_bound_combo(value):
    """kglobalshortcutsrc stores 'Active,Default,FriendlyName', where either
    of the first two fields can be empty or the literal 'none', and each can
    itself hold multiple alternate bindings. KConfig's own ini writer
    escapes the separator between those alternates as a literal backslash+t
    on disk (confirmed live: 'mic_mute=Microphone Mute\\tMeta+Volume Mute,...'),
    not a real tab byte -- kreadconfig6 unescapes it via the KConfig API,
    but plain configparser has no idea, so unescape it ourselves first."""
    parts = value.replace("\\t", "\t").split(",")
    active = parts[0].strip() if len(parts) > 0 else ""
    default = parts[1].strip() if len(parts) > 1 else ""
    for combo in (active, default):
        if combo and combo.lower() != "none":
            return combo.split("\t")[0]
    return None


def _friendly_name(parts, fallback):
    return parts[2].strip() if len(parts) > 2 and parts[2].strip() else fallback


def _system_shortcuts():
    if not KGLOBALSHORTCUTS.is_file():
        return []
    # interpolation=None: shortcut friendly names/values are raw literal
    # strings that can contain a bare "%" (e.g. "Zoom In/Out") -- confirmed
    # live, configparser's default interpolation crashes on those.
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        parser.read(KGLOBALSHORTCUTS)
    except configparser.Error:
        return []

    entries = []
    for section in parser.sections():
        group_label = parser.get(section, "_k_friendly_name", fallback=section)
        for key, value in parser.items(section):
            if key == "_k_friendly_name":
                continue
            combo = _first_bound_combo(value)
            if not combo:
                continue
            entries.append({
                "group": group_label,
                "action": _friendly_name(value.split(","), key),
                "keys": combo.replace("+", " + "),
                "source": "System",
            })
    return entries


def _custom_shortcuts():
    try:
        shortcuts = json.loads(CUSTOM_SHORTCUTS.read_text())
    except Exception:
        return []
    return [
        {
            "group": "Custom (Control Center → Keyboard)",
            "action": s.get("command", ""),
            "keys": s.get("keys", "").replace("+", " + "),
            "source": "Custom",
        }
        for s in shortcuts
        if s.get("keys") and s.get("command")
    ]


class Backend(QObject):
    @Slot(result="QVariantList")
    def shortcuts(self):
        entries = _system_shortcuts() + _custom_shortcuts()
        entries.sort(key=lambda e: (e["group"].lower(), e["action"].lower()))
        return entries


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Shortcuts")
    app.setDesktopFileName("reyos-shortcuts-cheatsheet")
    app.setWindowIcon(QIcon.fromTheme("input-keyboard"))

    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("reyosAccentColor", _reyos_accent_color())
    engine.load(QUrl.fromLocalFile(str(APP_DIR / "qml" / "Main.qml")))

    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
