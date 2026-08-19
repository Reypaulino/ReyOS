#
# ~/.bashrc — ReyOS default
#

[[ $- != *i* ]] && return

HISTCONTROL=ignoreboth
HISTSIZE=2000
HISTFILESIZE=4000
shopt -s checkwinsize

PS1='\[\e[1;38;2;201;121;50m\]\u@\h\[\e[0m\]:\[\e[1;38;2;255;243;230m\]\w\[\e[0m\]\$ '

alias ls='ls --color=auto'
alias ll='ls -lah --color=auto'
alias grep='grep --color=auto'
alias update='sudo pacman -Syu'

# reyos-terminal ships the neofetch config + ASCII art but never actually
# called neofetch anywhere — this is the hook.
command -v neofetch &>/dev/null && neofetch

# ReyOS quick-launcher — offered once per new terminal
if [[ $- == *i* ]]; then
  printf "  \e[1;38;2;240;180;106m[1]\e[0m System Tools   \e[2;38;2;215;193;170m[Enter] Regular terminal\e[0m  "
  read -r -n 1 _reyos_choice
  echo ""
  case "$_reyos_choice" in
    1) bash /usr/share/reyos/bin/reyos-system-menu.sh ;;
  esac
  unset _reyos_choice
fi
