# ReyOS WSL — small interactive-shell banner.
# Skip non-interactive shells (scripts, VS Code Remote, scp, CI) and skip
# once already shown for this session so it doesn't reprint in subshells.
case $- in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

if [ -z "$REYOS_WSL_BANNER_SHOWN" ] && [ -f /var/lib/reyos-wsl/initialized ]; then
    export REYOS_WSL_BANNER_SHOWN=1
    printf '\n\033[1;38;2;0;112;255mReyOS WSL\033[0m\n'
    printf 'SIMPLE \xc2\xb7 SAFE \xc2\xb7 READY TO BUILD\n\n'
fi
