#!/usr/bin/env bash
# ReyOS WSL — first-run setup wizard.
# Runs once, as root, on the first interactive login (triggered by
# /etc/profile.d/reyos-wsl-firstrun.sh). Installed into the image at
# /usr/local/bin/reyos-wsl-init by wsl/build.sh.
set -euo pipefail

MARKER_DIR=/var/lib/reyos-wsl
MARKER="$MARKER_DIR/initialized"
PKGLIST_DIR=/usr/share/reyos-wsl/package-lists

mkdir -p "$MARKER_DIR"

printf '\n\033[1;38;2;0;112;255m'
cat <<'EOF'
  ____             ___  ____
 |  _ \ ___ _   _  / _ \/ ___|
 | |_) / _ \ | | || | | \___ \
 |  _ <  __/ |_| || |_| |___) |
 |_| \_\___|\__, (_)___/|____/
            |___/       WSL
EOF
printf '\033[0m'
echo "SIMPLE · SAFE · READY TO BUILD"
echo
echo "Welcome to ReyOS WSL — first-time setup."
echo

# --- username ---------------------------------------------------------
while true; do
    read -r -p "Username: " REYOS_USER
    if [[ "$REYOS_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] && ! id "$REYOS_USER" &>/dev/null; then
        break
    fi
    echo "Enter a valid, unused lowercase username (e.g. rey)."
done

useradd -m -G wheel -s /bin/bash "$REYOS_USER"
echo "Set a password for $REYOS_USER:"
passwd "$REYOS_USER"

echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/g_wheel
chmod 0440 /etc/sudoers.d/g_wheel

# --- development profile ----------------------------------------------
echo
echo "Development environment:"
echo "  [1] Minimal      (already installed, nothing further to add)"
echo "  [2] Developer     (git, base-devel, Python, Node.js)"
echo "  [3] ReyOS Developer (adds tools to build real reyos-* packages)"
read -r -p "Choose [1-3, default 1]: " PROFILE_CHOICE
PROFILE_CHOICE="${PROFILE_CHOICE:-1}"

install_list() {
    mapfile -t pkgs < <(grep -vE '^\s*#|^\s*$' "$1")
    pacman -Sy --needed --noconfirm "${pkgs[@]}"
}

case "$PROFILE_CHOICE" in
    2)
        install_list "$PKGLIST_DIR/developer.txt"
        ;;
    3)
        install_list "$PKGLIST_DIR/developer.txt"
        install_list "$PKGLIST_DIR/reyos-developer.txt"
        ;;
    *)
        echo "Staying on Minimal."
        ;;
esac

# --- confirm ReyOS repositories ----------------------------------------
echo
echo "ReyOS package repositories:"
pacman-conf --repo-list | sed 's/^/  - /'
echo "(reyos-local has no public host yet — see docs/wsl.md. Upstream"
echo " Arch/CachyOS repos above are live and update normally.)"

# --- default user --------------------------------------------------------
sed -i "s/^default=.*/default=$REYOS_USER/" /etc/wsl.conf

touch "$MARKER"
chown -R "$REYOS_USER:$REYOS_USER" "/home/$REYOS_USER"

echo
echo "Setup complete. Restart this distro to log in as $REYOS_USER:"
echo "  (from PowerShell)  wsl -t ReyOS"
echo "  (then)             wsl -d ReyOS"
echo
