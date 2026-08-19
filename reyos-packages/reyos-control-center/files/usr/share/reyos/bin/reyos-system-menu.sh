#!/bin/bash
#
# ReyOS System Tools — terminal quick-launcher for system care, updates,
# network, and disk utilities. Adapted from a personal dev-machine tool;
# trimmed to remove anything tied to one person's own infrastructure
# (hardcoded passwords, a specific Raspberry Pi, a curated personal app
# list) so it's safe to ship to every real ReyOS install.

# Force a UTF-8 locale for this script's own string-length math regardless
# of the caller's environment. Without it (confirmed live: LANG/LC_ALL both
# empty, LC_CTYPE falls back to POSIX/C), bash's ${#var} counts *bytes*,
# not characters -- every row renders fine except the CPU/RAM stats row,
# whose progress bars use multi-byte UTF-8 block characters (█/░, 3 bytes
# each in UTF-8). That row's padding came out short by 2 bytes per filled
# bar segment, so its right border landed several columns before every
# other row's, making the whole box's right edge visibly ragged.
export LC_ALL=C.utf8

# Midnight Copper terminal palette — true-color escape sequences work in Konsole.
CYN=$'\033[1;38;2;201;121;50m'    # copper: borders and system actions
YLW=$'\033[1;38;2;240;180;106m'    # copper highlight: prompts and attention
GRN=$'\033[0;38;2;154;216;174m'    # success
RED=$'\033[0;38;2;237;90;90m'     # warning/error
WHT=$'\033[1;38;2;255;243;230m'   # ivory heading
DIM=$'\033[2;38;2;215;193;170m'    # warm muted detail
RST=$'\033[0m'

STAT_ROW=4     # row where stats start (after clear)
PROMPT_ROW=0   # zero-indexed row of the in-menu input field -- computed fresh in draw_menu()
PROMPT_COL=19  # column immediately after "  Select option: "

SUDO_READY=0
SUDO_KEEPALIVE_PID=""
ensure_sudo() {
  [ "$SUDO_READY" -eq 1 ] && return 0
  if ! sudo -n true 2>/dev/null; then
    echo ""
    printf "  ${YLW}Sudo password required for this action.${RST}\n"
    sudo -v || { printf "  ${RED}Authentication failed.${RST}\n"; return 1; }
  fi
  # keep the sudo credential cache alive for the rest of the session so
  # later actions (updates, system care, permissions, reboot...)
  # don't prompt again
  ( while kill -0 "$$" 2>/dev/null; do sudo -n true 2>/dev/null; sleep 60; done ) &
  disown
  SUDO_KEEPALIVE_PID=$!
  SUDO_READY=1
}

# `sysctl -w` only changes live kernel state -- persist the same value to a
# sysctl.d drop-in so it survives reboot instead of silently reverting.
persist_swappiness() {
  printf 'vm.swappiness=%s\n' "$1" | sudo tee /etc/sysctl.d/99-reyos-swappiness.conf > /dev/null
}

pkg_check_updates() { checkupdates 2>/dev/null; }
is_live_session() { mountpoint -q /run/archiso/airootfs; }
pkg_full() {
  if is_live_session; then
    printf "  ${YLW}Updates are disabled in the live session. Install ReyOS first, then update the installed system.${RST}\n"
    return 2
  fi
  sudo pacman -Syu
}
pkg_clean() {
  local -a ORPHANS=()
  mapfile -t ORPHANS < <(pacman -Qtdq 2>/dev/null)
  ((${#ORPHANS[@]})) && sudo pacman -Rns --noconfirm "${ORPHANS[@]}"
  sudo pacman -Sc --noconfirm
}
pkg_list_orphans() { pacman -Qtdq 2>/dev/null; }

UPDATE_STAMP="$HOME/.last_pkg_update"
UPDATE_INTERVAL_DAYS=3

# stty reads the tty driver's actual window size directly, more reliable
# than tput's terminfo/COLUMNS-based lookup, which can come back empty
# right when a terminal first spawns and $TERM/the pty geometry haven't
# been fully wired up yet (the same class of "script runs before the
# environment has settled" race hit elsewhere in this project). Retry
# briefly before falling back, rather than trusting a single blind read.
TERM_ROWS=0
TERM_COLS=0
read_term_size() {
  local out attempt
  for attempt in 1 2 3 4 5; do
    out=$(stty size 2>/dev/null)
    if [ -n "$out" ]; then
      TERM_ROWS=${out% *}
      TERM_COLS=${out#* }
      [ -n "$TERM_ROWS" ] && [ -n "$TERM_COLS" ] && return 0
    fi
    sleep 0.1
  done
  TERM_ROWS=$(tput lines 2>/dev/null)
  TERM_COLS=$(tput cols 2>/dev/null)
}

borders() {
  read_term_size
  TW=$TERM_COLS
  [ -z "$TW" ] && TW=80
  [ "$TW" -lt 60 ] && TW=60
  # One column of safety margin -- some terminal/font combinations render
  # box-drawing characters a hair wider than the reported cell width.
  TW=$((TW - 1))
  # Cap the box at a comfortable reading width instead of always
  # stretching to fill the terminal -- on a wide window this content
  # (menu labels, stats) is nowhere near wide enough to fill it, and an
  # uncapped box just leaves a huge empty gap before the right border on
  # every row, which reads as broken even though it's rendering exactly
  # as instructed.
  [ "$TW" -gt 100 ] && TW=100
  IW=$((TW - 4))
  LINE=$(printf '═%.0s' $(seq 1 $((TW - 2))))
  TOP="${CYN}╔${LINE}╗${RST}"
  MID="${CYN}╠${LINE}╣${RST}"
  BOT="${CYN}╚${LINE}╝${RST}"
}

row() {
  printf "${CYN}║${RST} %-${IW}s ${CYN}║${RST}\n" "$1"
  LINE_COUNT=$((LINE_COUNT + 1))
}

crow() {
  local visible
  visible=$(printf '%s' "$1" | sed 's/\x1b\[[0-9;]*m//g')
  local pad=$(( IW - ${#visible} ))
  [ "$pad" -lt 0 ] && pad=0
  printf "${CYN}║${RST} %s%${pad}s ${CYN}║${RST}\n" "$1" ""
  LINE_COUNT=$((LINE_COUNT + 1))
}

border_line() {
  printf '%s\n' "$1"
  LINE_COUNT=$((LINE_COUNT + 1))
}

gather_stats() {
  local u1 n1 sys1 i1 w1 x1 y1 u2 n2 sys2 i2 w2 x2 y2
  read -r _ u1 n1 sys1 i1 w1 x1 y1 _ < <(grep -m1 '^cpu ' /proc/stat)
  sleep 0.2
  read -r _ u2 n2 sys2 i2 w2 x2 y2 _ < <(grep -m1 '^cpu ' /proc/stat)
  local t1=$((u1+n1+sys1+i1+w1+x1+y1)) t2=$((u2+n2+sys2+i2+w2+x2+y2))
  CPU=$(awk "BEGIN{printf \"%.1f\", (1-($i2-$i1)/($t2-$t1))*100}")
  read -r _ MEM_TOTAL MEM_USED _   < <(free -m | grep '^Mem:')
  read -r _ SWAP_TOTAL SWAP_USED _ < <(free -m | grep '^Swap:')
  MEM_PCT=$(awk "BEGIN{printf \"%.0f\", ($MEM_USED/$MEM_TOTAL)*100}")
  if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
    GOVERNOR=$(< /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
  else
    GOVERNOR="N/A"
  fi
  SWAPPINESS=$(< /proc/sys/vm/swappiness)
  SWAP_ON=$(swapon --show 2>/dev/null | tail -n +2 | grep -c ".")
  [ "$SWAP_ON" -gt 0 ] && SWAP_STATUS="ON" || SWAP_STATUS="OFF"
  UPTIME=$(uptime -p 2>/dev/null | sed 's/up //' || echo "N/A")
}

# Exactly 5 lines — called for both initial draw and live refresh
print_stats() {
  local cpu_bar="" ram_bar="" i filled empty
  filled=$(awk -v c="$CPU" 'BEGIN{printf "%d", c/10+0}')
  empty=$(( 10 - filled ))
  for ((i=0; i<filled; i++)); do cpu_bar+="█"; done
  for ((i=0; i<empty;  i++)); do cpu_bar+="░"; done
  filled=$(awk -v u="$MEM_USED" -v t="$MEM_TOTAL" 'BEGIN{if(t>0)printf "%d",(u/t)*10;else print 0}')
  empty=$(( 10 - filled ))
  for ((i=0; i<filled; i++)); do ram_bar+="█"; done
  for ((i=0; i<empty;  i++)); do ram_bar+="░"; done
  crow "  ${YLW}CPU${RST}  ${cpu_bar}  ${YLW}${CPU}%${RST}          ${GRN}RAM${RST}  ${ram_bar}  ${GRN}${MEM_USED} / ${MEM_TOTAL} MB  (${MEM_PCT}%)${RST}"
  crow "  ${DIM}Swap  ${SWAP_USED} / ${SWAP_TOTAL} MB   ·   Status  ${RST}${CYN}${SWAP_STATUS}${RST}"
  row  ""
  crow "  ${DIM}Governor${RST}  ${CYN}${GOVERNOR}${RST}   ${DIM}·   Swappiness${RST}  ${CYN}${SWAPPINESS}${RST}   ${DIM}·   Up${RST}  ${CYN}${UPTIME}${RST}"
  row  ""
}

refresh_stats() {
  gather_stats
  tput cup $STAT_ROW 0
  print_stats
}

show_cpu_hogs() {
  local key
  while true; do
    clear
    borders
    printf '%s\n' "$TOP"
    crow "  ${WHT}CPU HOGS${RST}   ${DIM}$(date '+%H:%M:%S')${RST}    ${YLW}[R]${RST} refresh   ${RED}[Q]${RST} quit"
    printf '%s\n' "$MID"
    crow "  ${WHT}$(printf '%-7s  %-12s  %-6s  %-6s  %-6s  %-9s  %s' 'PID' 'USER' 'CPU%' 'MEM%' 'STAT' 'TIME' 'COMMAND')${RST}"
    printf '%s\n' "$MID"
    while read -r user pid cpu mem stat time cmd; do
      if   awk "BEGIN{exit !($cpu+0 >= 50)}"; then col=$RED
      elif awk "BEGIN{exit !($cpu+0 >= 20)}"; then col=$YLW
      else col=$GRN; fi
      crow "  $(printf '%-7s  %-12s' "$pid" "$user")  ${col}$(printf '%-6s' "$cpu")${RST}  $(printf '%-6s  %-6s  %-9s  %s' "$mem" "$stat" "$time" "$cmd")"
    done < <(ps aux --sort=-%cpu | awk 'NR>1 {print $1,$2,$3,$4,$8,$10,$11}' | head -20)
    printf '%s\n' "$BOT"
    echo ""
    printf "  ${YLW}Press R to refresh, Q to quit:${RST} "
    read -rn1 key
    echo ""
    [[ "$key" =~ ^[Qq]$ ]] && break
  done
}

copy_network() {
  echo ""
  printf "  ${YLW}What to copy?  [1] File   [2] Folder   [0] Cancel:${RST} "
  read -r type_choice
  case $type_choice in
    1) src=$(zenity --file-selection \
         --title="Select file to copy" \
         --filename="$HOME/" 2>/dev/null) ;;
    2) src=$(zenity --file-selection --directory \
         --title="Select folder to copy" \
         --filename="$HOME/" 2>/dev/null) ;;
    0|"") printf "  ${DIM}Cancelled.${RST}\n"; sleep 1; return ;;
    *)    printf "  ${RED}Invalid.${RST}\n"; sleep 1; return ;;
  esac
  [ -z "$src" ] && printf "  ${DIM}Cancelled.${RST}\n" && return
  printf "  ${GRN}Selected:${RST} %s\n" "$src"
  echo ""
  printf "  ${YLW}Host (user@ip):${RST} "; read -r RHOST
  [ -z "$RHOST" ] && printf "  ${DIM}Cancelled.${RST}\n" && return
  printf "  ${YLW}Destination path [default: ~/]:${RST} "; read -r rdest
  [ -z "$rdest" ] && rdest="~/"

  echo ""
  printf "  ${CYN}Copying '%s'  →  %s:%s ...${RST}\n\n" "$src" "$RHOST" "$rdest"
  rsync -avh --progress -e "ssh -o StrictHostKeyChecking=accept-new" "$src" "${RHOST}:${rdest}"
  local rc=$?
  echo ""
  [ $rc -eq 0 ] && printf "  ${GRN}Done.${RST}\n" || printf "  ${RED}rsync failed (exit %d).${RST}\n" "$rc"
  read -rp "  Press Enter to return to menu..."
}

show_network() {
  local key
  while true; do
    clear
    borders
    printf '%s\n' "$TOP"
    crow "  ${WHT}NETWORK INFO${RST}   ${DIM}$(date '+%H:%M:%S')${RST}    ${YLW}[R]${RST} refresh   ${RED}[Q]${RST} quit"
    printf '%s\n' "$MID"

    crow "  ${YLW}IP ADDRESSES${RST}"
    printf '%s\n' "$MID"
    while IFS= read -r line; do crow "  $line"; done < <(
      ip -4 addr | awk '
        /^[0-9]+:/ { iface=$2; gsub(/:$/,"",iface) }
        /inet /    { printf "%-12s  %s\n", iface, $2 }
      '
    )
    printf '%s\n' "$MID"

    crow "  ${YLW}GATEWAY${RST}"
    printf '%s\n' "$MID"
    while IFS= read -r line; do crow "  $line"; done < <(ip route | grep default)
    printf '%s\n' "$MID"

    crow "  ${YLW}LISTENING PORTS${RST}"
    printf '%s\n' "$MID"
    crow "  $(printf '%-5s  %-30s' 'Proto' 'Address:Port')"
    printf '%s\n' "$MID"
    while IFS= read -r line; do crow "  $line"; done < <(
      ss -tuln 2>/dev/null | awk 'NR>1 && /LISTEN/ {
        printf "%-5s  %s\n", $1, $5
      }' | sort -t: -k2 -n
    )
    printf '%s\n' "$BOT"
    echo ""
    printf "  ${YLW}Press R to refresh, Q to quit:${RST} "
    read -rn1 key
    [[ "$key" =~ ^[Qq]$ ]] && break
  done
}

system_updates() {
  local updates update_rc confirm
  while true; do
    printf "\n  System Updates (pacman)\n\n  [1] Check for updates (no changes)\n  [2] Install updates (atomic sync + upgrade)\n  [3] Remove old packages\n  [0] Back\n\n  Select: "
    read -r upd_choice
    case $upd_choice in
      1) updates=$(pkg_check_updates); update_rc=$?
         if [ "$update_rc" -eq 0 ]; then printf "%s\n" "$updates"; elif [ "$update_rc" -eq 2 ]; then printf "  Your packages are up to date.\n"; else printf "  Could not check updates. Verify your network connection.\n"; fi
         read -rp "  Press Enter to return..." ;;
      2) ensure_sudo || continue
         if pkg_full; then touch "$UPDATE_STAMP"; printf "  Updates installed.\n"; else printf "  Update failed; no completion record was written.\n"; fi
         read -rp "  Press Enter to return..." ;;
      3) ensure_sudo || continue
         printf "  Remove orphaned packages and clean cache? (y/N): "; read -r confirm
         [[ "$confirm" =~ ^[Yy]$ ]] && pkg_clean
         read -rp "  Press Enter to return..." ;;
      0|"") return ;;
      *) printf "  Invalid selection.\n" ;;
    esac
  done
}

show_disk() {
  local key
  while true; do
    clear
    borders
    printf '%s\n' "$TOP"
    crow "  ${WHT}DISK SPACE${RST}   ${DIM}$(date '+%a %d %b %Y  %H:%M:%S')${RST}    ${YLW}[R]${RST} refresh   ${RED}[Q]${RST} quit"
    printf '%s\n' "$MID"

    crow "  $(printf '%-28s  %6s  %6s  %6s  %5s  %s' 'Filesystem' 'Size' 'Used' 'Avail' 'Use%' 'Mounted on')"
    printf '%s\n' "$MID"
    while read -r src sz used avail pct mnt; do
      local p=${pct//%/}
      if   [ "${p:-0}" -ge 90 ] 2>/dev/null; then col=$RED
      elif [ "${p:-0}" -ge 70 ] 2>/dev/null; then col=$YLW
      else col=$GRN; fi
      crow "  ${col}$(printf '%-28s  %6s  %6s  %6s  %5s  %s' "$src" "$sz" "$used" "$avail" "$pct" "$mnt")${RST}"
    done < <(df -h --output=source,size,used,avail,pcent,target 2>/dev/null \
             | grep -Ev '^(tmpfs|udev|Filesystem|none)')
    printf '%s\n' "$MID"

    crow "  ${YLW}LARGEST ITEMS IN ~/${RST}   ${DIM}(top 15 — node_modules/.git excluded)${RST}"
    printf '%s\n' "$MID"
    while IFS=$'\t' read -r sz path; do
      crow "  ${CYN}$(printf '%7s' "$sz")${RST}  $path"
    done < <(du -sh \
               --exclude='node_modules' \
               --exclude='.git' \
               --exclude='.cache' \
               "$HOME"/* 2>/dev/null \
             | sort -rh | head -15)
    printf '%s\n' "$BOT"
    echo ""
    printf "  ${YLW}Press R to refresh, Q to quit:${RST} "
    read -rn1 key
    [[ "$key" =~ ^[Qq]$ ]] && break
  done
}

package_inspector() {
  local term matches count idx choice pkg action confirm required_by
  echo ""
  printf "  ${WHT}Package Inspector${RST}\n\n"
  printf "  ${YLW}Package name or search term (blank to cancel): ${RST}"
  read -r term
  [ -z "$term" ] && { printf "  ${DIM}Cancelled.${RST}\n"; return; }

  mapfile -t matches < <(pacman -Qq 2>/dev/null | grep -i -- "$term")
  count=${#matches[@]}
  if [ "$count" -eq 0 ]; then
    printf "  ${RED}No installed package matches \"%s\".${RST}\n" "$term"
    return
  elif [ "$count" -eq 1 ]; then
    pkg="${matches[0]}"
  else
    echo ""
    printf "  ${YLW}%d matches:${RST}\n" "$count"
    for idx in "${!matches[@]}"; do
      printf "  ${CYN}[%2d]${RST}  %s\n" "$((idx + 1))" "${matches[$idx]}"
    done
    printf "  ${RED}[ 0]${RST}  Cancel\n\n  Select: "
    read -r choice
    [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ] || { printf "  ${DIM}Cancelled.${RST}\n"; return; }
    pkg="${matches[$((choice - 1))]}"
  fi

  while true; do
    clear
    borders
    printf '%s\n' "$TOP"
    crow "  ${WHT}PACKAGE: ${pkg}${RST}"
    printf '%s\n' "$MID"
    # pacman -Qi is entirely local (reads the installed package's own
    # metadata) -- no sudo, no network, safe to run for any package name.
    while IFS= read -r info_line; do
      row "$info_line"
    done < <(pacman -Qi -- "$pkg" 2>/dev/null)
    printf '%s\n' "$BOT"
    echo ""
    printf "  ${RED}[D]${RST}  Delete this package    ${RED}[Q]${RST}  Back to menu\n"
    printf "  ${YLW}Select: ${RST}"
    read -rn1 action
    echo ""
    case $action in
      [Dd])
        required_by=$(pacman -Qi -- "$pkg" 2>/dev/null | awk -F': ' '/^Required By/{print $2}')
        echo ""
        if [ -n "$required_by" ] && [ "$required_by" != "None" ]; then
          printf "  ${RED}Warning: other installed packages depend on this one:${RST}\n  %s\n" "$required_by"
        fi
        printf "  ${RED}Remove %s and its unused dependencies? Type the package name to confirm: ${RST}" "$pkg"
        read -r confirm
        if [ "$confirm" != "$pkg" ]; then
          printf "  ${DIM}Cancelled -- typed name didn't match.${RST}\n"
          read -rp "  Press Enter to return..."
          continue
        fi
        ensure_sudo || { read -rp "  Press Enter to return..."; continue; }
        if sudo pacman -Rns --noconfirm -- "$pkg"; then
          printf "  ${GRN}Removed: %s${RST}\n" "$pkg"
          read -rp "  Press Enter to return to menu..."
          return
        else
          printf "  ${RED}Removal failed -- see pacman's output above.${RST}\n"
          read -rp "  Press Enter to return..."
        fi
        ;;
      [Qq]) return ;;
      *) ;;
    esac
  done
}

firewall_menu() {
  local fw_choice rule_input confirm status_line
  while true; do
    echo ""
    printf "  ${WHT}Firewall (ufw)${RST}\n\n"
    status_line=$(sudo ufw status verbose 2>/dev/null | head -1)
    printf "  ${DIM}%s${RST}\n\n" "${status_line:-Status unknown -- try Enter to authenticate.}"
    printf "  ${YLW}[1]${RST}  Enable firewall\n"
    printf "  ${YLW}[2]${RST}  Disable firewall\n"
    printf "  ${YLW}[3]${RST}  Allow a port/service\n"
    printf "  ${YLW}[4]${RST}  Deny a port/service\n"
    printf "  ${YLW}[5]${RST}  Remove a rule\n"
    printf "  ${RED}[0]${RST}  Back\n\n  Select: "
    read -r fw_choice
    case $fw_choice in
      1) ensure_sudo || continue
         # Enabling with default-deny-incoming and no SSH rule cuts off the
         # very session used to enable it if sshd is running -- keep 22/tcp
         # open automatically, same safety the GUI's Firewall page applies.
         if sudo systemctl is-active --quiet sshd 2>/dev/null; then
           sudo ufw allow 22/tcp > /dev/null 2>&1
           printf "  ${DIM}SSH access on 22/tcp kept open automatically.${RST}\n"
         fi
         sudo ufw --force enable && printf "  ${GRN}Firewall enabled.${RST}\n" || printf "  ${RED}Failed to enable firewall.${RST}\n"
         read -rp "  Press Enter to return..." ;;
      2) ensure_sudo || continue
         sudo ufw disable && printf "  ${GRN}Firewall disabled.${RST}\n" || printf "  ${RED}Failed to disable firewall.${RST}\n"
         read -rp "  Press Enter to return..." ;;
      3) printf "  ${YLW}Port/service to allow (e.g. 22, 8080/tcp, ssh): ${RST}"; read -r rule_input
         [ -z "$rule_input" ] && { printf "  ${DIM}Cancelled.${RST}\n"; continue; }
         ensure_sudo || continue
         sudo ufw allow "$rule_input" && printf "  ${GRN}Allowed: %s${RST}\n" "$rule_input" || printf "  ${RED}Failed to add rule.${RST}\n"
         read -rp "  Press Enter to return..." ;;
      4) printf "  ${YLW}Port/service to deny (e.g. 22, 8080/tcp, ssh): ${RST}"; read -r rule_input
         [ -z "$rule_input" ] && { printf "  ${DIM}Cancelled.${RST}\n"; continue; }
         ensure_sudo || continue
         sudo ufw deny "$rule_input" && printf "  ${GRN}Denied: %s${RST}\n" "$rule_input" || printf "  ${RED}Failed to add rule.${RST}\n"
         read -rp "  Press Enter to return..." ;;
      5) ensure_sudo || continue
         echo ""
         sudo ufw status numbered 2>/dev/null | grep '^\[' | while IFS= read -r l; do printf "  %s\n" "$l"; done
         echo ""
         printf "  ${YLW}Rule number to delete (blank to cancel): ${RST}"; read -r rule_input
         [ -z "$rule_input" ] && { printf "  ${DIM}Cancelled.${RST}\n"; continue; }
         [[ "$rule_input" =~ ^[0-9]+$ ]] || { printf "  ${RED}Invalid -- enter the number shown in brackets.${RST}\n"; continue; }
         sudo ufw --force delete "$rule_input" && printf "  ${GRN}Rule removed.${RST}\n" || printf "  ${RED}Failed to remove rule.${RST}\n"
         read -rp "  Press Enter to return..." ;;
      0|"") return ;;
      *) printf "  ${RED}Invalid selection.${RST}\n" ;;
    esac
  done
}

fix_permissions() {
  local mode choice target canonical file_count pm_type pm_val confirm
  echo ""
  printf "  ${WHT}Fix Permissions${RST}\n\n"
  printf "  ${YLW}[1]${RST}  Fix a folder inside your home directory\n"
  printf "  ${YLW}[2]${RST}  Make a file executable inside your home directory\n"
  printf "  ${RED}[0]${RST}  Cancel\n\n"
  printf "  Select: "; read -r mode
  case $mode in
    2)
      target=$(zenity --file-selection --title="Select file to make executable" --filename="$HOME/Downloads/" 2>/dev/null)
      [ -z "$target" ] && { printf "  ${DIM}Cancelled.${RST}\n"; return; }
      [ -f "$target" ] && [ ! -L "$target" ] || { printf "  ${RED}Select a regular file.${RST}\n"; return; }
      canonical=$(realpath -e -- "$target") || return
      if [[ "$canonical" != "$HOME/"* ]] || mountpoint -q "$canonical"; then
        printf "  ${RED}For safety, only files inside your home folder can be changed.${RST}\n"; return
      fi
      chmod +x -- "$canonical" && printf "  ${GRN}Executable permission added: $canonical${RST}\n" || printf "  ${RED}Could not change permissions.${RST}\n"
      ;;
    1)
      printf "  ${YLW}[1]${RST}  Pick a folder\n  ${YLW}[2]${RST}  Enter a path\n  ${RED}[0]${RST}  Cancel\n\n  Select: "; read -r choice
      case $choice in
        1) target=$(zenity --file-selection --directory --title="Select folder to fix" --filename="$HOME/" 2>/dev/null) ;;
        2) printf "  ${YLW}Folder path: ${RST}"; read -r target; target="${target/#\~/$HOME}" ;;
        *) printf "  ${DIM}Cancelled.${RST}\n"; return ;;
      esac
      [ -n "$target" ] && [ -d "$target" ] && [ ! -L "$target" ] || { printf "  ${RED}Select a real folder, not a symlink.${RST}\n"; return; }
      canonical=$(realpath -e -- "$target") || return
      if [[ "$canonical" != "$HOME/"* ]] || mountpoint -q "$canonical"; then
        printf "  ${RED}For safety, only non-mounted folders inside your home directory can be changed.${RST}\n"; return
      fi
      file_count=$(find -P "$canonical" -xdev -printf . 2>/dev/null | wc -c)
      printf "  ${GRN}Folder:${RST} %s  ${DIM}(%s items; current filesystem only)${RST}\n" "$canonical" "$file_count"
      printf "  ${YLW}Continue? (y/N):${RST} "; read -r confirm
      [[ "$confirm" =~ ^[Yy]$ ]] || { printf "  ${DIM}Cancelled.${RST}\n"; return; }
      printf "  ${YLW}[1]${RST} Add owner write access\n  ${YLW}[2]${RST} Take ownership and add owner read/write\n  ${YLW}[3]${RST} Apply a numeric chmod mode\n  ${RED}[0]${RST} Cancel\n\n  Select: "; read -r pm_type
      case $pm_type in
        1) ensure_sudo && sudo chown -R -- "$USER:$USER" "$canonical" && chmod -R u+w -- "$canonical" ;;
        2) ensure_sudo && sudo chown -R -- "$USER:$USER" "$canonical" && chmod -R u+rwX -- "$canonical" ;;
        3) printf "  ${YLW}Numeric chmod mode (e.g. 755): ${RST}"; read -r pm_val
           [[ "$pm_val" =~ ^[0-7]{3,4}$ ]] || { printf "  ${RED}Use a numeric mode from 000 to 7777.${RST}\n"; return; }
           ensure_sudo && sudo chown -R -- "$USER:$USER" "$canonical" && chmod -R "$pm_val" -- "$canonical" ;;
        *) printf "  ${DIM}Cancelled.${RST}\n"; return ;;
      esac
      if [ $? -eq 0 ]; then printf "  ${GRN}Permissions updated.${RST}\n"; else printf "  ${RED}Permission update failed.${RST}\n"; fi
      ;;
    *) printf "  ${DIM}Cancelled.${RST}\n" ;;
  esac
}

# Two-column menu pair: num1 label1 color1  num2 label2 color2
mpair() {
  local n1="$1" l1="$2" c1="$3" n2="${4:-}" l2="${5:-}" c2="${6:-}"
  local left_vis="[${n1}]  ${l1}"
  local col_width=$(( IW / 2 ))
  local pad=$(( col_width - ${#left_vis} ))
  [ "$pad" -lt 2 ] && pad=2
  local content="${c1}[${n1}]${RST}  ${l1}$(printf '%*s' "$pad" '')"
  [[ -n "$n2" ]] && content+="${c2}[${n2}]${RST}  ${l2}"
  crow "  ${content}"
}

msec() { crow "  ${DIM}── $1${RST}"; }

draw_menu() {
  clear
  borders
  gather_stats
  LINE_COUNT=0

  # ── Header ──────────────────────────────────────────────
  border_line "$TOP"
  crow "  ${WHT}REYOS SYSTEM TOOLS${RST}   ${DIM}${USER}${RST}"
  border_line "$MID"
  print_stats

  # ── PERFORMANCE ─────────────────────────────────────────
  msec "SYSTEM CARE"
  mpair " 1" "Manage processes"     "$GRN"  " 2" "Balanced defaults"   "$YLW"
  mpair " 3" "Resource usage"       "$GRN"  " 4" "CPU power mode"      "$GRN"
  mpair " 5" "Memory behavior"      "$GRN"  " 6" "Reclaim memory"      "$GRN"
  mpair " 7" "Swap control"         "$GRN"  " R" "Restart machine"     "$RED"

  # ── SYSTEM ──────────────────────────────────────────────
  msec "SYSTEM"
  mpair " 8" "System updates"       "$CYN"  " 9" "Flatpak update"      "$CYN"
  mpair "10" "Empty trash"          "$CYN"  "11" "Fix permissions"     "$CYN"

  # ── NETWORK & STORAGE ───────────────────────────────────
  msec "NETWORK & STORAGE"
  mpair "12" "Network info"         "$CYN"  "13" "Send file/folder to network"  "$CYN"
  crow  "  ${CYN}[14]${RST}  Disk space"

  # ── SECURITY ─────────────────────────────────────────────
  msec "SECURITY"
  crow  "  ${CYN}[15]${RST}  Package inspector — view info, delete"
  crow  "  ${CYN}[16]${RST}  Firewall — enable/disable, allow/deny, remove rules"

  border_line "$MID"
  crow "  ${RED}[ 0]${RST}  Exit"
  border_line "$MID"
  # Capture the row the "Select option:" line lands on before printing it --
  # LINE_COUNT is a running tally of every line drawn so far (incremented by
  # row()/crow()/border_line()), so this stays correct no matter how many
  # rows the menu above it grows or shrinks by, instead of a hardcoded
  # row number silently going stale every time a menu item is added.
  PROMPT_ROW=$LINE_COUNT
  crow "  ${YLW}Select option:${RST} "
  printf '%s\n' "$BOT"
  # Keep typed input on the Select option line without resizing the
  # terminal. If the whole menu is taller than the terminal window, it has
  # already auto-scrolled by the time we get here -- the "Select option:"
  # line we just printed is guaranteed to be sitting on the terminal's own
  # last visible row (it was the last thing printed), so target that row
  # directly instead of the original absolute PROMPT_ROW, which would now
  # point above the visible area and put the cursor in the wrong place (or,
  # with the old skip-entirely guard, leave it wherever printf happened to
  # land -- one row below the box).
  read_term_size
  if [ -n "$TERM_ROWS" ] && [ "$TERM_ROWS" -gt 0 ] 2>/dev/null; then
    # Once total output (PROMPT_ROW + the prompt's own line + $BOT after
    # it = PROMPT_ROW+2 lines) exceeds the terminal's height, the terminal
    # has auto-scrolled and $BOT -- not the prompt line -- sits on the
    # actual bottom row; the prompt is exactly one row above that. Below
    # that threshold nothing has scrolled and the absolute PROMPT_ROW is
    # still correct as-is. min() unifies both cases in one formula instead
    # of a hand-tuned threshold that has to be re-derived by hand (and has
    # twice landed off-by-one) every time the menu's line count changes.
    LAST_ROW=$((TERM_ROWS - 2))
    [ "$LAST_ROW" -lt 0 ] && LAST_ROW=0
    CUP_ROW=$PROMPT_ROW
    [ "$LAST_ROW" -lt "$CUP_ROW" ] && CUP_ROW=$LAST_ROW
    tput cup "$CUP_ROW" "$PROMPT_COL"
  fi
}

cleanup() {
  tput cnorm
  echo ''
  [ -n "$SUDO_KEEPALIVE_PID" ] && kill "$SUDO_KEEPALIVE_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

while true; do
  draw_menu

  read -r choice

  case $choice in
    1) htop ;;
    2) echo ""
       ensure_sudo || { read -rp "  Press Enter to return to menu..."; continue; }
       printf "  ${YLW}Applying balanced ReyOS defaults...${RST}\n"
       if compgen -G "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor" > /dev/null; then
         BALANCED_GOV="schedutil"
         grep -qw "$BALANCED_GOV" /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors 2>/dev/null || BALANCED_GOV="ondemand"
         for cpu_path in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
           echo "$BALANCED_GOV" | sudo tee "$cpu_path" > /dev/null
         done
         GOVERNOR="$BALANCED_GOV"
       else
         printf "  ${DIM}No CPU power controls available on this system (common in VMs).${RST}\n"
       fi
       sudo sysctl -w vm.swappiness=60 > /dev/null
       persist_swappiness 60
       SWAPPINESS=60
       printf "  ${GRN}Balanced defaults applied.${RST} Normal memory behavior now persists across reboots.\n"
       read -rp "  Press Enter to return to menu..." ;;
    3) show_cpu_hogs ;;
    4) echo ""
       printf "  ${YLW}Select CPU power mode — [1] balanced (schedutil)  [2] responsive (ondemand)  [3] saver:${RST} "
       read -r gov_choice
       case $gov_choice in
         1) GOV="schedutil" ;;
         2) GOV="ondemand" ;;
         3) GOV="powersave" ;;
         *) printf "  ${RED}Invalid.${RST}\n"; sleep 1; continue ;;
       esac
       ensure_sudo || { read -rp "  Press Enter to return to menu..."; continue; }
       if compgen -G "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor" > /dev/null; then
         for cpu_path in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
           echo "$GOV" | sudo tee "$cpu_path" > /dev/null
         done
         printf "  ${GRN}Governor set to: ${GOV}${RST}\n"
       else
         printf "  ${DIM}No cpufreq scaling available on this system (common in VMs) — skipped.${RST}\n"
       fi
       read -rp "  Press Enter to return to menu..." ;;
    5) echo ""
       printf "  ${YLW}Current swappiness: ${SWAPPINESS}. New value (0–100):${RST} "
       read -r new_swap
       if [[ "$new_swap" =~ ^[0-9]+$ ]] && [ "$new_swap" -ge 0 ] && [ "$new_swap" -le 100 ]; then
         ensure_sudo || { read -rp "  Press Enter to return to menu..."; continue; }
         sudo sysctl -w vm.swappiness="$new_swap" > /dev/null
         persist_swappiness "$new_swap"
         printf "  ${GRN}Swappiness set to: ${new_swap} (persists across reboots)${RST}\n"
       else
         printf "  ${RED}Invalid. Must be 0–100.${RST}\n"
       fi
       read -rp "  Press Enter to return to menu..." ;;
    6) echo ""
       ensure_sudo || { read -rp "  Press Enter to return to menu..."; continue; }
       printf "  ${YLW}Dropping caches...${RST}\n"
       sync
       sudo bash -c 'echo 3 > /proc/sys/vm/drop_caches'
       read -r _ _ MEM_FREE _ < <(free -m | grep '^Mem:')
       printf "  ${GRN}Done. Free RAM: ${MEM_FREE} MB${RST}\n"
       read -rp "  Press Enter to return to menu..." ;;
    7) echo ""
       ensure_sudo || { read -rp "  Press Enter to return to menu..."; continue; }
       SWAP_ON=$(swapon --show 2>/dev/null | tail -n +2 | grep -c ".")
       if [ "$SWAP_ON" -gt 0 ]; then
         printf "  ${YLW}Disabling swap...${RST}\n"
         # swapoff -a only affects the running session -- systemd regenerates
         # the swap unit from fstab on every boot, so mask it (an
         # /etc/systemd/system mask always wins over that generated unit)
         # instead of editing fstab directly.
         mapfile -t SWAP_UNITS < <(swapon --show=NAME --noheadings 2>/dev/null | \
           while read -r dev; do systemd-escape --path --suffix=swap "$dev"; done)
         sudo swapoff -a && printf "  ${GRN}Swap disabled${RST} (stays off after reboot)\n"
         for unit in "${SWAP_UNITS[@]}"; do
           [ -n "$unit" ] && sudo systemctl mask "$unit" > /dev/null 2>&1
         done
       else
         printf "  ${YLW}Enabling swap...${RST}\n"
         mapfile -t MASKED_UNITS < <(systemctl list-unit-files --type=swap --state=masked \
           --no-legend --plain 2>/dev/null | awk '{print $1}')
         for unit in "${MASKED_UNITS[@]}"; do
           [ -n "$unit" ] && sudo systemctl unmask "$unit" > /dev/null 2>&1
         done
         sudo swapon -a  && printf "  ${GRN}Swap enabled.${RST}\n"
       fi
       read -rp "  Press Enter to return to menu..." ;;
    8) system_updates ;;
    9) echo ""
       printf "  ${CYN}Running flatpak update...${RST}\n\n"
       flatpak update -y
       read -rp "  Press Enter to return to menu..." ;;
    10) echo ""
       TRASH_SIZE=$(du -sh ~/.local/share/Trash/files/ 2>/dev/null | cut -f1)
       printf "  ${DIM}Trash size: ${TRASH_SIZE:-0}${RST}\n"
       printf "  ${YLW}Empty trash? (y/N):${RST} "
       read -r confirm
       if [[ "$confirm" =~ ^[Yy]$ ]]; then
         rm -rf ~/.local/share/Trash/files/* ~/.local/share/Trash/info/* 2>/dev/null
         printf "  ${GRN}Trash emptied.${RST}\n"
       else
         printf "  ${DIM}Cancelled.${RST}\n"
       fi
       read -rp "  Press Enter to return to menu..." ;;
    11) fix_permissions
       read -rp "  Press Enter to return to menu..." ;;
    12) show_network ;;
    13) copy_network ;;
    14) show_disk ;;
    15) package_inspector ;;
    16) firewall_menu ;;
    r|R) echo ""
       printf "  ${RED}Restart machine? (y/N):${RST} "
       read -r confirm
       if [[ "$confirm" =~ ^[Yy]$ ]]; then
         ensure_sudo || continue
         printf "  ${YLW}Restarting...${RST}\n"
         sudo reboot
       else
         printf "  ${DIM}Cancelled.${RST}\n"
         sleep 1
       fi ;;
    0) printf "\n  ${GRN}Goodbye!${RST}\n\n"; exit 0 ;;
    "") : ;;
    *) printf "  ${RED}Invalid option.${RST}\n"; sleep 1 ;;
  esac
done
