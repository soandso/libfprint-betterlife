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

12. Packaging: combined Arch package `libfprint-btl-syno` (synochip patch unchanged + this driver).
13. **Delete RE (static):** only sender of the remove IOCTL (0x44041c) is the storage adapter's
    `DeleteRecord`: `[01] + 32 B`; SID copied in when other host records remain, else left zero →
    zero identity = wipe. Device DLL maps buf[0] → p1, rest → data.
14. Test (user-approved): `B2/1 "BTLTEST1"` → `00`, count 3→2; thumb and index still match.
15. C driver delete with its random binary identity: `00`, but count unchanged and the index still
    matched with tag `ff…ff`. After unplug/replug: no match, count still 2 → leaked slot.
16. `B2/1 "BTLTEST2"` → count 2→1, thumb no longer matches. ⇒ identity is a C string.
17. Driver switched to ASCII identities (`LFP-` + 26 hex); both allowlists require printable ASCII +
    NUL padding for B0 finish and B2. libfprint: enroll right middle → template 0 (slot reuse),
    verify MATCH, delete → count 2→1, identify → no match.
18. fprintd 1.94.5 only deletes on the device if FP_DEVICE_FEATURE_STORAGE, which libfprint sets for
    delete + (list or clear_storage). The driver implements clear_storage as NOT_SUPPORTED (sends
    nothing) to get that flag; fprintd then only warns before a first enrollment.

19. Package pkgrel 2 installed; fprintd-enroll right index 7/7 → template 0. fprintd-verify: 2 of 7
    matched. fprintd debug (`G_MESSAGES_DEBUG=libfprint-betterlife` drop-in): the module recognised
    the finger every time (status 00) but returned the **leaked template 2** (also right index) in
    2 of 3 → the driver correctly rejected it. So the zombie still matched; the earlier post-replug
    "no match" was a false reject.
20. `B2/1` + 32×`FF` (guessing the erased identity; temporary Python-only exception, reverted):
    reply `00`, count unchanged. ⇒ B2 always answers 00.
21. One-off remove-all (`B2/1` + 32 zero bytes, user-approved, temporary exception reverted
    immediately): count 2 → 0. Module answers normally afterwards.
22. Driver delete now compares the B3 count before/after and returns DATA_NOT_FOUND on a no-op
    (checked by deleting an already-removed print). Package pkgrel 3.

23. pkgrel 3 installed. `fprintd-delete dave` on the stale print: driver reported DATA_NOT_FOUND
    (0 before, 0 after), fprintd removed the host print. `fprintd-enroll` right index 7/7,
    `fprintd-verify` **3/3 match**.

24. Cancel (`experiments/lf_cancel.py`): identify and enroll cancelled after 3 s send `B1/1` / `B0/3`,
    get an immediate reply, return G_IO_ERROR_CANCELLED; next operation fine; count unchanged.
25. PAM: `scripts/pam-enable.sh` adds `auth sufficient pam_fprintd.so max-tries=3 timeout=10` to
    sudo, polkit-1 (new /etc copy) and lightdm. sudo: fingerprint accepted; timeout falls back to the
    password. KDE lock screen (kde-fingerprint): works. LightDM/polkit not separately tested.

26. umockdev test. The host side is randomised (SM2 key, IVs, identities), so in libfprint emulation
    mode (`fpi_device_emulation_mode_enabled()`: FP_DEVICE_EMULATION=1 *and* the test helper library
    present, i.e. never in an installed package built with installed-tests=false) the driver uses a
    fixed test-only SM2 key pair and counter-based IVs/identities. First recording failed twice over:
    `usbmon` module not loaded (tshark "Permission denied"), and identify reported no scanned print
    (libfprint expects one equal to the match) — fixed (`btl_scanned_print`). The crashed run left
    its left-index template on the module; removed by its deterministic identity
    `LFP-a5a5a5a5a5a5a5a5a50000000a` (count 2→1). Second recording OK (enroll 7/7, verify, identify,
    delete). Replay: `meson test betterlife` OK, valgrind 0 leaks / 0 errors, all-drivers suite and
    the package check() 131/131.

27. Docs: AI disclosure + evidence (`VALIDATION.md`), fork maintenance (`MAINTAINING.md`). Decision:
    the driver lives as a fork; not proposed upstream for now (context: the CS9711 driver's sigfm
    dependency, MRs !418/!530, has been in review since 2022). Patch applies cleanly to upstream
    master `6f9479c`, alone and on top of the Synochip patch.
28. Published: public GitHub repo `soandso/libfprint-betterlife`, release **v0.1.0** (patch asset,
    checksum verified after download). AUR-ready `packaging/aur/` (builds from the release,
    131/131), **not** published to the AUR (decision). Another project already supports this reader:
    `arqueon/betterlife-347d-libfprint` (AUR `libfprint-betterlife-347d-git`, 2026-10-30): adds
    `347d:0304` (match-on-host, needs OpenCV/SIGFM on top of the CS9711 fork), and its
    `clear_storage` sends remove-all, so fprintd wipes the module before a first enrollment.
29. Housekeeping: per-read debug line removed (replay, valgrind, uncrustify re-run); VALIDATION lists
    the untested paths. Combined package: `update.sh` re-hashed a stale cached `file://` patch, fixed
    (pkgrel 6). Synochip README got an AI disclosure.

## Module state after this session

1 of 10: the user's fprintd right-index enrollment (template 0).

## Open problems

- libfprint's `examples/verify` takes its device-storage path once STORAGE is advertised and fails
  without `list`; use `experiments/lf_verify_delete.py` or fprintd instead.
- `A0[0]` (crypto flag) and `A1[0]`/`[3]` semantics beyond what the driver needs.
- Enroll touch result byte `[1]` echoes the index; whether it can differ (e.g. module wants more
  touches) is unknown.
