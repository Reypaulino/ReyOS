#!/bin/bash
# Privileged helper for ReyOS Control Center's "Fix folder permissions" action.
# Invoked exclusively via pkexec (see org.reyos.controlcenter.policy) -- never
# run directly, since it trusts $PKEXEC_UID to know which user to chown to.
set -e

FOLDER="$1"
MODE="$2"

if [ -z "$PKEXEC_UID" ]; then
    echo "This script must be run via pkexec." >&2
    exit 1
fi

REAL=$(realpath -m -- "$FOLDER" 2>/dev/null)
if [ -z "$REAL" ] || [ ! -e "$REAL" ]; then
    echo "Path does not exist: $FOLDER" >&2
    exit 1
fi

case "$REAL" in
    /|/etc|/etc/*|/usr|/usr/*|/bin|/bin/*|/sbin|/sbin/*|/boot|/boot/*|/root|/root/*|/var|/var/*|/sys|/sys/*|/proc|/proc/*|/dev|/dev/*|/lib|/lib/*|/lib64|/lib64/*|/opt|/opt/*)
        echo "Refusing to modify a protected system path: $REAL" >&2
        exit 1
        ;;
esac

TARGET_USER=$(id -nu "$PKEXEC_UID")
chown -R "$TARGET_USER:$TARGET_USER" -- "$REAL"

case "$MODE" in
    write)
        chmod -R u+w -- "$REAL"
        ;;
    own)
        chmod -R u+rw -- "$REAL"
        ;;
    custom:*)
        chmod -R "${MODE#custom:}" -- "$REAL"
        ;;
    *)
        echo "Unknown mode: $MODE" >&2
        exit 1
        ;;
esac
