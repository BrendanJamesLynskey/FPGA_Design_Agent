"""Bit-exact model of the leading-zero count and normaliser (brief 139b), written from spec.md alone.

Input x, unsigned W bits (W >= 2). Outputs: lz = the number of leading zero bits (W when x = 0), and y = x << lz truncated to W bits, so
that y has its MSB set for every non-zero x (y = 0 for x = 0). ``stagewise`` is the log-shifter recurrence the stagewise variants implement,
on x zero-extended at the LSB side to P = 2**ceil(log2 W) bits.
"""
from __future__ import annotations

import random

VARIANTS = {0: "tree_barrel", 1: "loop_barrel", 2: "stagewise_pipe", 3: "tree_barrel_2st"}


def k_stages(w: int) -> int:
    return (w - 1).bit_length()                         # ceil(log2 W) for W >= 2


def lw(w: int) -> int:
    return w.bit_length()                               # bits to hold 0..W


def lzc_norm(x: int, w: int) -> tuple[int, int]:
    assert w >= 2 and 0 <= x < 1 << w
    lz = w - x.bit_length()
    return lz, (x << lz) & ((1 << w) - 1)


def stagewise(x: int, w: int) -> tuple[int, int, int]:
    """(stage bits as an integer, v, P): v is the padded value after the K stages. The stage with step 2**k shifts when the top 2**k bits of v are zero."""
    k, p = k_stages(w), 1 << k_stages(w)
    v, bits = x << (p - w), 0
    for s in range(k - 1, -1, -1):
        step = 1 << s
        if (v >> (p - step)) == 0:
            v = (v << step) & ((1 << p) - 1)
            bits |= step
    return bits, v, p


def latency(variant: int, w: int, pipe: int = 1) -> int:
    if variant in (0, 1):
        return 1
    if variant == 3:
        return 2
    return -(-k_stages(w) // pipe)


def edge_values(w: int) -> list[int]:
    m = (1 << w) - 1
    s = {0, 1, 2, 3, m, m >> 1, (m >> 1) + 1}
    s |= {1 << i for i in range(w)} | {(1 << i) - 1 for i in range(1, w + 1)} | {(1 << i) + 1 for i in range(w)}
    return sorted(v for v in s if 0 <= v <= m)


def inputs(w: int, count: int | None = None, seed: int = 1) -> list[int]:
    if count is None:
        return list(range(1 << w))
    rng = random.Random(seed)
    out = edge_values(w)
    while len(out) < count:
        out.append(rng.getrandbits(rng.randint(0, w)))        # every leading-zero count is common
    return out[:count]


def stream(w: int, count: int | None = None, seed: int = 1) -> tuple[list[int], list[int]]:
    xs = inputs(w, count, seed)
    return xs, [(lzc_norm(x, w)[0] << w) | lzc_norm(x, w)[1] for x in xs]      # out_data = {lz, y}
