#!/bin/bash
# Apply ReyOS boot branding and regenerate GRUB safely.
set -euo pipefail

preset=/etc/mkinitcpio.d/linux.preset
old_uki=/boot/EFI/Linux/arch-linux.efi
new_uki=/boot/EFI/Linux/reyos-linux.efi

# Older installations may inherit Arch's UKI filename and splash bitmap.
if [ -f "$preset" ] && grep -q "arch-linux\|splash-arch\.bmp" "$preset"; then
  sed -i \
    -e "s|arch-linux|reyos-linux|g" \
    -e "s|/usr/share/systemd/bootctl/splash-arch\.bmp|/usr/share/reyos/boot/splash-reyos.bmp|g" \
    "$preset"
  if command -v mkinitcpio >/dev/null 2>&1; then
    mkinitcpio -P
  fi
  # Remove only the exact legacy file after the ReyOS UKI is available.
  if [ -f "$new_uki" ]; then
    rm -f "$old_uki"
  fi
fi

if [ -f /etc/default/grub ]; then
  if grep -q "^GRUB_THEME=" /etc/default/grub; then
    sed -i "s|^GRUB_THEME=.*|GRUB_THEME=\"/boot/grub/themes/reyos/theme.txt\"|" /etc/default/grub
  else
    echo 'GRUB_THEME="/boot/grub/themes/reyos/theme.txt"' >> /etc/default/grub
  fi
  if grep -q "^GRUB_TIMEOUT_STYLE=" /etc/default/grub; then
    sed -i "s|^GRUB_TIMEOUT_STYLE=.*|GRUB_TIMEOUT_STYLE=menu|" /etc/default/grub
  else
    echo "GRUB_TIMEOUT_STYLE=menu" >> /etc/default/grub
  fi
  command -v grub-mkconfig >/dev/null 2>&1 && grub-mkconfig -o /boot/grub/grub.cfg
fi
