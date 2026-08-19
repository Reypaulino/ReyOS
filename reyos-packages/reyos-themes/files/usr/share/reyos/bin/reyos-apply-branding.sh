#!/bin/bash
# ReyOS desktop setup — triggered by reyos-welcome on exit (not an
# independent autostart entry — that used to run concurrently with
# Welcome and race it for the same Plasma config file, the root cause
# of the panel/shortcuts clobbering bugs). Idempotent via a marker file
# since Welcome can trigger this on every exit, not just the first one.
MARKER="$HOME/.config/reyos-branding-applied"
# Existing marker files must not block a corrected ReyOS visual identity.
BRANDING_VERSION="midnight-copper-3"
PANEL_EDIT_MARKER="$HOME/.config/reyos-panel-editing-requested"
[ "$(cat "$MARKER" 2>/dev/null)" = "$BRANDING_VERSION" ] && exit 0

CONFIG_FILE="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
mkdir -p "$HOME/.config"

apply_visual_identity() {
  plasma-apply-colorscheme ReyOS >/dev/null 2>&1 || true
  kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.reyos.desktop
}

apply_wallpaper() {
  qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
  var d = desktops();
  for (i = 0; i < d.length; i++) {
      d[i].wallpaperPlugin = "org.kde.image";
      d[i].currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
      d[i].writeConfig("Image", "file:///usr/share/backgrounds/reyos-wallpaper.jpg");
  }
  ' >/dev/null 2>&1
  # Lock screen wallpaper is a separate config from the desktop wallpaper
  # above (kscreenlockerrc, not plasma-org.kde.plasma.desktop-appletsrc) and
  # was never set anywhere — confirmed via kreadconfig6 returning empty on a
  # live install, so the greeter fell back to KDE's stock default background
  # instead of ReyOS's. No running-session API for this one; it's a plain
  # config write.
  kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General --key Image "file:///usr/share/backgrounds/reyos-wallpaper.jpg"
}

apply_virtual_desktops() {
  kwriteconfig6 --file kwinrc --group Desktops --key Number 5
  kwriteconfig6 --file kwinrc --group Desktops --key Rows 1
  # `KWin reconfigure` does NOT re-read Desktops/Number for an already-running
  # session -- confirmed directly: count stayed at 1 even right after a manual
  # reconfigure call. VirtualDesktopManager.count is read-only over D-Bus;
  # Number is only consulted by KWin at its own startup. The only way to grow
  # a *live* session is to explicitly create each missing desktop.
  local current
  current=$(qdbus6 org.kde.KWin /VirtualDesktopManager org.freedesktop.DBus.Properties.Get org.kde.KWin.VirtualDesktopManager count 2>/dev/null)
  current=${current:-1}
  while [ "$current" -lt 5 ]; do
    qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.createDesktop "$current" "Desktop $((current + 1))" >/dev/null 2>&1
    current=$((current + 1))
  done
}

apply_shortcuts() {
  # Trim shortcuts that overlap with Overview (Meta+W) or are rarely used,
  # to declutter the default keybinding set. Keeps the default field intact
  # (second value) so "Reset to Default" in the Shortcuts KCM still works —
  # only the active binding (first value) is cleared.
  local F=kglobalshortcutsrc
  kwriteconfig6 --file "$F" --group kwin --key "Activate Window Demanding Attention" "none,Meta+Ctrl+A,Activate Window Demanding Attention"
  kwriteconfig6 --file "$F" --group kwin --key "Edit Tiles" "none,Meta+T,Toggle Tiles Editor"
  kwriteconfig6 --file "$F" --group kwin --key "Expose" "none,Ctrl+F9\tMeta+F9,Toggle Present Windows (Current desktop)"
  kwriteconfig6 --file "$F" --group kwin --key "ExposeAll" "none,Launch (C)\tCtrl+F10\tMeta+F10,Toggle Present Windows (All desktops)"
  kwriteconfig6 --file "$F" --group kwin --key "ExposeClass" "none,Ctrl+F7\tMeta+F7,Toggle Present Windows (Window class)"
  kwriteconfig6 --file "$F" --group kwin --key "Grid View" "none,Meta+G,Toggle Grid View"
  kwriteconfig6 --file "$F" --group kwin --key "Kill Window" "none,Meta+Ctrl+Esc,Kill Window"
  kwriteconfig6 --file "$F" --group kwin --key "MoveMouseToCenter" "none,Meta+F6,Move Mouse to Center"
  kwriteconfig6 --file "$F" --group kwin --key "MoveMouseToFocus" "none,Meta+F5,Move Mouse to Focus"
  kwriteconfig6 --file "$F" --group kwin --key "view_actual_size" "none,Meta+0,Zoom to Actual Size"
  kwriteconfig6 --file "$F" --group kwin --key "view_zoom_in" "none,Meta++\tMeta+=,Zoom In"
  kwriteconfig6 --file "$F" --group kwin --key "view_zoom_out" "none,Meta+-,Zoom Out"
}

SHORTCUT_KEYS=(
  "Activate Window Demanding Attention" "Edit Tiles" "Expose" "ExposeAll"
  "ExposeClass" "Grid View" "Kill Window" "MoveMouseToCenter"
  "MoveMouseToFocus" "view_actual_size" "view_zoom_in" "view_zoom_out"
)

shortcuts_still_bound() {
  # kglobalaccel loads its bindings into memory early in session bootstrap,
  # before this script runs — the same class of race as the panel layout.
  # `KWin reconfigure` can write kglobalaccel's still-bound in-memory state
  # back over our on-disk changes for some keys (confirmed: Expose stuck,
  # but Grid View/Kill Window/MoveMouseToCenter silently reverted). Verify
  # what's actually on disk after reconfigure rather than trusting the write.
  for k in "${SHORTCUT_KEYS[@]}"; do
    case "$(kreadconfig6 --file kglobalshortcutsrc --group kwin --key "$k")" in
      none,*) ;;
      *) return 0 ;;
    esac
  done
  return 1
}

apply_panel_layout() {
  # Use Plasma's stable scripting API; saved containment IDs vary per user and
  # caused fresh installs to restore the legacy panel template.
  qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript 'var e=panels(); for(var p=e.length-1;p>=0;--p){e[p].remove();} var t=new Panel; t.location="top"; t.height=30; t.floating=false; t.immutability=3; t.addWidget("org.reyos.workspacedots"); t.addWidget("org.kde.plasma.panelspacer"); var c=t.addWidget("org.kde.plasma.digitalclock"); c.currentConfigGroup=["Appearance"]; c.writeConfig("showDate",true); c.writeConfig("dateDisplayFormat","Custom"); c.writeConfig("customDateFormat","ddd, MMM d"); t.addWidget("org.kde.plasma.panelspacer"); t.addWidget("org.kde.plasma.systemtray"); t.addWidget("org.kde.plasma.lock_logout"); var b=new Panel; b.location="bottom"; b.height=40; b.floating=false; b.immutability=3; var l=b.addWidget("org.kde.plasma.kickoff"); l.currentConfigGroup=["General"]; l.writeConfig("icon","reyos-launcher"); b.addWidget("org.kde.plasma.icontasks");' >/dev/null 2>&1
}

unlock_panel_layout() {
  qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript 'var e=panels(); for (var p=0; p<e.length; p++) { e[p].immutability=1; }' >/dev/null 2>&1
}

# Wait for Plasma's own first-run bootstrap to write a default panel before
# we touch the file at all.
for _ in $(seq 1 60); do
  [ -f "$CONFIG_FILE" ] && grep -q 'plugin=org\.kde\.panel' "$CONFIG_FILE" 2>/dev/null && break
  sleep 1
done
touch "$CONFIG_FILE"

apply_wallpaper
apply_visual_identity
apply_virtual_desktops


# Confirmed on a fresh boot: retrying this exact sequence didn't help — only
# Expose stayed unbound, all the rest kept reverting on every single attempt,
# not just intermittently. That points to `KWin reconfigure` itself being
# what clobbers the write (KWin re-asserting kglobalaccel's own in-memory
# defaults back to disk), not a one-off timing race — retrying a
# deterministic clobber just reproduces it every time. Dropping the
# reconfigure call entirely: the on-disk file is what matters for every
# future login (this user's next session, and every other user), so we
# don't need this session to reflect it live. One retry kept as a cheap
# safety net in case the write itself intermittently loses a race with
# something else touching the file, without the deterministic clobber step.
for attempt in $(seq 1 2); do
  apply_shortcuts
  sleep 1
  shortcuts_still_bound || break
done

# Timing alone (fixed sleep, or even a file-stability check) isn't reliable
# here — Plasma writes this config in a burst of several passes during its
# own bootstrap, spaced unpredictably under load, and any later pass in
# that burst can silently clobber our appended containments no matter how
# long we wait first. Verify-and-retry instead of guessing timing: apply
# the layout, wait for it to settle, then check it's actually still there;
# if Plasma clobbered it, reapply. Bounded retries so a genuinely broken
# environment still exits instead of looping forever.
#
# Checking a marker widget's presence alone isn't enough either — confirmed
# a run where our content was present AND a stray orphan default panel also
# existed alongside it (3 panel containments instead of 2), left over from
# Plasma re-bootstrapping a default panel during one of the retry cycles'
# plasmashell restarts. Require the exact count too, not just presence.
# The ReyOS Workspace Dots widget is the marker for the modern default layout.
for attempt in $(seq 1 5); do
  apply_panel_layout
  sleep 6
  panel_count=$(awk 'BEGIN{RS="";FS="\n"} $1 ~ /^\[Containments\]\[[0-9]+\]$/ && /plugin=org\.kde\.panel/ {n++} END{print n+0}' "$CONFIG_FILE")
  if grep -q 'plugin=org.reyos.workspacedots' "$CONFIG_FILE" 2>/dev/null && [ "$panel_count" -eq 2 ]; then
    break
  fi
done

[ -f "$PANEL_EDIT_MARKER" ] && unlock_panel_layout
printf '%s\n' "$BRANDING_VERSION" > "$MARKER"
