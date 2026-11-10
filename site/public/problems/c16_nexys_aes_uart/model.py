"""P16-1 model: AES-128 requests (key then plaintext, 32 bytes) and the replies the board must send (standalone: python only)."""
import hashlib
import math
import random
import struct


def xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a


def gmul(a: int, b: int) -> int:
    """Multiplication in GF(2^8) modulo x^8 + x^4 + x^3 + x + 1."""
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = xtime(a)
        b >>= 1
    return r


def _build_sbox():
    inv = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if gmul(a, b) == 1:
                inv[a] = b
                break
    sb = []
    for a in range(256):
        x = inv[a]
        y = x
        for s in (1, 2, 3, 4):
            y ^= ((x << s) | (x >> (8 - s))) & 0xFF
        sb.append(y ^ 0x63)
    return sb


SBOX = _build_sbox()


RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def expand_key(key: bytes) -> list[bytes]:
    """The 11 round keys of AES-128 (16 bytes each)."""
    w = [list(key[4 * i:4 * i + 4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i // 4 - 1]
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [bytes(sum(w[4 * r:4 * r + 4], [])) for r in range(11)]


def _shift_rows(s):
    return [s[4 * ((c + r) % 4) + r] for c in range(4) for r in range(4)]


def _mix_columns(s):
    out = []
    for c in range(4):
        a = s[4 * c:4 * c + 4]
        out += [gmul(a[0], 2) ^ gmul(a[1], 3) ^ a[2] ^ a[3], a[0] ^ gmul(a[1], 2) ^ gmul(a[2], 3) ^ a[3],
                a[0] ^ a[1] ^ gmul(a[2], 2) ^ gmul(a[3], 3), gmul(a[0], 3) ^ a[1] ^ a[2] ^ gmul(a[3], 2)]
    return out


def aes128_encrypt(key: bytes, block: bytes, trace: list | None = None) -> bytes:
    """AES-128 encryption of one block. `trace`, if given, receives the state after every round."""
    rk = expand_key(key)
    s = [a ^ b for a, b in zip(block, rk[0])]
    if trace is not None:
        trace.append(bytes(s))
    for r in range(1, 11):
        s = [SBOX[b] for b in s]
        s = _shift_rows(s)
        if r != 10:
            s = _mix_columns(s)
        s = [a ^ b for a, b in zip(s, rk[r])]
        if trace is not None:
            trace.append(bytes(s))
    return bytes(s)


def requests():
    kats = [("2b7e151628aed2a6abf7158809cf4f3c" + "3243f6a8885a308d313198a2e0370734"), ("000102030405060708090a0b0c0d0e0f" + "00112233445566778899aabbccddeeff")]   # FIPS 197 appendix B and C.1
    rng = random.Random(16)
    return kats + [rng.randbytes(32).hex() for _ in range(6)]


def reply_for(req_hex):
    b = bytes.fromhex(req_hex)
    return aes128_encrypt(b[:16], b[16:]).hex()


def reference_output():
    return {"cases": [{"request": r, "reply": reply_for(r)} for r in requests()]}


# ---- benchmark wrapper (from spec.yaml) ----
DESIGN_ID = None


def bench_requests():
    return [(r, reply_for(r)) for r in requests()]
