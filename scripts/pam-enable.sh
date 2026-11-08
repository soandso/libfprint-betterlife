#!/bin/bash
# Add fingerprint auth (pam_fprintd, password still works as fallback) to sudo, polkit and LightDM.
# Run as root:  sudo bash scripts/pam-enable.sh      Undo:  sudo bash scripts/pam-revert.sh
# Keep a root shell open in another terminal while testing.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
LINE='auth       sufficient   pam_fprintd.so max-tries=3 timeout=10'
BK=/root/pam-backup-fprintd-$(date +%F-%H%M%S)
mkdir -p "$BK"

add() {   # $1 = file: insert $LINE before the first auth line, once
  local f=$1
  if grep -q pam_fprintd "$f"; then echo "skip $f (already has pam_fprintd)"; return; fi
  cp -a "$f" "$BK/"
  sed -i "0,/^auth/s//$LINE\n&/" "$f"
  grep -q pam_fprintd "$f" || { echo "FAILED on $f, restoring"; cp -a "$BK/$(basename "$f")" "$f"; exit 1; }
  echo "added to $f"
}

# polkit: Arch ships it in /usr/lib/pam.d; an /etc copy takes precedence
if [ ! -e /etc/pam.d/polkit-1 ]; then
  cp /usr/lib/pam.d/polkit-1 /etc/pam.d/polkit-1
  touch "$BK/polkit-1.created"
fi

add /etc/pam.d/sudo
add /etc/pam.d/polkit-1
add /etc/pam.d/lightdm
echo "backups in $BK"
echo "test: sudo -k; sudo true   (touch the reader, or wait 10 s for the password prompt)"
