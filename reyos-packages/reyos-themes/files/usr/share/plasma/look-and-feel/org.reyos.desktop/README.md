# ReyOS KDE Global Theme

A Plasma "Global Theme" (Look and Feel) package: dark color scheme with a blue
accent, plus a branded ReyOS splash screen shown at login/session start.
Works on any KDE Plasma desktop — Ubuntu w/ KDE, CachyOS, Kubuntu, etc.

## Requirements

KDE Plasma desktop (Plasma 5.24+ or Plasma 6). Not applicable to GNOME, XFCE, etc.

## Usage

Run as your **normal user** (not root):

```
chmod +x install-kde-theme.sh
./install-kde-theme.sh
```

Then:
- If it didn't auto-apply: **System Settings → Global Theme → ReyOS → Apply**
- Colors alone: **System Settings → Colors → ReyOS**
- The splash screen appears on your *next login*, not instantly

## What's in the package

```
ReyOS.colors                          — color scheme (dark + blue accent)
org.reyos.desktop/
  metadata.json                       — theme identity
  contents/
    defaults                          — tells Plasma which colors/icons/splash to use
    splash/Splash.qml                 — the login splash screen
    splash/images/watermark.png       — placeholder logo (swap for final logo later)
    previews/preview.png              — thumbnail shown in the theme picker
```

## Swapping in your final logo

Once you have the real ReyOS logo:
```
cp reyos-logo.png org.reyos.desktop/contents/splash/images/watermark.png
```
Re-run the install script, or just copy that one file to:
`~/.local/share/plasma/look-and-feel/org.reyos.desktop/contents/splash/images/watermark.png`

## Uninstalling

```
rm -rf ~/.local/share/plasma/look-and-feel/org.reyos.desktop
rm ~/.local/share/color-schemes/ReyOS.colors
```
Then pick a different theme in System Settings → Global Theme.

## Next: login screen (SDDM)

This package themes the *desktop session* (colors, splash after login). The
SDDM **login screen itself** (before you log in) is a separate theme system —
that's the next piece to build.
