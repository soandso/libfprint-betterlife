#!/bin/bash
# Undo scripts/pam-enable.sh: restore the newest backup of each file (removes a created polkit-1).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
BK=$(ls -d /root/pam-backup-fprintd-* 2>/dev/null | sort | tail -1)
[ -n "$BK" ] || { echo "no backup found"; exit 1; }
for f in sudo lightdm; do [ -e "$BK/$f" ] && cp -a "$BK/$f" /etc/pam.d/$f && echo "restored /etc/pam.d/$f"; done
if [ -e "$BK/polkit-1.created" ]; then rm -f /etc/pam.d/polkit-1 && echo "removed /etc/pam.d/polkit-1"
elif [ -e "$BK/polkit-1" ]; then cp -a "$BK/polkit-1" /etc/pam.d/polkit-1 && echo "restored /etc/pam.d/polkit-1"; fi
