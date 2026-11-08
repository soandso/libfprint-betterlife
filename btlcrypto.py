"""Pure-Python SM2 / SM3 / SM4 (GM/T 0003/0004/0002), just enough for the Betterlife link layer.

The Windows driver (BetterlifeFingerprintDevice.dll, gmssl-based) does:
  * host generates an SM2 key pair, sends the 65-byte public key (04||X||Y) with CMD 0xA2;
  * module answers with the 16-byte session key SM2-encrypted to that key:
        04 || C1.x || C1.y || C3 (SM3, 32 B) || C2 (16 B)          ("C1C3C2" order)
  * every encrypted frame carries a random 16-byte IV; the per-message key is
        K_msg = SM4_encrypt(session_key, IV)
    and the body is SM4-ECB encrypted with K_msg.
Speed is irrelevant here (a handful of blocks per command).
"""
import os
import struct

# ---------------------------------------------------------------- SM3
_IV = [0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600,
       0xA96F30BC, 0x163138AA, 0xE38DEE4D, 0xB0FB0E4E]


def _rotl(x, n):
    n %= 32
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _p0(x):
    return x ^ _rotl(x, 9) ^ _rotl(x, 17)


def _p1(x):
    return x ^ _rotl(x, 15) ^ _rotl(x, 23)


def sm3(msg: bytes) -> bytes:
    ml = len(msg) * 8
    msg = msg + b"\x80" + b"\x00" * ((55 - len(msg)) % 64) + struct.pack(">Q", ml)
    v = list(_IV)
    for off in range(0, len(msg), 64):
        w = list(struct.unpack(">16I", msg[off:off + 64]))
        for j in range(16, 68):
            w.append(_p1(w[j - 16] ^ w[j - 9] ^ _rotl(w[j - 3], 15)) ^ _rotl(w[j - 13], 7) ^ w[j - 6])
        w1 = [w[j] ^ w[j + 4] for j in range(64)]
        a, b, c, d, e, f, g, h = v
        for j in range(64):
            t = 0x79CC4519 if j < 16 else 0x7A879D8A
            ss1 = _rotl((_rotl(a, 12) + e + _rotl(t, j)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ _rotl(a, 12)
            if j < 16:
                ff, gg = a ^ b ^ c, e ^ f ^ g
            else:
                ff = (a & b) | (a & c) | (b & c)
                gg = (e & f) | (~e & g)
            tt1 = (ff + d + ss2 + w1[j]) & 0xFFFFFFFF
            tt2 = (gg + h + ss1 + w[j]) & 0xFFFFFFFF
            d, c, b, a = c, _rotl(b, 9), a, tt1
            h, g, f, e = g, _rotl(f, 19), e, _p0(tt2)
        v = [x ^ y for x, y in zip(v, (a, b, c, d, e, f, g, h))]
    return struct.pack(">8I", *v)


# ---------------------------------------------------------------- SM4
_SBOX = bytes.fromhex(
    "d690e9fecce13db716b614c228fb2c052b679a762abe04c3aa441326498606999c4250f491ef987a33540b43edcfac62"
    "e4b31ca9c908e89580df94fa758f3fa64707a7fcf37317ba83593c19e6854fa8686b81b27164da8bf8eb0f4b70569d35"
    "1e240e5e6358d1a225227c3b01217887d40046579fd327524c3602e7a0c4c89eeabf8ad240c738b5a3f7f2cef96115a1"
    "e0ae5da49b341a55ad933230f58cb1e31df6e22e8266ca60c02923ab0d534e6fd5db3745defd8e2f03ff6a726d6c5b51"
    "8d1baf92bbddbc7f11d95c411f105ad80ac13188a5cd7bbd2d74d012b8e5b4b08969974a0c96777e65b9f109c56ec684"
    "18f07dec3adc4d2079ee5f3ed7cb3948")
_FK = (0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC)
_CK = [((4 * i) * 7 % 256) << 24 | ((4 * i + 1) * 7 % 256) << 16 | ((4 * i + 2) * 7 % 256) << 8
       | ((4 * i + 3) * 7 % 256) for i in range(32)]


def _tau(a):
    return (_SBOX[a >> 24] << 24) | (_SBOX[(a >> 16) & 0xFF] << 16) | (_SBOX[(a >> 8) & 0xFF] << 8) | _SBOX[a & 0xFF]


def _sm4_rk(key: bytes):
    k = [x ^ f for x, f in zip(struct.unpack(">4I", key), _FK)]
    rk = []
    for i in range(32):
        b = _tau(k[1] ^ k[2] ^ k[3] ^ _CK[i])
        n = k[0] ^ b ^ _rotl(b, 13) ^ _rotl(b, 23)
        rk.append(n)
        k = k[1:] + [n]
    return rk


def _sm4_block(rk, block: bytes) -> bytes:
    x = list(struct.unpack(">4I", block))
    for r in rk:
        b = _tau(x[1] ^ x[2] ^ x[3] ^ r)
        x = x[1:] + [x[0] ^ b ^ _rotl(b, 2) ^ _rotl(b, 10) ^ _rotl(b, 18) ^ _rotl(b, 24)]
    return struct.pack(">4I", x[3], x[2], x[1], x[0])


def sm4_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    assert len(key) == 16 and len(data) % 16 == 0
    rk = _sm4_rk(key)
    return b"".join(_sm4_block(rk, data[i:i + 16]) for i in range(0, len(data), 16))


def sm4_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    assert len(key) == 16 and len(data) % 16 == 0
    rk = _sm4_rk(key)[::-1]
    return b"".join(_sm4_block(rk, data[i:i + 16]) for i in range(0, len(data), 16))


# ---------------------------------------------------------------- SM2 (sm2p256v1)
P = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF
A = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC
B = 0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93
N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
G = (0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7,
     0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0)


def _on_curve(pt):
    x, y = pt
    return (y * y - (x * x * x + A * x + B)) % P == 0


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return x3, (lam * (x1 - x3) - y1) % P


def _mul(k, pt):
    r = None
    while k:
        if k & 1:
            r = _add(r, pt)
        pt = _add(pt, pt)
        k >>= 1
    return r


def _i2b(i):
    return i.to_bytes(32, "big")


def _kdf(z: bytes, klen: int) -> bytes:
    out, ct = b"", 1
    while len(out) < klen:
        out += sm3(z + struct.pack(">I", ct))
        ct += 1
    return out[:klen]


def sm2_keygen():
    """Returns (private int, 65-byte uncompressed public key 04||X||Y)."""
    d = int.from_bytes(os.urandom(32), "big") % (N - 2) + 1
    x, y = _mul(d, G)
    return d, b"\x04" + _i2b(x) + _i2b(y)


def sm2_encrypt_c1c3c2(pub65: bytes, msg: bytes) -> bytes:
    """Only used by the self-test (the module does this side)."""
    pb = (int.from_bytes(pub65[1:33], "big"), int.from_bytes(pub65[33:65], "big"))
    k = int.from_bytes(os.urandom(32), "big") % (N - 2) + 1
    x1, y1 = _mul(k, G)
    x2, y2 = _mul(k, pb)
    t = _kdf(_i2b(x2) + _i2b(y2), len(msg))
    c2 = bytes(a ^ b for a, b in zip(msg, t))
    c3 = sm3(_i2b(x2) + msg + _i2b(y2))
    return b"\x04" + _i2b(x1) + _i2b(y1) + c3 + c2


def sm2_decrypt_c1c3c2(d: int, ct: bytes) -> bytes:
    """ct = 04 || x1 || y1 || C3(32) || C2. Raises ValueError if C3 doesn't verify."""
    if ct[0] != 0x04 or len(ct) < 97:
        raise ValueError("bad SM2 ciphertext")
    c1 = (int.from_bytes(ct[1:33], "big"), int.from_bytes(ct[33:65], "big"))
    if not _on_curve(c1):
        raise ValueError("C1 not on curve")
    c3, c2 = ct[65:97], ct[97:]
    x2, y2 = _mul(d, c1)
    t = _kdf(_i2b(x2) + _i2b(y2), len(c2))
    if not any(t):
        raise ValueError("KDF output all zero")
    m = bytes(a ^ b for a, b in zip(c2, t))
    if sm3(_i2b(x2) + m + _i2b(y2)) != c3:
        raise ValueError("SM2 C3 check failed")
    return m


# ---------------------------------------------------------------- link layer helpers
def msg_key(session_key: bytes, iv: bytes) -> bytes:
    return sm4_ecb_encrypt(session_key, iv)


def selftest():
    assert sm3(b"abc").hex() == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    k = bytes.fromhex("0123456789abcdeffedcba9876543210")
    assert sm4_ecb_encrypt(k, k).hex() == "681edf34d206965e86b3e94f536e4246"
    assert sm4_ecb_decrypt(k, bytes.fromhex("681edf34d206965e86b3e94f536e4246")) == k
    d, pub = sm2_keygen()
    assert _on_curve((int.from_bytes(pub[1:33], "big"), int.from_bytes(pub[33:], "big")))
    m = os.urandom(16)
    assert sm2_decrypt_c1c3c2(d, sm2_encrypt_c1c3c2(pub, m)) == m
    return True


if __name__ == "__main__":
    print("selftest:", selftest())
