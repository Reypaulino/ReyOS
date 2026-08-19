# ReyOS Light KDE Global Theme

A Plasma "Global Theme" (Look and Feel) package: light color scheme (recreated
from Breeze Light) with the same ReyOS blue accent as the dark ReyOS theme,
plus the same branded ReyOS splash screen shown at login/session start.

## Usage

**System Settings → Global Theme → ReyOS Light → Apply**
Colors alone: **System Settings → Colors → ReyOS Light**

## What's in the package

```
ReyOSLight.colors                     — color scheme (Breeze Light base + ReyOS blue accent)
org.reyos.light.desktop/
  metadata.json                       — theme identity
  contents/
    defaults                          — tells Plasma which colors/icons/splash to use
    splash/Splash.qml                 — the login splash screen (shared with org.reyos.desktop)
    splash/images/watermark.png       — ReyOS logo (shared with org.reyos.desktop)
    previews/preview.png              — thumbnail shown in the theme picker (currently reuses
                                         the dark theme's preview -- not visually accurate,
                                         swap in a real light-theme screenshot when available)
```

## How the colors relate to Breeze Light

Kept Breeze Light's backgrounds/foregrounds (the parts that make it "light"
and legible) and re-skinned only the brand-specific colors, mirroring exactly
what `org.reyos.desktop` (dark) already does relative to Breeze Dark:

- Accent (DecorationFocus/Hover, ForegroundActive, ForegroundLink): `90,170,255`
- Negative: `237,90,90` · Neutral: `246,190,90` · Positive: `90,200,140` · Visited: `170,130,220`
- Selection block copied verbatim from the dark ReyOS scheme (same blue
  highlight regardless of light/dark base)
