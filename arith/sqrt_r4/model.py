"""Bit-exact model of the radix-4 integer square root (brief 139c), written from spec.md alone.

``isqrt``: x unsigned W bits (W >= 5) -> root = floor(sqrt(x)) in RW = ceil(W / 2) bits and rem = x - root**2 in RW + 1 bits (the same
function as arith/isqrt). ``r4_trace`` is the digit recurrence the RTL variants implement: one radix-4 digit (two root bits) per step from four
radicand bits, the digit chosen by three trial subtractions in parallel; the register widths are those of the RTL and are asserted.
"""
from __future__ import annotations

import math
import random

VARIANTS = {0: "iter", 1: "pipe"}


def rw(w: int) -> int:
    return (w + 1) // 2


def steps(w: int) -> int:
    """Radix-4 digit steps: RP = ceil(RW / 2). The internal root is QW = 2 * RP bits (the top bit is zero when RW is odd)."""
    return (rw(w) + 1) // 2


def isqrt(x: int, w: int) -> tuple[int, int]:
    assert w >= 5 and 0 <= x < 1 << w
    r = math.isqrt(x)
    return r, x - r * r


def r4_trace(x: int, w: int) -> tuple[list[tuple[int, int, int]], tuple[int, int]]:
    """([(digit, rem, root) after each step], (root, rem)). Before step j (0-based) the root q is below 4**j and rem <= 2q, so
    sh = 16 rem + nibble is below 2**(2j+5), at most QW + 3 bits, and every trial value (8q+1, 16q+4, 24q+9) fits there too."""
    n = steps(w)
    qw = 2 * n
    r = q = 0
    out = []
    xe = x                                                  # zero-extended to 4n bits
    for j in range(n):
        nib = (xe >> (4 * (n - 1 - j))) & 15
        sh = (r << 4) | nib
        t = (8 * q + 1, 16 * q + 4, 24 * q + 9)
        assert sh < 1 << (2 * j + 5) and sh < 1 << (qw + 3) and t[2] < 1 << (qw + 3) and q < 1 << (2 * j)
        d = 3 if sh >= t[2] else 2 if sh >= t[1] else 1 if sh >= t[0] else 0
        if d:
            sh -= t[d - 1]
        r, q = sh, 4 * q + d
        assert r <= 2 * q and q < 1 << (2 * (j + 1)) and r < 1 << (2 * (j + 1) + 1)
        out.append((d, r, q))
    return out, (q, r)


def latency(variant: int, w: int, pipe: int = 1) -> int:
    n = steps(w)
    return n + 1 if variant == 0 else -(-n // pipe)


def throughput_clocks(variant: int, w: int) -> int:
    return steps(w) + 1 if variant == 0 else 1


def edge_values(w: int) -> list[int]:
    m = (1 << w) - 1
    s = {0, 1, 2, 3, 4, 5, 8, 9, 15, 16, 17, m, m - 1, m >> 1}
    for r in (2, 3, 5, 15, 16, (1 << ((w + 1) // 2)) - 1):
        for d in (-1, 0, 1):
            v = r * r + d
            if 0 <= v <= m:
                s.add(v)
    return sorted(s)


def inputs(w: int, count: int | None = None, seed: int = 1) -> list[int]:
    if count is None:
        return list(range(1 << w))
    rng = random.Random(seed)
    out = edge_values(w)
    while len(out) < count:
        if rng.random() < 0.4:                                         # near a perfect square: remainder 0 and 2*root
            r = rng.getrandbits(rw(w))
            v = r * r + rng.choice((-1, 0, 0, 1, 2 * r, 2 * r + 1))
            out.append(min(max(v, 0), (1 << w) - 1))
        else:
            out.append(rng.getrandbits(w))
    return out[:count]


def stream(w: int, count: int | None = None, seed: int = 1) -> tuple[list[int], list[int]]:
    xs = inputs(w, count, seed)
    n = rw(w)
    return xs, [(isqrt(x, w)[0] << (n + 1)) | isqrt(x, w)[1] for x in xs]     # out_data = {root, rem}
