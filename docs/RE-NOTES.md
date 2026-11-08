# Reverse-engineering log

## Sources

Microsoft Update Catalog, search `VID_347D` (25 results; BLESTECH and YLDTECH). Hardware IDs per
update were read from the catalog's details pages. `usb\vid_347d&pid_0302` is covered by:

- `BLESTECH - Biometric - 14.36.53.907` (INF DriverVer 03/04/2024), **used for RE**
- `<BLESTECH> - Biometric - 11.43.14.455`, `9.0.26.943` (older)

Other PIDs (`00f0`, `0c02`, `0c04`) use different packages and were not examined.

Files (14.36.53.907): `BetterlifeFingerprintDevice.dll` (UMDF2 WBDI driver, WinUSB),
`BetterlifeEngineAdapter.dll`, `BetterlifeSensorAdapter.dll`, `BetterlifeStorageAdapter.dll`, INF.
The device DLL's resources `BIN/143..149` are firmware images (143: small, probably bootloader;
144/145: N32G4FR app at 0x08000000; 149: another MCU). The vendor binaries are **not** in this repo.

Tooling: rizin 0.8 + rz-ghidra (`pdg`), Python for table dumps.

## Function map (BetterlifeFingerprintDevice.dll, image base 0x180000000)

| Address | Role |
|---|---|
| `0x18003dbd0` | command table, 0x20-byte entries `{cmd, name*, reply_handler*, short_name*}` A0..D1 |
| `fcn.180018318` | reply dispatcher: body `+1` cmd, `+2` p1, `+6` LE32 len, `+10` data |
| `fcn.180004258` | frame sender: `AA`, LE32 L, IV, body, CRC32; SM4 per-message key |
| `fcn.180002814` | body serializer `4C cmd p1 00 p2 p3 len32 data` |
| `fcn.1800029a0` | random IV (16 B) for encrypted requests |
| `fcn.18000cd10` / `fcn.18000b500` | SM4 key schedule / block (S-box at file offset 0x2e910) |
| receive path around `0x1800186c1..0x180018a59` | sync `AA`, length, CRC check, IV≠0 → SM4 decrypt, magic `4C` |
| `fcn.180004768` | generic `send(cmd, p1, encrypt, wait)` |
| `fcn.180001000` | enroll `B0` (p1 0 start / 1 touch / 2 finish / 3 cancel) |
| `fcn.180001598` | identify `B1` (0 start / 1 cancel) |
| `fcn.180001c10` | remove `B2` (p1 0 "Single", else "All") |
| `fcn.180001a04` | key exchange `A2` (65-byte host SM2 pubkey from ctx+0x16a28) |
| `fcn.180015e20` | `A2` reply: gmssl `SM2_CIPHERTEXT` (point, hash, size=16, ct) → `fcn.180007980` SM2 decrypt → session key ctx+0x16a08 |
| `fcn.180016fb4` | device init: A0 → (FW compare, D0/D1 update) → A1 → keygen → A2 → C0 → C1 |
| `fcn.180001da8` / `fcn.180001230` | `D0` update FW / `D1` work-mode switch ("Boot"/"App") |

Engine adapter: `EngineAdapterAcceptSampleData` (`0x18009b060`) increments a counter after every
accepted enroll touch and sends it with `IOCTL_CUSTOM_SET_CUR_ENROLLED_TIMES` (0x440428); the device
DLL stores it at ctx+0x169b4 and sends it as the `B0/1` data byte. `EngineAdapterCommitEnrollment`
sends `IOCTL_CUSTOM_END_ENROLL` (0x440410) with the 32-byte account SID.

## Session log (2026-11-09)

1. `lsusb`: `347d:0302 btlfp Betterlife Fingerprint`, vendor class, bulk 0x81/0x02.
2. Catalog download, INF: own engine/sensor/storage adapters (algorithm in the package is for the
   SPB variants); USB variant is a match-on-chip module. Command name table found in `.data`.
3. Framing, CRC, body format, SM2 key exchange and SM4-per-message scheme recovered statically.
   Python SM2/SM3/SM4 written (`btlcrypto.py`), checked against standard vectors and against an
   OpenSSL-generated SM2 ciphertext.
4. Safety policy: allowlist of the exact (cmd, p1, enc, len) shapes Windows sends for init /
   enroll / identify. `B2` (remove, incl. remove-all) and every never-sent or firmware command
   blocked. `B5 B6 C2 C3` have no sender in the Windows driver at all.
5. First probe (read-only): everything worked first try. Module empty (0 of 10 templates).
6. Second process got no replies → **data-toggle bug**: the firmware ignores the toggle reset of a
   repeated SET_CONFIGURATION; packet-count parity explained every success/failure. Fix: never re-send
   SET_CONFIGURATION; `A0` doubles as resync.
7. Identify with an empty module: ack, then async `21` (no match). As predicted.
8. Enroll #1 sent touch bytes `01,00,00,…` → template 0 stored (tag `de4ae406…`) but matched poorly
   (2 misses, 1 later hit). Static re-check found the touch-index counter in the engine adapter.
9. Enroll #2 aborted (no touch within the timeout), finish → `13`, nothing stored.
10. Enroll #3 with indices 1..7 (right thumb): module echoes the index, template 1, identify 2/2 match,
    right index rejected.
11. libfprint driver (`driver/betterlife.c`, OpenSSL for SM2/SM4): enroll right index 7/7 → template 2;
    verify: 1 false reject, 1 match; right thumb → module matched template 1 → driver rejected (tag
    not in the print) → NO MATCH. Correct.

## Module state after this session

| Template | Finger | Created by | Notes |
|---|---|---|---|
| 0 | unknown (user's first test) | Python, wrong touch indices | poor template |
| 1 | right thumb | Python test (`BTLTEST2`) | |
| 2 | right index | libfprint enroll example | its print is in `experiments/lf-test/` (gitignored) |

None can be removed without `B2`, which is blocked. 7 of 10 slots are free.

## Open problems

- **Delete.** `B2` p1=0 ("Single") is how Windows deletes a template; its data comes from the storage
  adapter (not yet analysed: probably the LE16 template id). `B2` with p1≠0 is remove-**all**.
  Neither is enabled. Without it, every enrollment uses a slot for good (10 total).
- `A0[0]` (crypto flag) and `A1[0]`/`[3]` semantics beyond what the driver needs.
- Enroll touch result byte `[1]` echoes the index; whether it can differ (e.g. module wants more
  touches) is unknown.
