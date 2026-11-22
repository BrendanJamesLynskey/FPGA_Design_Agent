"""Bit-exact model of the integer square root (brief 139b), written from spec.md alone.

``isqrt``: x unsigned W bits (W >= 3) -> root = floor(sqrt(x)) in RW = ceil(W / 2) bits and rem = x - root**2 in RW + 1 bits.
``restoring_trace`` and ``nonrestoring_trace`` are the digit recurrences the RTL variants implement, one bit pair per step (the top pair first;
an odd W is zero-extended to 2 * RW bits), with the register widths of the RTL so the intermediate ranges are checked.
"""
from __future__ import annotations

import math
import random

VARIANTS = {0: "restoring_iter", 1: "restoring_pipe", 2: "nonrestoring_pipe"}


def rw(w: int) -> int:
    return (w + 1) // 2


def isqrt(x: int, w: int) -> tuple[int, int]:
    assert w >= 3 and 0 <= x < 1 << w
    r = math.isqrt(x)
    return r, x - r * r


def restoring_trace(x: int, w: int) -> list[tuple[int, int]]:
    """(rem, root) after each of the RW steps. The shifted remainder 4*rem + pair and the trial 4*root + 1 are checked to fit RW + 2 bits."""
    n, rem, root, out = rw(w), 0, 0, []
    for i in range(n - 1, -1, -1):
        sh = (rem << 2) | ((x >> (2 * i)) & 3)
        trial = (root << 2) | 1
        assert sh < 1 << (n + 2) and trial < 1 << (n + 2)
        if sh >= trial:
            rem, root = sh - trial, (root << 1) | 1
        else:
            rem, root = sh, root << 1
        out.append((rem, root))
    return out


def nonrestoring_trace(x: int, w: int) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """(signed rem, root) after each step, then the corrected (root, rem). rem is checked to fit RW + 3 signed bits."""
    n, rem, root, out = rw(w), 0, 0, []
    for i in range(n - 1, -1, -1):
        sh = (rem << 2) | ((x >> (2 * i)) & 3)
        rem = sh - ((root << 2) | 1) if rem >= 0 else sh + ((root << 2) | 3)
        root = (root << 1) | (1 if rem >= 0 else 0)
        assert -(1 << (n + 2)) <= rem < 1 << (n + 2)
        out.append((rem, root))
    if rem < 0:
        rem += (root << 1) | 1
    return out, (root, rem)


def latency(variant: int, w: int, pipe: int = 1) -> int:
    n = rw(w)
    return n + 1 if variant == 0 else -(-n // pipe)


def throughput_clocks(variant: int, w: int) -> int:
    return rw(w) + 1 if variant == 0 else 1


def edge_values(w: int) -> list[int]:
    m = (1 << w) - 1
    s = {0, 1, 2, 3, 4, 5, 8, 9, m, m - 1, m >> 1}
    for r in (2, 3, 5, (1 << ((w + 1) // 2)) - 1):
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
