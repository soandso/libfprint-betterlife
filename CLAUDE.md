# libfprint-betterlife: project memory

libfprint match-on-chip driver (plus Python RE tooling) for the Betterlife / BLESTECH USB fingerprint
module `347d:0302`. Spec: `docs/PROTOCOL.md`. RE log + module state: `docs/RE-NOTES.md`.
Sister project with the same workflow: `../libfprint-synochip` (its first unit was bricked by an
assumed "clear all" opcode; that is why this project is allowlist-only).

## Ground rules
- **SAFETY (do not weaken):** only allowlisted command shapes may be sent. Python: `safety.py`
  `check_command()` inside `btl.build_frame()` (no override). C: `btl_cmd_allowed()` in `btl_cmd()`.
  `tests/test_offline.py` + `tests/test_c_allowlist.py` enforce both. Never write raw bytes to EP 0x02.
- **Never send** `B2` (remove; p1≠0 = remove ALL), `B4 B5 B6`, `C2` (JTAG), `C3` (restore MCU),
  `D0` (FW update), `D1` (bootloader switch). Enabling `B2` single-delete needs the user's explicit OK.
- Enrolling consumes one of 10 module slots permanently while `B2` is blocked. Don't enroll casually.
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
- umockdev is not installed, so libfprint driver tests skip.
