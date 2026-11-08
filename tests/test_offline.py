"""No-hardware tests: crypto vectors, frame codec round trip, and the safety allowlist."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btl  # noqa: E402
import btlcrypto  # noqa: E402
from safety import UnsafeCommand, BLOCKED  # noqa: E402


class Crypto(unittest.TestCase):
    def test_selftest(self):
        self.assertTrue(btlcrypto.selftest())


class Frames(unittest.TestCase):
    def test_plain_roundtrip(self):
        f = btl.build_frame(0xA0)
        self.assertEqual(f[0], 0xAA)
        self.assertEqual(len(f), 5 + 20 + 16)
        self.assertEqual(f[5:21], bytes(16))
        r = btl.parse_frame(f)
        self.assertEqual((r["cmd"], r["p1"], r["data"], r["encrypted"]), (0xA0, 0, b"", False))

    def test_encrypted_roundtrip(self):
        k = os.urandom(16)
        ident = b"BTLTEST9".ljust(32, b"\0")
        f = btl.build_frame(0xB0, 2, ident, True, k)
        self.assertNotEqual(f[5:21], bytes(16))
        r = btl.parse_frame(f, k)
        self.assertEqual((r["cmd"], r["p1"], r["data"]), (0xB0, 2, ident))

    def test_bad_crc(self):
        f = bytearray(btl.build_frame(0xA0))
        f[-1] ^= 1
        with self.assertRaises(btl.BtlError):
            btl.parse_frame(bytes(f))


class Safety(unittest.TestCase):
    def test_blocked_commands_never_build(self):
        for cmd in BLOCKED:
            for p1 in range(256):
                for enc in (False, True):
                    with self.assertRaises(UnsafeCommand):
                        btl.build_frame(cmd, p1, b"", enc, bytes(16))

    def test_clear_all_blocked(self):
        k = bytes(16)
        for p1 in range(256):
            for data in (b"", b"\x00", bytes(32), b"\xff\xff", b"\x01" * 31, b"\x01" * 33):
                with self.assertRaises(UnsafeCommand, msg=f"B2/{p1} {data.hex()}"):
                    btl.build_frame(0xB2, p1, data, True, k)
        for p1 in set(range(256)) - {1}:
            with self.assertRaises(UnsafeCommand):
                btl.build_frame(0xB2, p1, b"x".ljust(32, b"\0"), True, k)
        with self.assertRaises(UnsafeCommand):
            btl.build_frame(0xB2, 1, b"x".ljust(32, b"\0"), False)     # must be encrypted
        btl.build_frame(0xB2, 1, b"BTLTEST1".ljust(32, b"\0"), True, k)   # the only allowed shape
        for bad in (b"\x00" + b"A" * 31, b"A" * 32, b"AB\x00C".ljust(32, b"\0"), b"\x9a\x01".ljust(32, b"\0"),
                    b"A B".ljust(32, b"\0")):
            for cmd, p1 in ((0xB2, 1), (0xB0, 2)):
                with self.assertRaises(UnsafeCommand, msg=bad.hex()):
                    btl.build_frame(cmd, p1, bad, True, k)
        btl.build_frame(0xB0, 2, b"LFP-0123456789abcdef0123456789".ljust(32, b"\0"), True, k)

    def test_unknown_commands_blocked(self):
        allowed = {0xA0, 0xA1, 0xA2, 0xB0, 0xB1, 0xB2, 0xB3, 0xC0, 0xC1}
        for cmd in set(range(256)) - allowed:
            with self.assertRaises(UnsafeCommand):
                btl.build_frame(cmd, 0, b"", True, bytes(16))

    def test_shape_enforced(self):
        with self.assertRaises(UnsafeCommand):
            btl.build_frame(0xA0, 0, b"\x01")           # extra data
        with self.assertRaises(UnsafeCommand):
            btl.build_frame(0xB3, 0, b"", False)         # must be encrypted
        with self.assertRaises(UnsafeCommand):
            btl.build_frame(0xB1, 2, b"", True, bytes(16))  # unknown sub-command
        with self.assertRaises(UnsafeCommand):
            btl.build_frame(0xA0, 0, b"", False, p2=1)


if __name__ == "__main__":
    unittest.main()
