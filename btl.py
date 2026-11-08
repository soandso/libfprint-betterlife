#!/usr/bin/env python3
"""Userspace RE/test driver for the Betterlife (BLESTECH) USB fingerprint module, 347d:0302.

Protocol recovered from the vendor Windows WBDI driver (BetterlifeFingerprintDevice.dll
14.36.53.907); see docs/PROTOCOL.md.

Frame (both directions, bulk EP 0x02 OUT / 0x81 IN):
    AA | L (LE32) | IV (16) | body | CRC32 (LE, standard, over AA..body)
    L = 20 + len(body); IV all-zero => body is plaintext
body (padded with zeros to a multiple of 16; SM4-ECB encrypted when IV != 0):
    4C | cmd | p1 | 00 | p2 | p3 | datalen (LE32) | data
"""
import os
import struct
import sys
import time
import zlib

import usb.core
import usb.util

import btlcrypto as bc
from safety import check_command

VID, PID = 0x347D, 0x0302
EP_OUT, EP_IN = 0x02, 0x81

STATUS = {
    0x00: "OK",
    0x10: "enroll: no finger press",
    0x11: "enroll: finger lifted too fast",
    0x12: "enroll: this finger is already enrolled",
    0x13: "enroll: template save failed",
    0x14: "enroll: overlap with previous touches too large",
    0x21: "identify: no matching template",
    0x30: "finger away",
    0x31: "algorithm processing failed",
    0x32: "not a live finger",
    0x33: "finger too wet",
    0x34: "finger too dry",
    0x35: "valid area too small",
    0x36: "image quality too poor",
    0x41: "flash read/write failed",
    0xF0: "internal error",
}

PROJECT = {1: "BOE MOC", 2: "HUAHONG MOUSE MOC", 3: "DYW MOH", 4: "NATION TEST", 6: "NATIONALCHIP"}


class BtlError(Exception):
    pass


def build_frame(cmd, p1=0, data=b"", encrypt=False, session_key=None, p2=0, p3=0, iv=None):
    """Build one host->module frame. SAFETY: refuses anything not on the allowlist."""
    check_command(cmd, p1, p2, p3, data, encrypt)
    body = bytes([0x4C, cmd, p1, 0, p2, p3]) + struct.pack("<I", len(data)) + data
    body += b"\0" * (-len(body) % 16)
    if encrypt:
        if session_key is None:
            raise BtlError("encrypted command before key exchange")
        iv = iv or os.urandom(16)
        body = bc.sm4_ecb_encrypt(bc.msg_key(session_key, iv), body)
    else:
        iv = bytes(16)
    head = b"\xAA" + struct.pack("<I", 20 + len(body)) + iv + body
    return head + struct.pack("<I", zlib.crc32(head) & 0xFFFFFFFF)


def parse_frame(frame: bytes, session_key=None):
    """Returns dict(cmd, p1, p2, p3, data, encrypted). Raises BtlError on a bad frame."""
    if frame[0] != 0xAA:
        raise BtlError(f"bad sync byte {frame[0]:02x}")
    ln = struct.unpack_from("<I", frame, 1)[0]
    if len(frame) != ln + 5:
        raise BtlError(f"length mismatch: header {ln + 5}, got {len(frame)}")
    crc = struct.unpack_from("<I", frame, ln + 1)[0]
    if zlib.crc32(frame[:ln + 1]) & 0xFFFFFFFF != crc:
        raise BtlError("CRC mismatch")
    iv, body = frame[5:21], frame[21:ln + 1]
    enc = any(iv)
    if enc:
        if session_key is None:
            raise BtlError("encrypted reply but no session key")
        if len(body) % 16:
            raise BtlError("encrypted body not block aligned")
        body = bc.sm4_ecb_decrypt(bc.msg_key(session_key, iv), body)
    if body[0] != 0x4C:
        raise BtlError(f"bad body magic {body[0]:02x} (decryption problem?)")
    dlen = struct.unpack_from("<I", body, 6)[0]
    if 10 + dlen > len(body):
        raise BtlError(f"data length {dlen} exceeds body")
    return dict(cmd=body[1], p1=body[2], p2=body[4], p3=body[5], data=body[10:10 + dlen], encrypted=enc)


class Btl:
    def __init__(self, debug=False):
        self.debug = debug
        self.session_key = None
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError("reader 347d:0302 not found")
        try:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            pass
        # Do NOT re-send SET_CONFIGURATION on an already-configured device: the module firmware
        # does not reset its OUT data toggle on it, so the host and module toggles desync and
        # the module silently drops every other packet (see docs/RE-NOTES.md).
        try:
            self.dev.get_active_configuration()
        except usb.core.USBError:
            self.dev.set_configuration()
        usb.util.claim_interface(self.dev, 0)
        self._rx = bytearray()

    def close(self):
        usb.util.release_interface(self.dev, 0)
        usb.util.dispose_resources(self.dev)

    def _log(self, *a):
        if self.debug:
            print(*a, file=sys.stderr)

    # --- transport -----------------------------------------------------------------
    def send(self, cmd, p1=0, data=b"", encrypt=False):
        f = build_frame(cmd, p1, data, encrypt, self.session_key)
        self._log(f">> cmd={cmd:02X} p1={p1} enc={int(encrypt)} data={data.hex(' ')}")
        self._log(f"   raw[{len(f)}] {f.hex(' ')}")
        self.dev.write(EP_OUT, f, timeout=1000)

    def recv(self, timeout=2000):
        """Read one complete frame (blocks up to `timeout` ms per USB read)."""
        while True:
            if len(self._rx) >= 5:
                if self._rx[0] != 0xAA:
                    i = self._rx.find(b"\xAA")
                    self._log(f"!! dropping {len(self._rx) if i < 0 else i} junk bytes: {bytes(self._rx[:32]).hex(' ')}")
                    del self._rx[:len(self._rx) if i < 0 else i]
                    continue
                need = struct.unpack_from("<I", self._rx, 1)[0] + 5
                if need > 0x20000:
                    raise BtlError(f"implausible frame length {need}")
                if len(self._rx) >= need:
                    raw = bytes(self._rx[:need])
                    del self._rx[:need]
                    self._log(f"   raw[{len(raw)}] {raw.hex(' ')}")
                    r = parse_frame(raw, self.session_key)
                    self._log(f"<< cmd={r['cmd']:02X} p1={r['p1']} enc={int(r['encrypted'])} data[{len(r['data'])}]={r['data'].hex(' ')}")
                    return r
            self._rx += bytes(self.dev.read(EP_IN, 4096, timeout=timeout))

    def cmd(self, cmd, p1=0, data=b"", encrypt=False, timeout=2000):
        """Send and wait for the reply frame with the same cmd/p1."""
        self.send(cmd, p1, data, encrypt)
        t0 = time.monotonic()
        while True:
            r = self.recv(timeout)
            if r["cmd"] == cmd and r["p1"] == p1:
                return r["data"]
            self._log(f"!! unexpected frame cmd={r['cmd']:02X} p1={r['p1']} while waiting for {cmd:02X}/{p1}")
            if time.monotonic() - t0 > timeout / 1000:
                raise BtlError("timeout waiting for reply")

    # --- read-only queries -----------------------------------------------------------
    def fw_version(self):
        d = self.cmd(0xA0)
        if len(d) < 7:
            raise BtlError(f"short A0 reply {d.hex()}")
        return dict(crypto=d[0], project=PROJECT.get(d[1], f"unknown {d[1]}/{d[2]}"),
                    project_code=(d[1], d[2]), version=d[3:7].hex("."), raw=d.hex(" "))

    def scheme(self):
        d = self.cmd(0xA1)
        return dict(flag=d[0], asym=d[1], sym=d[2], hash=d[3], raw=d.hex(" "))

    def key_exchange(self):
        priv, pub = bc.sm2_keygen()
        d = self.cmd(0xA2, 0, pub)
        if len(d) < 0x71:
            raise BtlError(f"short A2 reply ({len(d)} bytes): {d.hex(' ')}")
        self.session_key = bc.sm2_decrypt_c1c3c2(priv, d[:0x71])
        self._log(f"   session key established ({len(self.session_key)} bytes)")
        return len(d)

    def module_uid(self):
        return self.cmd(0xC0, encrypt=True)

    def sensor_info(self):
        d = self.cmd(0xC1, encrypt=True)
        chip, a, b = struct.unpack_from("<IHH", d, 0)
        return dict(chip_id=d[0:4].hex(), w1=a, w2=b, tech=d[8], raw=d.hex(" "))

    def fp_count(self):
        d = self.cmd(0xB3, encrypt=True)
        a, b = struct.unpack_from("<HH", d, 0)
        return dict(count=a, max=b, raw=d.hex(" "))

    def init(self):
        # A0 is a read-only single-packet frame, so it doubles as a data-toggle resync: if the
        # module dropped it (toggle mismatch), the retry goes out with the other toggle.
        for attempt in range(3):
            try:
                info = self.fw_version_quick()
                break
            except usb.core.USBTimeoutError:
                self._log(f"!! A0 attempt {attempt + 1} got no reply (toggle resync)")
            except IndexError:
                self._log(f"!! A0 attempt {attempt + 1} got an empty reply (module busy?)")
                time.sleep(0.3)
        else:
            raise BtlError("module does not answer A0")
        sch = self.scheme()
        self.key_exchange()
        return info, sch

    def fw_version_quick(self):
        self.send(0xA0)
        d = self.recv(timeout=700)["data"]
        return dict(crypto=d[0], project_code=(d[1], d[2]), version=d[3:7].hex("."), raw=d.hex(" "))

    def _unused_init(self):
        info = self.fw_version()
        sch = self.scheme()
        self.key_exchange()
        return info, sch

    # --- identify --------------------------------------------------------------------
    def identify(self, timeout=15.0):
        """Start identify, then wait for the asynchronous result.
        Returns (status, template_id, tag16)."""
        ack = self.cmd(0xB1, 0, encrypt=True)
        self._log(f"   identify ack: {ack.hex(' ')}")
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                r = self.recv(timeout=500)
            except usb.core.USBTimeoutError:
                continue
            if r["cmd"] == 0xB1 and r["p1"] == 0 and r["data"]:
                d = r["data"]
                st = d[0]
                tid = struct.unpack_from("<H", d, 1)[0] if len(d) >= 3 else None
                return st, tid, d[3:19]
        self.cmd(0xB1, 1, encrypt=True)  # cancel
        return None

    # --- enroll (writes a template to module flash) -----------------------------------
    def enroll_start(self):
        d = self.cmd(0xB0, 0, b"\x00", encrypt=True)
        return d

    def enroll_touch(self, index, timeout=20.0):
        """index = 1-based number of this touch (Windows: SET_CUR_ENROLLED_TIMES counter,
        incremented after every accepted touch). Returns (status, flag) once processed."""
        if not 1 <= index <= 255:
            raise ValueError("touch index must be 1..255")
        ack = self.cmd(0xB0, 1, bytes([index]), encrypt=True)
        if ack:  # immediate result without separate ack
            return ack[0], ack[1] if len(ack) > 1 else None
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                r = self.recv(timeout=500)
            except usb.core.USBTimeoutError:
                continue
            if r["cmd"] == 0xB0 and r["p1"] == 1 and r["data"]:
                return r["data"][0], r["data"][1] if len(r["data"]) > 1 else None
        return None

    def enroll_finish(self, identity32: bytes):
        d = self.cmd(0xB0, 2, identity32.ljust(32, b"\0")[:32], encrypt=True, timeout=8000)
        return d

    def enroll_cancel(self):
        return self.cmd(0xB0, 3, b"\x00", encrypt=True)


if __name__ == "__main__":
    b = Btl(debug="-v" in sys.argv)
    try:
        info, sch = b.init()
        print("firmware:", info)
        print("scheme:  ", sch)
        print("uid:     ", b.module_uid().hex(" "))
        print("sensor:  ", b.sensor_info())
        print("count:   ", b.fp_count())
    finally:
        b.close()
