# ReyOS WSL — launch first-run setup on the first interactive root login.
# Guarded so it never fires for non-interactive shells (scripts, `wsl -e`,
# remote-exec tooling) and never fires again once initialized.
case $- in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

if [ "$(id -u)" = "0" ] && [ ! -f /var/lib/reyos-wsl/initialized ]; then
    /usr/local/bin/reyos-wsl-init
fi
