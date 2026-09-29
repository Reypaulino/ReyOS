#!/bin/sh
# Builds the Ubuntu/Debian .deb for reyos-browser from this repo's
# tracked source (previously the Debian packaging lived only in an
# untracked host directory -- see docs/whats-next.md's 2026-08-24 entry).
#
# Usage: ./build.sh <deb-version, e.g. 0.1.0-112ubuntu1>
#
# Must run on a real Debian/Ubuntu machine with dpkg-deb available
# (not inside a Flatpak sandbox). Matches the project's existing
# pattern of verifying .deb installs in a clean ubuntu:24.04 container
# before publishing.
set -e

if [ -z "$1" ]; then
    echo "usage: $0 <version>  (e.g. 0.1.0-112ubuntu1)" >&2
    exit 1
fi

VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_ROOT="$SCRIPT_DIR/.."
SRC_APP="$PKG_ROOT/files/usr/share/reyos/browser"
SRC_ICON="$PKG_ROOT/files/usr/share/icons/hicolor/scalable/apps/reyos-browser.svg"
STAGE="$(mktemp -d)"

mkdir -p "$STAGE/DEBIAN"
mkdir -p "$STAGE/opt/reyos-browser"
mkdir -p "$STAGE/usr/bin"
mkdir -p "$STAGE/usr/share/applications"
mkdir -p "$STAGE/usr/share/icons/hicolor/scalable/apps"

sed "s/^Version: REPLACE_VERSION/Version: $VERSION/" "$SCRIPT_DIR/control" > "$STAGE/DEBIAN/control"
cp "$SCRIPT_DIR/postinst" "$STAGE/DEBIAN/postinst"
cp "$SCRIPT_DIR/postrm" "$STAGE/DEBIAN/postrm"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

cp -a "$SRC_APP"/. "$STAGE/opt/reyos-browser/"
rm -rf "$STAGE/opt/reyos-browser/__pycache__"
cp "$SCRIPT_DIR/requirements.txt" "$STAGE/opt/reyos-browser/requirements.txt"

cp "$SCRIPT_DIR/reyos-browser" "$STAGE/usr/bin/reyos-browser"
chmod 755 "$STAGE/usr/bin/reyos-browser"
chmod 755 "$STAGE/opt/reyos-browser/main.py"
find "$STAGE/opt/reyos-browser" -type f -exec chmod 644 {} \;
chmod 755 "$STAGE/usr/bin/reyos-browser"

cp "$SCRIPT_DIR/reyos-browser.desktop" "$STAGE/usr/share/applications/reyos-browser.desktop"
cp "$SRC_ICON" "$STAGE/usr/share/icons/hicolor/scalable/apps/reyos-browser.svg"

OUT="reyos-browser_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
rm -rf "$STAGE"

echo "built $OUT"
echo "test in a clean container first, e.g.:"
echo "  docker run --rm -v \$PWD/$OUT:/pkg.deb ubuntu:24.04 sh -c 'apt update && apt install -y /pkg.deb'"
