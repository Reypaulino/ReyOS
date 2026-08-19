#!/usr/bin/env bash
set -e -u

useradd -m -G wheel,storage,power,audio,video,network -s /bin/bash liveuser
echo 'liveuser:liveuser' | chpasswd
echo 'root:reyos' | chpasswd

echo 'liveuser ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/g_wheel
chmod 0440 /etc/sudoers.d/g_wheel

systemctl enable NetworkManager.service
systemctl enable sddm.service

mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/autologin.conf << 'EOF'
[Autologin]
User=liveuser
Session=plasma
EOF

chown -R liveuser:liveuser /home/liveuser

# ReyOS branding: override the default wallpaper baked into every
# Look-and-Feel package so a brand-new user's first Plasma session
# picks it up automatically (runs after packages are installed, so
# this survives — an airootfs overlay file at the same path would
# get clobbered by pacstrap installing the owning package).
# org.reyos.desktop is the actually-active Look-and-Feel package (our own
# custom Global Theme, confirmed via kreadconfig6 kdeglobals KDE
# LookAndFeelPackage on a live boot) -- its own defaults file ships with
# Theme=breeze-dark hardcoded from when it was originally built, before this
# icon theme existed. The stock breeze/breezedark/breezetwilight entries are
# kept too as defensive coverage in case a user switches away from
# org.reyos.desktop later.
for lnf in org.kde.breeze.desktop org.kde.breezedark.desktop org.kde.breezetwilight.desktop org.reyos.desktop; do
  defaults="/usr/share/plasma/look-and-feel/${lnf}/contents/defaults"
  if [ -f "$defaults" ]; then
    sed -i 's|^Image=.*|Image=/usr/share/backgrounds/reyos-wallpaper.jpg|' "$defaults"
    # ReyOS icon theme (inherits breeze-dark, overrides select icons like
    # preferences-system with a ReyOS-blue gear) — same reasoning as the
    # wallpaper line above, must patch post-install. Scoped to the
    # [kdeglobals][Icons] section specifically — a blanket "s|^Theme=|"
    # would also hit the unrelated [ksplashrc][KSplash] Theme= line
    # further down this same file and break the splash screen.
    sed -i '/^\[kdeglobals\]\[Icons\]$/,/^$/{s|^Theme=.*|Theme=ReyOS|}' "$defaults"
  fi
done

# ReyOS branding: auto-run neofetch (REY ASCII logo + system info) on every
# new terminal. Appended here rather than shipped as a full /etc/skel/.bashrc
# in reyos-terminal's own package — the bash package already owns that path,
# so shipping our own would be a pacman file conflict at install time.
echo 'neofetch' >> /etc/skel/.bashrc

# mkinitcpio's own stock /etc/mkinitcpio.conf ships a Unicode "≥" (U+2265) in
# a comment ("Linux ≥ 5.9") -- harmless on its own, but Calamares' real exec
# phase (added 2026-08-09) reads this exact file from the target during the
# initcpiocfg job using plain ASCII decoding, and hard-crashes the whole
# install with UnicodeDecodeError the moment it hits that byte. Confirmed via
# a real end-to-end install test on ReyOS-Test: install failed at job 19/34
# with this exact error. Not a ReyOS-introduced bug (stock Arch's file, stock
# Calamares module), but ReyOS controls what's baked into the live squashfs,
# so scrub it here at ISO build time rather than patch Calamares itself.
sed -i 's/≥/>=/' /etc/mkinitcpio.conf
