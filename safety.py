"""Hard safety guard for anything that sends bytes to the Betterlife reader (347d:0302).

Every send path calls check_command() before a frame is built. There is deliberately NO
override flag. Policy (lesson from libfprint-synochip, where an assumed "clear all" opcode
permanently switched a reader into an unusable firmware mode):

  * Only (cmd, p1) pairs that the vendor Windows driver sends during its normal init /
    identify / enroll flows are allowed, with exactly the payload shape it uses.
  * Template removal (0xB2, both "single" and "all"), firmware update / mode switch,
    JTAG, MCU restore and sleep are blocked. Several of these are never sent by the
    Windows driver at all; their on-device behaviour is unknown.
"""

BLOCKED = {
    0xB2: "CMD_REMOVE_FINGERPRINT: p1=0 single, p1!=0 ALL templates (clear-all). Not enabled",
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
    (0xB0, 1): (True, {1}),         # enroll: one touch  (data: first-touch flag)
    (0xB0, 2): (True, {32}),        # enroll: finish, store under a 32-byte identity
    (0xB0, 3): (True, {1}),         # enroll: cancel     (data: 00)
}


class UnsafeCommand(Exception):
    pass


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
    if cmd == 0xA2 and data[0] != 0x04:
        raise UnsafeCommand("0xA2 payload must be an uncompressed SM2 point")
