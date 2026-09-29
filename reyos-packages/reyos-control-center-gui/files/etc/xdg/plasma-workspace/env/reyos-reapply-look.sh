# Sourced by startplasma at every login, before KWin and plasmashell start.
# Package updates reset Look-recolored system files (app icons, window
# border) to copper; this puts the active Look's accent back first.
/usr/share/reyos/control-center/main.py --reapply-look >/dev/null 2>&1 || true
