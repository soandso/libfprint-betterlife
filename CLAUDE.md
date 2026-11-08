# libfprint-betterlife: project memory

libfprint match-on-chip driver (plus Python RE tooling) for the Betterlife / BLESTECH USB fingerprint
module `347d:0302`. Spec: `docs/PROTOCOL.md`. RE log + module state: `docs/RE-NOTES.md`.
Sister project with the same workflow: `../libfprint-synochip` (its first unit was bricked by an
assumed "clear all" opcode; that is why this project is allowlist-only).

## Ground rules
- **SAFETY (do not weaken):** only allowlisted command shapes may be sent. Python: `safety.py`
  `check_command()` inside `btl.build_frame()` (no override). C: `btl_cmd_allowed()` in `btl_cmd()`.
  `tests/test_offline.py` + `tests/test_c_allowlist.py` enforce both. Never write raw bytes to EP 0x02.
- **Never send** `B4 B5 B6`, `C2` (JTAG), `C3` (restore MCU), `D0` (FW update), `D1` (bootloader
  switch), or `B2` with an all-zero identity (= remove ALL). `B2` is allowed only as p1=1 + an ASCII
  identity (user approved 2026-11-09). Identities MUST be printable ASCII + NUL padding: a binary
  identity leaks a module slot (see PROTOCOL.md "Remove").
- 10 module slots (module wiped once with user approval on 2026-11-09). Enroll tests should delete
  what they add. `B2` replies 00 even for unknown identities: check the `B3` count.
- Use `.venv/bin/python -I`. Device access: udev rule `70-libfprint-betterlife.rules` (installed).
- Don't call pyusb `set_configuration()` on a configured device (data-toggle desync; see PROTOCOL.md).
- Interactive tests: run in background via `experiments/run.sh <script> <log>`, tell the user exactly
  which finger and how many touches, watch the log. Don't `pkill -f` with a pattern that appears in
  your own command line.
- Vendor Windows binaries stay out of the repo (scratch dir only).
- sudo needs the user (`! sudo ...`).

## Dev loop
- `libfprint/` (gitignored) = upstream v1.94.100 + driver. `meson compile -C libfprint/build`
  (betterlife only) or `build-all`. Examples: `experiments/lf-test/` with
  `../../libfprint/build/examples/{enroll,verify}` (stdin `6\n` = right index).
- After editing the driver: copy to `driver/`, re-export
  `git -C libfprint diff HEAD -- meson.build libfprint/meson.build data/autosuspend.hwdb libfprint/drivers/betterlife > packaging/0001-add-betterlife-driver.patch`,
  run `.venv/bin/python -m unittest discover -s tests`.
- umockdev test: `libfprint/tests/betterlife/` (copy in `tests/umockdev/`). Re-record (root, 9 touches with a
  finger NOT enrolled): `sudo modprobe usbmon && sudo libfprint/build/tests/create-driver-test.py --test custom betterlife`,
  then take ownership of the root-owned files. Replay: `meson test -C libfprint/build betterlife`
  (`--setup=valgrind` too). Any change to the command sequence needs a new recording; emulation
  mode makes the host side deterministic (fixed test SM2 key, counter IVs/identities).
- Export the patch with `--binary` and include `tests/meson.build tests/betterlife` (git add -N first).
- `examples/verify` fails with "Device has no storage" (no `list`); use
  `experiments/lf_verify_delete.py` (GI against libfprint/build, needs GI_TYPELIB_PATH/LD_LIBRARY_PATH).
- Package: sibling repo `../libfprint-btl-syno` (combined synochip + betterlife, replaces libfprint).
  It fetches `packaging/0001-add-betterlife-driver.patch` from here by file:// + b2sum. After
  re-exporting the patch, run `../libfprint-btl-syno/update.sh` (re-pins, bumps pkgrel, builds + tests).
