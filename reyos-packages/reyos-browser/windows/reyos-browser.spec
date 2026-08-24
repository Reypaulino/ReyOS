# -*- mode: python ; coding: utf-8 -*-
#
# Build with (on Windows, inside the venv from requirements.txt):
#   pyinstaller windows/reyos-browser.spec
#
# UNTESTED as of 2026-08-24 — no Windows/Wine build environment has been used
# yet. This is a starting point, not a verified build. See the
# reyos-browser-windows-port project memory for what's still open.

from pathlib import Path

BROWSER_DIR = Path(SPECPATH).resolve().parent.parent / "files" / "usr" / "share" / "reyos" / "browser"

a = Analysis(
    [str(BROWSER_DIR / "main.py")],
    pathex=[str(BROWSER_DIR)],
    binaries=[],
    datas=[
        (str(BROWSER_DIR / "qml"), "qml"),
        (str(BROWSER_DIR / "icons"), "icons"),
        (str(BROWSER_DIR / "assets"), "assets"),
        (str(BROWSER_DIR / "home.html"), "."),
        (str(BROWSER_DIR / "password-autofill.js"), "."),
        (str(BROWSER_DIR / "qwebchannel.js"), "."),
        (str(BROWSER_DIR / "fingerprint-protection.js"), "."),
        (str(BROWSER_DIR / "shields-blocklist.txt"), "."),
    ],
    hiddenimports=["keyring.backends.Windows"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ReyOSBrowser",
    # TODO: no .ico exists yet — only assets/reyos-r-penguin.png (PNG) and
    # SVG toolbar icons. PyInstaller needs a real .ico on Windows; generate
    # one (multi-resolution, e.g. via Pillow) before shipping a real build.
    icon=None,
    console=False,
    onefile=True,
)
