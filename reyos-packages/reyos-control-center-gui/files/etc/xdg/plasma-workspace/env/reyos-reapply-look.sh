# Sourced by startplasma at every login, before KWin and plasmashell start.
# Package updates reset Look-recolored system files (app icons, window
# border) to copper; this puts the active Look's accent back first.
# looks.py loads no Qt, so this costs a fraction of a second, and it's a
# no-op when nothing needs changing.
python3 /usr/share/reyos/control-center/looks.py --reapply-look >/dev/null 2>&1 || true
