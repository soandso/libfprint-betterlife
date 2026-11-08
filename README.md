# libfprint-betterlife

> **Unofficial.** Not affiliated with or endorsed by Betterlife / BLESTECH.

Linux support (libfprint driver + Python RE tooling) for the **Betterlife USB fingerprint module**,
USB ID `347d:0302` ("btlfp Betterlife Fingerprint"). The vendor only ships a Windows driver; the
protocol was reverse-engineered from it (Microsoft Update Catalog, `BLESTECH - Biometric -
14.36.53.907`) and verified on hardware.

The module is **match-on-chip**: an N32G4FR MCU does capture, enrollment, template storage
(10 templates) and matching. The host only sends commands, over a CRC-framed protocol that is
SM4-encrypted after an SM2 key exchange.

**This is a fork, not upstream libfprint.** The driver is maintained as a patch on top of libfprint
releases (currently v1.94.100); it is not proposed upstream for now. See
[`docs/MAINTAINING.md`](docs/MAINTAINING.md).

## How this was made

**AI disclosure:** the reverse engineering, the protocol documentation and all code in this repo
were produced with **Claude Code** (Anthropic's AI coding agent). A human directed the work, owned
the hardware, approved every step that writes to the module, and did all the hardware testing, but
has **not reviewed the code line by line**. Commits carry a `Co-Authored-By: Claude` trailer.

Judge it by the evidence rather than the authorship. [`docs/VALIDATION.md`](docs/VALIDATION.md)
lists every claim with how it was verified on the real device, the bugs found along the way, and
what is **not** verified. In short:

- every feature below was observed working on the hardware, through fprintd and PAM;
- a umockdev test recorded on the device replays without hardware, clean under valgrind;
- libfprint's full test suite passes with the driver (131/131), and the code passes libfprint's
  style check;
- the dangerous module commands (firmware update, bootloader switch, remove-all, …) can't be sent,
  enforced by tests in both the Python tool and the C driver;
- tested on **one** unit and firmware (01.00.00.00) only.

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
| libfprint umockdev test (recorded on hardware, replays without it) | ✅ `tests/umockdev/`, valgrind clean |
| PAM: KDE lock screen, sudo | ✅ (`scripts/pam-enable.sh`, also polkit + LightDM; undo: `pam-revert.sh`) |

Evidence for each line: [`docs/VALIDATION.md`](docs/VALIDATION.md).

## Install

Releases: <https://github.com/soandso/libfprint-betterlife/releases> (the patch is attached).
An AUR-ready `PKGBUILD` that uses the release is in [`packaging/aur/`](packaging/aur/).

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
| `docs/RE-NOTES.md` | how it was found, function map, session log, module state |
| `docs/VALIDATION.md` | provenance (AI disclosure), evidence, failures, what isn't verified |
| `docs/MAINTAINING.md` | keeping the fork on top of new libfprint releases |
| `tests/umockdev/` | copy of the recorded libfprint test (`custom.py`, recording, device dump) |
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
