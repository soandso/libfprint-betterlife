# Maintaining the fork

This driver lives **out of tree**: one patch against a libfprint release,
[`packaging/0001-add-betterlife-driver.patch`](../packaging/0001-add-betterlife-driver.patch), that adds
`libfprint/drivers/betterlife/`, its meson entries, the hwdb line and the umockdev test. On Arch
it ships together with the Synochip driver in the sibling repo `../libfprint-btl-syno`.

It is not proposed upstream for now. For comparison, the ChipSailing CS9711 driver also lives in
community forks rebased onto each libfprint release, because the matcher it depends on (sigfm,
libfprint MRs !418 and !530) has been under review since 2022. This driver needs no new matcher, so
an upstream proposal would be simpler; see [`VALIDATION.md`](VALIDATION.md) for the evidence and the
AI disclosure that would go with one.

## Current state

| | |
|---|---|
| Base | libfprint **v1.94.100** (latest release as of 2026-11-09) |
| Patch on upstream `master` | applies cleanly, alone and on top of the Synochip patch (checked 2026-11-09, `6f9479c`) |
| Package | `libfprint-btl-syno` (in `../libfprint-btl-syno`) |

## Rebasing onto a new libfprint release

`libfprint/` (gitignored) is a working clone with an `upstream` remote
(`https://gitlab.freedesktop.org/libfprint/libfprint.git`).

1. **Check nobody else claimed the device.** In the new release, `grep -i 347d data/autosuspend.hwdb`.
   If upstream gained a driver for `347d:0302`, stop and compare before carrying ours.
2. **Move the patch.**
   ```bash
   cd libfprint
   git fetch upstream --tags
   git stash -u                      # or commit: the driver files are uncommitted on top of the tag
   git checkout vX.Y.Z
   git apply -3 ../packaging/0001-add-betterlife-driver.patch
   ```
   Conflicts are usually only in the lists other drivers also touch: `meson.build` (driver list),
   `libfprint/meson.build` (driver sources), `tests/meson.build` (driver tests). The hwdb line must
   stay where the generator puts it (driver name order).
3. **Build and test.**
   ```bash
   meson setup --wipe build -Ddrivers=betterlife -Ddoc=false -Dgtk-examples=false
   meson compile -C build && meson test -C build betterlife
   meson test -C build --setup=valgrind betterlife
   uncrustify -q -c scripts/uncrustify.cfg --check libfprint/drivers/betterlife/betterlife.[ch]
   ```
   Then once with all drivers, and compare the hwdb with `build/libfprint/fprint-list-udev-hwdb`.
4. **If the replay test fails** because the test framework or the driver's command sequence changed,
   re-record it (root; 9 touches with a finger that is *not* enrolled on the module):
   ```bash
   sudo modprobe usbmon
   sudo build/tests/create-driver-test.py --test custom betterlife
   ```
   Take ownership of the root-owned `tests/betterlife/{custom.pcapng,device}` afterwards. If the
   script crashes midway, the test print stays on the module; remove it by its deterministic
   identity (see `RE-NOTES.md` step 26).
5. **Export.**
   ```bash
   git add -N tests/betterlife libfprint/drivers/betterlife
   git diff --binary HEAD -- meson.build libfprint/meson.build data/autosuspend.hwdb \
       libfprint/drivers/betterlife tests/meson.build tests/betterlife \
       > ../packaging/0001-add-betterlife-driver.patch
   cp libfprint/drivers/betterlife/betterlife.[ch] ../driver/
   cp tests/betterlife/{custom.py,custom.pcapng,device} ../tests/umockdev/
   cd .. && .venv/bin/python -m unittest discover -s tests
   ```
6. **Package.** The Synochip patch must be rebased the same way in its own repo. Then in
   `../libfprint-btl-syno`: set `pkgver` to the new release, `pkgrel=1`, run `./update.sh`
   (re-pins checksums, builds, runs the full test suite), install, restart fprintd, and do one
   `fprintd-verify`.

## Rules that must survive every rebase

- The command allowlist (`btl_cmd_allowed()`) and the ASCII-identity rule (`btl_identity_valid()`):
  `tests/test_c_allowlist.py` must pass. Never add firmware update, bootloader switch, JTAG, MCU
  restore, or remove with an all-zero identity.
- Emulation-mode determinism (fixed test SM2 key, counter IVs) must stay gated on
  `fpi_device_emulation_mode_enabled()`.
- Never re-send SET_CONFIGURATION on open (USB data-toggle quirk, see `PROTOCOL.md`).
