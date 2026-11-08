# Validation and provenance

This document is for anyone deciding whether to trust this driver (users of the fork, or reviewers
if it is ever proposed upstream). It says how the driver was made, what was verified and how, what
went wrong along the way, and what is **not** verified. Detailed session log:
[`RE-NOTES.md`](RE-NOTES.md). Protocol: [`PROTOCOL.md`](PROTOCOL.md).

## How this was made (AI disclosure)

The reverse engineering, the protocol documentation, the Python tooling and the libfprint driver
were produced with **Claude Code** (Anthropic's AI coding agent, model Claude Opus 5.5) in a single
working session on 2026-11-09. Concretely:

| Done by Claude Code | Done by the human contributor |
|---|---|
| Static analysis of the vendor Windows driver (rizin/Ghidra decompilation) | Owns the hardware; every touch on the sensor |
| All code: `driver/`, `btl.py`, `btlcrypto.py`, `safety.py`, tests | Approved each step that writes to the module (first enroll, delete test, the one-off wipe) |
| Choosing what to test, reading logs, debugging | Ran every root command: udev rule, package installs, PAM, umockdev recording |
| These documents | Confirmed results only a person could see (sudo prompt, lock screen) |

The human contributor has **not reviewed the code line by line**. That review is recommended before
publishing the fork, and is a must before any upstream proposal. Commits carry a
`Co-Authored-By: Claude` trailer.

Why we think it can be trusted anyway is the rest of this document: every behaviour below was
observed on the real device, the risky parts are guarded by tests, and the failures are written
down rather than hidden.

## Evidence summary

| Claim | How it was verified | Result |
|---|---|---|
| Framing, CRC-32, SM2 key exchange, SM4 per-message encryption | Read-only probe on hardware; every reply decrypts to the expected `4C` magic | ✅ first attempt |
| Crypto implementation (Python) | GM/T test vectors for SM3/SM4; SM2 decrypt of an OpenSSL-generated ciphertext | ✅ `tests/test_offline.py` |
| Crypto implementation (C driver) | Uses OpenSSL EVP (SM2, SM4-ECB); key exchange works on hardware | ✅ |
| Enroll: 7 touches, touch index 1..7 | Python tool, libfprint examples, fprintd | ✅ (first attempt wrong, see failures) |
| Identify / verify | Python tool; libfprint examples; fprintd-verify | ✅ fprintd 3/3 (final run) |
| A module template that no print owns can't authenticate | Verified right thumb while only right index was in libfprint storage: module matched template 1, driver rejected it (tag check) | ✅ |
| Per-print delete | Delete by identity: count 3→2 and 2→1, deleted finger no longer matches, others still match | ✅ |
| Delete reports failure honestly | Deleting an already-removed print → `DATA_NOT_FOUND` ("0 before, 0 after") | ✅ |
| Cancel | Identify and enroll cancelled after 3 s; module cancel acknowledged; next operation fine; count unchanged | ✅ |
| fprintd | enroll 7/7, verify, delete via fprintd 1.94.5 | ✅ |
| PAM | sudo and KDE lock screen accept the finger; timeout falls back to the password | ✅ (LightDM, polkit configured but untested) |
| Replayable test | `tests/umockdev/` recorded on hardware (enroll, verify, identify, delete, clear_storage refused) | ✅ replay passes |
| Memory safety | Replay under valgrind | ✅ 0 bytes lost, 0 errors (re-run 2026-11-09 10:12 on the committed code) |
| No regressions in libfprint | Full test suite in the combined package build (with the Synochip driver) | ✅ 131/131 |
| hwdb entry | `fprint-list-udev-hwdb` output vs `data/autosuspend.hwdb`; `udev-hwdb` test | ✅ |
| Code style | libfprint's `scripts/uncrustify.cfg`, `--check` | ✅ |
| Safety allowlist (Python + C) | `tests/test_offline.py`, `tests/test_c_allowlist.py`: every blocked command, every p1, the all-zero (remove-all) identity | ✅ 13 tests |

## Safety approach

The sister project [`libfprint-synochip`] lost a reader to an assumed "clear all" command, so this
driver can only send an **allowlist** of exact command shapes that the vendor's own driver sends
during init, enroll, identify and delete. Firmware update, the switch into the bootloader, JTAG
control, MCU restore, sleep and image upload cannot be sent at all. The remove command is only
accepted with a print's own ASCII identity; the all-zero identity (= remove all templates) is
refused in both Python and C, and the tests check that.

Exceptions during development, both with explicit approval and reverted immediately (no diff left
in `safety.py`): one remove attempt with a guessed `FF…` identity (no effect), and **one** remove-all
to clear a leaked template (count 2 → 0).

## What went wrong along the way (all fixed)

1. **Enroll touch byte.** First enroll sent `01,00,00,…` instead of the touch index: the template
   was stored but matched poorly. Found by re-reading the vendor engine adapter.
2. **USB data toggle.** The firmware ignores the toggle reset of a repeated SET_CONFIGURATION, so
   every other packet was silently dropped after a reopen. The driver never re-sends it and retries
   a read-only query to resync.
3. **Binary identities.** The firmware treats the 32-byte identity as a C string. A delete with a
   random binary identity erased the record but leaked the slot; the leaked template still matched
   the finger and caused fprintd false rejects (2 of 7) until it was cleared. Identities are now
   printable ASCII; both allowlists enforce it.
4. **Missing scanned print.** Identify reported no scanned print; libfprint expects one. Found by
   the umockdev test, fixed.

## Not verified

- Commands known only from static analysis and never sent: `B4`–`B6`, `C2`, `C3`, `D0`, `D1`.
- Only **one unit** (`347d:0302`, firmware 01.00.00.00, project code `0x0F`, sensor 112 × 96) was
  tested. The vendor driver also lists `347d:0304` and SPI parts (`BF63112`, `BF61100`); not claimed.
- Other firmware versions; the vendor driver can update the module firmware (we never do).
- Coexistence with templates enrolled by Windows on a dual-boot machine (they can't authenticate
  on Linux, by design, but may cause false rejects like the leaked template did).
- Long-term reliability; LightDM and polkit PAM paths.

## Reproduce

```bash
.venv/bin/python -m unittest discover -s tests                 # offline: crypto, framing, allowlists
.venv/bin/python btl.py -v                                     # read-only hardware probe
meson test -C libfprint/build betterlife                       # umockdev replay (no hardware)
meson test -C libfprint/build --setup=valgrind betterlife      # same, under valgrind
uncrustify -c libfprint/scripts/uncrustify.cfg --check driver/betterlife.[ch]
```

[`libfprint-synochip`]: ../../libfprint-synochip
