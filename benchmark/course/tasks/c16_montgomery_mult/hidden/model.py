"""P16-4 model: 64-bit Montgomery products a * b * 2^-64 mod n (standalone: python only)."""
import hashlib
import math
import random
import struct


def mont_mul(a, b, n, w=64):
    return a * b * pow(1 << w, -1, n) % n


def cases():
    rng = random.Random(19)
    out = []
    for t in range(40):
        n = rng.getrandbits(64) | (1 << 63) | 1 if t % 4 else rng.getrandbits(40) | (1 << 39) | 1
        out.append((rng.randrange(n), rng.randrange(n), n))
    n = (1 << 64) - 59                                                            # a 64-bit prime
    out += [(0, 5, n), (1, n - 1, n), (n - 1, n - 1, n), (n - 1, 1, n)]
    return out


def reference_output():
    return {"cases": [{"a": a, "b": b, "n": n, "r": mont_mul(a, b, n), "clocks": 66} for a, b, n in cases()]}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x4D4F4E54          # "MONT"
A_LO, A_HI, B_LO, B_HI, N_LO, N_HI, START, STATUS, R_LO, R_HI, CLOCKS = range(11)


def bench_cases():
    """First 14 course products (mixed 64/40-bit moduli), the four edge cases, and a 64-bit prime modulus case or two."""
    c = cases()
    return c[:14] + c[40:44] + [c[20], c[27], c[33]]
