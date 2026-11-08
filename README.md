# libfprint-betterlife

> **Unofficial.** Not affiliated with or endorsed by Betterlife / BLESTECH.

Linux support (libfprint driver + Python RE tooling) for the **Betterlife USB fingerprint module**,
USB ID `347d:0302` ("btlfp Betterlife Fingerprint"). The vendor only ships a Windows driver; the
protocol was reverse-engineered from it (Microsoft Update Catalog, `BLESTECH - Biometric -
14.36.53.907`) and verified on hardware.

The module is **match-on-chip**: an N32G4FR MCU does capture, enrollment, template storage
(10 templates) and matching. The host only sends commands, over a CRC-framed protocol that is
SM4-encrypted after an SM2 key exchange.

## Status

| Feature | State |
|---|---|
| Framing, CRC, SM2 key exchange, SM4 encryption | ✅ verified |
| Enroll (7 touches), identify, verify | ✅ Python tool and libfprint driver |
| Foreign/stale templates can't authenticate (template id + tag check) | ✅ verified |
| Delete a print from the module (per-print identity) | ✅ verified |
| Wipe all templates | ❌ deliberately not implemented (see Safety) |
| Cancel (module-side cancel command) | ✅ verified (identify and enroll) |
| fprintd enroll / verify / delete | ✅ (verify 3/3) |
| libfprint umockdev test (recorded on hardware, replays in CI) | ✅ `tests/umockdev/`, valgrind clean |
| PAM: KDE lock screen, sudo | ✅ (`scripts/pam-enable.sh`, also polkit + LightDM; undo: `pam-revert.sh`) |

## Install

The patch applies to libfprint v1.94.100. On Arch, the combined package with this driver and the
Synochip one is built from the sibling repo `../libfprint-btl-syno` (it fetches
`packaging/0001-add-betterlife-driver.patch` from here; run its `./update.sh` after changing the driver).

## Safety

This project follows a strict **allowlist**: only the command shapes the Windows driver itself
sends during init/enroll/identify/delete can be transmitted. Removal is only possible with a
print's own ASCII identity; the all-zero identity (remove **all**) is refused. Firmware update, the
switch into the bootloader, JTAG control and an MCU restore can't be sent at all. A sister project
lost a reader to an unvetted "clear" command.

## Layout

| Path | What |
|---|---|
| `driver/` | libfprint driver `betterlife.c/.h` (copy of what the patch adds) |
| `packaging/0001-add-betterlife-driver.patch` | patch against libfprint v1.94.100 |
| `btl.py`, `btlcrypto.py`, `safety.py` | Python userspace driver, pure-Python SM2/SM3/SM4, allowlist |
| `tests/` | offline tests (crypto vectors, frame codec, Python and C allowlists) |
| `experiments/` | interactive hardware tests |
| `docs/PROTOCOL.md` | the protocol |
| `docs/RE-NOTES.md` | how it was found, function map, module state |
| `scripts/pam-enable.sh`, `pam-revert.sh` | add/remove `pam_fprintd` for sudo, polkit, LightDM (backups in /root) |
| `70-libfprint-betterlife.rules` | udev rule for the Python tools |

## Quick start (Python tool)

```bash
sudo cp 70-libfprint-betterlife.rules /etc/udev/rules.d/ && sudo udevadm control --reload \
  && sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=347d
python3 -m venv .venv && .venv/bin/pip install pyusb
.venv/bin/python btl.py -v        # read-only: firmware, scheme, key exchange, UID, sensor, count
.venv/bin/python -m unittest discover -s tests
```

## License

LGPL-2.1-or-later, like libfprint.
