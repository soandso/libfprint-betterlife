"""Hard safety guard for anything that sends bytes to the Betterlife reader (347d:0302).

Every send path calls check_command() before a frame is built. There is deliberately NO
override flag. Policy (lesson from libfprint-synochip, where an assumed "clear all" opcode
permanently switched a reader into an unusable firmware mode):

  * Only (cmd, p1) pairs that the vendor Windows driver sends during its normal init /
    identify / enroll flows are allowed, with exactly the payload shape it uses.
  * Template removal is allowed only as 0xB2 p1=1 with a NON-ZERO 32-byte identity (an
    all-zero identity means "remove all"). Firmware update / mode switch, JTAG, MCU
    restore, sleep and image upload are blocked. Several of these are never sent by the
    Windows driver at all; their on-device behaviour is unknown.
"""

BLOCKED = {
    0xB4: "CMD_GET_IMG_DATA: raw image upload (diagnostic); not needed, not enabled",
    0xB5: "CMD_DETECT_FINGERPRINT_PRESS: never sent by the Windows driver",
    0xB6: "CMD_SLEEP: never sent by the Windows driver",
    0xC2: "CMD_JTAG_CONTROL: debug-port control, never sent by the Windows driver",
    0xC3: "CMD_RESTORE_MCU: never sent by the Windows driver; may wipe the module",
    0xD0: "CMD_UPDATE_FIRMWARE: flash write",
    0xD1: "CMD_FW_WORK_MODE_SWITCH: p1=0 reboots into the bootloader",
}

# (cmd, p1) -> (must_encrypt, allowed data lengths)
ALLOWED = {
    (0xA0, 0): (False, {0}),        # query firmware version
    (0xA1, 0): (False, {0}),        # query crypto scheme
    (0xA2, 0): (False, {65}),       # key exchange: host SM2 public key 04||X||Y
    (0xC0, 0): (True, {0}),         # query module UID
    (0xC1, 0): (True, {0}),         # query sensor info
    (0xB3, 0): (True, {0}),         # query fingerprint (template) count
    (0xB1, 0): (True, {0}),         # identify: start (result arrives asynchronously)
    (0xB1, 1): (True, {0}),         # identify: cancel
    (0xB0, 0): (True, {1}),         # enroll: start      (data: 00)
    (0xB0, 1): (True, {1}),         # enroll: one touch  (data: 1-based touch index)
    (0xB0, 2): (True, {32}),        # enroll: finish, store under a 32-byte identity
    (0xB0, 3): (True, {1}),         # enroll: cancel     (data: 00)
    (0xB2, 1): (True, {32}),        # remove the templates enrolled under this ASCII identity
}

# 0xB2 (CMD_REMOVE_FINGERPRINT): the Windows storage adapter only ever sends p1=1 with a 32-byte
# identity; it sends 32 ZERO bytes when its database became empty, i.e. zeros = remove ALL.
# Only p1=1 with an ASCII identity is allowed (see identity_valid). p1=0 ("Single" in the
# driver log) is never sent by Windows.


class UnsafeCommand(Exception):
    pass


def identity_valid(data: bytes) -> bool:
    """The firmware treats the 32-byte identity as a C string (a binary identity made removal
    only half work and leaked a slot, 2026-11-09). Require 1..31 printable ASCII characters
    followed by NUL padding. This also rules out the all-zero "remove all" identity."""
    if len(data) != 32:
        return False
    n = 0
    while n < 32 and 0x21 <= data[n] <= 0x7E:
        n += 1
    return 0 < n < 32 and not any(data[n:])


def check_command(cmd: int, p1: int, p2: int, p3: int, data: bytes, encrypt: bool) -> None:
    """Raise UnsafeCommand unless this exact command shape is allowed."""
    if cmd in BLOCKED:
        raise UnsafeCommand(f"CMD 0x{cmd:02X} is blocked: {BLOCKED[cmd]}")
    key = (cmd, p1)
    if key not in ALLOWED:
        raise UnsafeCommand(f"CMD 0x{cmd:02X} p1={p1} is not on the allowlist")
    must_enc, lens = ALLOWED[key]
    if p2 or p3:
        raise UnsafeCommand(f"CMD 0x{cmd:02X}: p2/p3 must be 0")
    if len(data) not in lens:
        raise UnsafeCommand(f"CMD 0x{cmd:02X} p1={p1}: data length {len(data)} not in {sorted(lens)}")
    if encrypt != must_enc:
        raise UnsafeCommand(f"CMD 0x{cmd:02X} p1={p1}: encrypt must be {must_enc}")
    if cmd == 0xB2 and not any(data):
        raise UnsafeCommand("0xB2 with an all-zero identity removes ALL templates: blocked")
    if (cmd, p1) in ((0xB2, 1), (0xB0, 2)) and not identity_valid(data):
        raise UnsafeCommand(f"CMD 0x{cmd:02X} p1={p1}: identity must be printable ASCII + NUL padding")
    if cmd == 0xA2 and data[0] != 0x04:
        raise UnsafeCommand("0xA2 payload must be an uncompressed SM2 point")
