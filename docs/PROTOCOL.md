# Betterlife 347d:0302 protocol (as recovered)

Status: framing, CRC, SM2/SM4, A0–A2, B0, B1, B3, C0, C1 **verified on hardware** (2026-11-09).
B2, B4–B6, C2, C3, D0, D1 are known only statically and are **never sent**. Source: vendor Windows WBDI driver
`BLESTECH - Biometric - 14.36.53.907` (Microsoft Update Catalog, `usb\vid_347d&pid_0302`; also
lists `PID_0304`, `ACPI\BF63112`, `ACPI\BF61100`).

## Hardware

```
ID 347d:0302 "btlfp" / "Betterlife Fingerprint", iSerial "Betterlife V1.0.0.0-0f00"
USB 1.1 full speed, 1 config, IF0 class FF: EP 0x81 bulk IN 64, EP 0x02 bulk OUT 64
```

A module with its own MCU (Nations N32G4FR, Cortex-M4, firmware embedded in the Windows driver as
resources BIN/144 and BIN/145) running the sensor, matcher and template store: **match-on-chip**.
The Windows package also carries a host-side matcher (Precise Biometrics), which is only used
for the SPB/ACPI sensor variants.

## Frame

Same layout in both directions:

| Off | Size | Field |
|---|---|---|
| 0 | 1 | `AA` sync |
| 1 | 4 | `L`, LE32 = 20 + body length. Total frame = L + 5 |
| 5 | 16 | IV. **All zeros = plaintext body**; otherwise the body is encrypted |
| 21 | L−20 | body (multiple of 16) |
| L+1 | 4 | CRC-32 (zlib/IEEE), LE, over bytes `0 .. L` |

Body (before encryption; zero-padded to a multiple of 16):

| Off | Field |
|---|---|
| 0 | `4C` ('L') magic |
| 1 | cmd |
| 2 | p1 (sub-command; echoed in replies) |
| 3 | `00` |
| 4, 5 | p2, p3 (always 0 in the Windows driver) |
| 6 | data length, LE32 |
| 10 | data |

Replies use the same body format: `cmd`/`p1` echo the request, `data[0]` is usually a status byte.

## Encryption

1. Host generates an ephemeral SM2 key pair (sm2p256v1) and sends `A2` with its public key
   `04‖X‖Y` (65 bytes, plaintext frame).
2. Module replies with ≥ 113 bytes: `04‖C1.x‖C1.y‖C3(32)‖C2(16)`, standard GM/T 0003 SM2
   encryption (C1C3C2 order, SM3 KDF) of the 16-byte **session key**.
3. Encrypted frame: random 16-byte IV, `K_msg = SM4_encrypt(session_key, IV)`, body is
   SM4-ECB with `K_msg`. Replies to encrypted commands are encrypted the same way.

`A1` reports the scheme: `[1]` 0=SM2/1=RSA1024/2=RSA2048, `[2]` 0=SM4-ECB/1=CBC/2=CTR/3=GCM,
`[3]` 0=SM3/1=MD5/2=SHA-1/3=SHA-256/4=SHA-512. The Windows driver itself only implements SM2 + SM4-ECB.

## Commands

| cmd | name (driver string table) | enc | sent by Windows | notes |
|---|---|---|---|---|
| A0 | QUERY_FIRMWARE_VER | no | init | ≥7 B: `[0]` crypto flag, `[1..2]` project code, `[3..6]` version |
| A1 | QUERY_MODULE_SCHEME_INFORMATION | no | init | 4 B, see above |
| A2 | QUERY_ROOT_KEY | no | init | key exchange, see above |
| B0 | ENROLL_FINGERPRINT | yes | enroll | p1: 0 start, 1 touch, 2 finish, 3 cancel |
| B1 | IDENTIFY_FINGERPRINT | yes | verify | p1: 0 start, 1 cancel. Result is asynchronous |
| **B2** | **REMOVE_FINGERPRINT** | yes | delete | **p1=0 single, p1≠0 ALL**. ⚠ blocked |
| B3 | QUERY_FINGERPRINT_COUNT | yes | storage | 2× LE16 |
| B4 | GET_IMG_DATA | yes | diagnostics | p1: 0 start, 1 upload, 2 cancel. blocked (unneeded) |
| B5 | DETECT_FINGERPRINT_PRESS | – | **never** | blocked |
| B6 | SLEEP | – | **never** | blocked |
| C0 | QUERY_MODULE_UID | yes | init | 16..32 B |
| C1 | QUERY_SENSOR_INFO | yes | init | ≥9 B: chip id (4), 2× LE16 rows/cols, tech byte |
| **C2** | JTAG_CONTROL | – | **never** | ⚠ blocked |
| **C3** | RESTORE_MCU | – | **never** | ⚠ blocked |
| **D0** | UPDATE_FIRMWARE | no | FW update | ⚠ blocked |
| **D1** | FW_WORK_MODE_SWITCH | yes | FW update | p1=0 → "Boot", 1 → "App". ⚠ blocked |

Windows init: `A0` → (if the module FW is older than the embedded one: `D0`/`D1` update — we never
do this) → `A1` → SM2 keygen → `A2` → `C0` → `C1`.

### Enroll (B0) — verified
- start `p1=0`, data `00` → `00 07`: status, **number of touches needed (7)**.
- touch `p1=1`, data = **1-based index of this touch** (Windows engine: `SET_CUR_ENROLLED_TIMES`,
  incremented after every accepted touch) → immediate empty ack, then, once a finger was processed,
  an asynchronous `B0/1` frame `[0]` status, `[1]` echo of the index. On a rejected touch, resend the
  same index. ⚠ Sending `01,00,00,…` instead also "works" but stores a template that hardly matches.
- finish `p1=2`, data = 32-byte identity (Windows: the account SID, zero-padded) → `[0]` status,
  `[1..2]` LE16 template id (0, 1, 2 … in order), `[3..18]` 16-byte tag (random-looking, not
  derived from the identity in any obvious way). Finishing without enough touches → status `13`,
  nothing stored.
- cancel `p1=3`, data `00` → `00`.

### Identify (B1) — verified
- start `p1=0`, no data → empty ack; when a finger is processed the module sends `B1/0` with
  `[0]` status (`00` match, `21` no match), `[1..2]` LE16 template id, `[3..18]` the template's
  16-byte tag (identical to the one returned by enroll finish). Cancel: `p1=1`.
- The module searches **all** its templates. The driver accepts a match only if template id *and*
  tag equal the ones stored in the libfprint print.

### Other verified values (this unit)
- `A0` → `01 0f 00 01 00 00 00`; `A1` → `10 00 00 ff` (SM2, SM4-ECB); `C1` → `83 5f 00 00 70 00 60 00 00`
  (chip `0x5F83`, 112 × 96); `B3` → `count LE16, max LE16` = 10 templates max; `C0` → 16 bytes.
- Replies to encrypted commands reuse the request's IV.

## USB quirks (verified)
- **Data toggle:** the firmware does not reset its bulk OUT data toggle on a repeated
  SET_CONFIGURATION. A host that re-sends SET_CONFIGURATION (pyusb `set_configuration()`) gets
  every other packet silently dropped. Don't send it if the device is already configured.
- **Echo after an interrupted session:** the module may bounce the host's frame back unchanged
  (an "empty" reply with the request's own CRC), followed by a 16-byte fragment. `A0` is read-only
  and fits one packet, so open retries it until a real (≥ 7-byte) reply arrives.
- Frames are always 29 + 16·k bytes, never a multiple of 64, so a large bulk read always ends with
  a short packet at a frame boundary.

### Status codes (from BetterlifeSensorAdapter.dll)
`10` no finger, `11` lifted too fast, `12` already enrolled, `13` save failed, `14` overlap too
large, `21` no match, `30` finger away, `31` algorithm failed, `32` not live, `33` wet, `34` dry,
`35` area too small, `36` poor quality, `41` flash r/w failed, `F0` internal.
