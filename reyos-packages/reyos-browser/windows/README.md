# ReyOS Browser on Windows

Status: code is portable (see `main.py`'s `IS_WINDOWS` branches), packaging is
scaffolded, **nothing has actually been built or run on Windows yet**. No
Windows/Wine/Winboat environment has been used to test this.

## What's portable

- Password storage: Windows Credential Manager via `keyring`, with a local
  `%APPDATA%\ReyOS Browser\password-index.json` tracking which usernames
  exist per site (no secrets in that file — passwords live only in
  Credential Manager). Linux keeps using KWallet/Secret Service, unchanged.
- App state directory: `%APPDATA%\ReyOS Browser` instead of
  `~/.local/share/reyos-browser`.
- Password manager launcher: opens the Windows Credential Manager control
  panel (`control.exe /name Microsoft.CredentialManager`) instead of
  KWalletManager/Seahorse.

## What's not done

- **Desktop notifications** (`notify()`) are a no-op on Windows right now —
  would need `win10toast`/`plyer` or a native WinRT toast call.
- **No `.ico` file exists** — only a PNG (`assets/reyos-r-penguin.png`) and
  SVG toolbar icons. PyInstaller needs a real `.ico` for the `.exe` icon.
- **`reyos-browser.spec` is untested.** It's a reasonable starting point
  (mirrors the file layout PyInstaller needs) but has never actually been
  run through `pyinstaller`.
- **No installer.** Once a working `.exe` exists, wrap it with Inno Setup or
  NSIS for a real installer experience — not started.
- **Unsigned.** Expect a Windows SmartScreen warning on first run until/unless
  code-signing is set up — a separate, later decision.

## Building (once a Windows/Wine environment exists)

```
cd reyos-packages\reyos-browser
python -m venv windows\.venv
windows\.venv\Scripts\activate
pip install -r windows\requirements.txt
pyinstaller windows\reyos-browser.spec
```

Output lands in `dist\ReyOSBrowser.exe`. Test it actually launches, that
Shields/bookmarks/password-save work, before trusting this instruction set.
