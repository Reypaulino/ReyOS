#!/bin/bash
# Privileged helper for ReyOS Control Center's Users & Groups page. Invoked
# exclusively via pkexec (see org.reyos.controlcenter.policy) -- never run
# directly, since it trusts $PKEXEC_UID to know who is making the request
# and refuses to let that account touch itself (see below).
#
# Password bytes (for add/setpassword) are read from stdin, never argv --
# pkexec forwards the caller's stdin unchanged, so the plaintext never shows
# up in `ps aux` the way a command-line argument would.
set -e

if [ -z "$PKEXEC_UID" ]; then
    echo "This script must be run via pkexec." >&2
    exit 1
fi

ACTION="$1"
TARGET_USER="$2"

if ! [[ "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    echo "Invalid username: $TARGET_USER" >&2
    exit 1
fi

CALLER=$(id -nu "$PKEXEC_UID")

# Never let this run against the account making the request (locking
# yourself out of your own admin session) or against a system account
# (UID below the distro's normal-user floor, e.g. root/daemon/nobody).
guard_not_self_or_system() {
    if [ "$TARGET_USER" = "$CALLER" ]; then
        echo "Refusing to act on your own account ($CALLER)." >&2
        exit 1
    fi
    local uid
    uid=$(id -u "$TARGET_USER" 2>/dev/null) || return 0
    if [ "$uid" -lt 1000 ]; then
        echo "Refusing to act on a system account: $TARGET_USER" >&2
        exit 1
    fi
}

case "$ACTION" in
    add)
        FULLNAME="$3"
        MAKE_ADMIN="$4"
        if getent passwd "$TARGET_USER" > /dev/null; then
            echo "User already exists: $TARGET_USER" >&2
            exit 1
        fi
        useradd -m -c "$FULLNAME" -s /bin/bash "$TARGET_USER"
        chpasswd <<< "${TARGET_USER}:$(cat)"
        [ "$MAKE_ADMIN" = "1" ] && usermod -aG wheel "$TARGET_USER"
        ;;
    delete)
        REMOVE_HOME="$3"
        guard_not_self_or_system
        if [ "$REMOVE_HOME" = "1" ]; then
            userdel -r "$TARGET_USER"
        else
            userdel "$TARGET_USER"
        fi
        ;;
    setpassword)
        guard_not_self_or_system
        chpasswd <<< "${TARGET_USER}:$(cat)"
        ;;
    setadmin)
        ENABLE="$3"
        guard_not_self_or_system
        if [ "$ENABLE" = "1" ]; then
            usermod -aG wheel "$TARGET_USER"
        else
            # Refuse to strip the last remaining wheel-group member --
            # that would leave no admin account able to sudo at all.
            WHEEL_COUNT=$(getent group wheel | cut -d: -f4 | tr ',' '\n' | grep -c .)
            if [ "$WHEEL_COUNT" -le 1 ]; then
                echo "Refusing to remove the last admin account." >&2
                exit 1
            fi
            gpasswd -d "$TARGET_USER" wheel
        fi
        ;;
    *)
        echo "Unknown action: $ACTION" >&2
        exit 1
        ;;
esac
