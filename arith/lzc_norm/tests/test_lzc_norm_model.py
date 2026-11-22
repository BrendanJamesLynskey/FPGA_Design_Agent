"""The leading-zero count and normaliser model against Python integer arithmetic (brief 139b); no simulator needed."""
from __future__ import annotations

import random

from arith.lzc_norm import model as M


def test_lzc_norm_exhaustive_small_widths() -> None:
    for w in range(2, 15):
        for x in range(1 << w):
            lz, y = M.lzc_norm(x, w)
            assert lz == len(format(x, f"0{w}b")) - len(format(x, "b")) if x else lz == w
            assert y == (x * (1 << lz)) % (1 << w) and (x == 0 or y >> (w - 1) == 1) and lz < 1 << M.lw(w)


def test_lzc_norm_random_large_widths() -> None:
    rng = random.Random(9)
    for w in (16, 31, 32, 48, 64, 100, 256):
        for _ in range(2000):
            x = rng.getrandbits(rng.randint(0, w))
            lz, y = M.lzc_norm(x, w)
            assert lz == (w if x == 0 else w - x.bit_length()) and (y >> (w - 1) == 1 if x else y == 0)


def test_stagewise_recurrence_equals_the_function() -> None:
    """The log-shifter recurrence (what the stagewise variants build): its stage bits are the count and its padded word holds the normalised value."""
    for w in range(2, 15):
        for x in range(1 << w):
            bits, v, p = M.stagewise(x, w)
            nz = (v >> (p - 1)) & 1
            assert nz == (1 if x else 0)
            lz, y = M.lzc_norm(x, w)
            assert (bits if nz else w) == lz and v >> (p - w) == y


def test_latency_formulas() -> None:
    assert [M.latency(v, 16) for v in (0, 1, 3)] == [1, 1, 2]
    assert [M.latency(2, 16, p) for p in (1, 2, 3, 4, 5)] == [4, 2, 2, 1, 1]
    assert [M.latency(2, 17, p) for p in (1, 2, 5)] == [5, 3, 1]
