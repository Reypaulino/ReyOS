# -*- mode: python ; coding: utf-8 -*-
# Build on Windows inside a venv from requirements.txt:
#   pyinstaller --noconfirm windows/reyos-browser.spec
# Output: dist/ReyOSBrowser/ (a folder, not one file: a one-file build would
# unpack ~300 MB of Qt WebEngine to %TEMP% on every launch).

from pathlib import Path

BROWSER_DIR = Path(SPECPATH).resolve().parent / "files" / "usr" / "share" / "reyos" / "browser"

a = Analysis(
    [str(BROWSER_DIR / "main.py")],
    pathex=[str(BROWSER_DIR)],
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
    excludes=["tkinter", "secretstorage", "setproctitle"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ReyOSBrowser",
    icon=str(BROWSER_DIR / "assets" / "reyos-browser.ico"),
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ReyOSBrowser",
)
