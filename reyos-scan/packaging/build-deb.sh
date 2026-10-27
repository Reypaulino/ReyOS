#!/bin/sh
# Builds reyos-scan_<version>_all.deb from this folder with dpkg-deb only (no
# debhelper), reproducibly: fixed file times (SOURCE_DATE_EPOCH, default =
# the last git commit), root ownership, sorted file list.
# Usage: packaging/build-deb.sh [output-dir]   (Ubuntu/Debian, needs dpkg-deb)
set -eu
cd "$(dirname "$0")/.."
VERSION=$(python3 -c 'import sys; sys.path.insert(0, "."); from reyos_scan import core; print(core.VERSION)')
OUT=${1:-dist}
: "${SOURCE_DATE_EPOCH:=$(git log -1 --format=%ct 2>/dev/null || date +%s)}"
export SOURCE_DATE_EPOCH
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
R="$STAGE/root"
install -d "$R/DEBIAN" "$R/usr/bin" "$R/usr/lib/reyos-scan/reyos_scan" "$R/usr/share/applications" \
    "$R/usr/share/icons/hicolor/scalable/apps" "$R/usr/share/doc/reyos-scan"
install -m 644 reyos_scan/__init__.py reyos_scan/core.py reyos_scan/cli.py reyos_scan/qt.py reyos_scan/gui.py \
    "$R/usr/lib/reyos-scan/reyos_scan/"
install -m 755 bin/reyos-scan bin/reyos-scan-gui "$R/usr/bin/"
install -m 644 data/reyos-scan.desktop "$R/usr/share/applications/"
install -m 644 data/reyos-scan.svg "$R/usr/share/icons/hicolor/scalable/apps/"
install -m 644 README.md "$R/usr/share/doc/reyos-scan/"
cat > "$R/usr/share/doc/reyos-scan/copyright" <<COPY
ReyOS Scan $VERSION. Copyright Reynaldo Paulino. MIT license.
Uses ClamAV (GPL-2.0), installed separately from Ubuntu.
COPY
chmod 644 "$R/usr/share/doc/reyos-scan/copyright"
SIZE=$(du -sk --exclude=DEBIAN "$R" | cut -f1)
cat > "$R/DEBIAN/control" <<CTRL
Package: reyos-scan
Version: $VERSION
Architecture: all
Maintainer: Rey Paulino <packages@reyapps.com>
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-pyqt6 | python3-pyside6, clamav (>= 1.0), clamav-freshclam
Section: utils
Priority: optional
Homepage: https://github.com/Reypaulino/ReyOS
Description: ReyOS Scan: on-demand malware scanner for files and game installers
 Scans Downloads/Desktop, a folder, an external drive or the home folder
 with ClamAV, checks Windows game installers and the programs next to them
 before they run, and keeps a private quarantine with SHA-256-verified
 restore. Runs as the user, on demand: no background scanner. Virus
 definitions are kept up to date by Ubuntu's clamav-freshclam service.
CTRL
# Icon/menu caches; nothing else to do on removal: reports and quarantine stay
# in ~/.local/share/reyos/security (they're the user's).
cat > "$R/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
    command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
fi
POST
cp "$R/DEBIAN/postinst" "$R/DEBIAN/postrm"
sed -i 's/= configure/= remove/' "$R/DEBIAN/postrm"
chmod 755 "$R/DEBIAN/postinst" "$R/DEBIAN/postrm"
find "$R" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
mkdir -p "$OUT"
DEB="$OUT/reyos-scan_${VERSION}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$R" "$DEB" >/dev/null
echo "$DEB"
sha256sum "$DEB"
