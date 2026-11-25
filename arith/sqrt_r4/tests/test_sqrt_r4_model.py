"""The radix-4 square-root model against Python integer arithmetic (brief 139c): exhaustive small widths, random large ones; no simulator needed."""
from __future__ import annotations

import math
import random

from arith.isqrt import model as I
from arith.sqrt_r4 import model as M


def test_isqrt_exhaustive_small_widths() -> None:
    for w in range(5, 15):
        for x in range(1 << w):
            r, rem = M.isqrt(x, w)
            assert r * r <= x < (r + 1) * (r + 1) and rem == x - r * r and r < 1 << M.rw(w) and rem < 1 << (M.rw(w) + 1)


def test_isqrt_random_large_widths() -> None:
    rng = random.Random(3)
    for w in (16, 31, 32, 48, 64, 96, 128, 200):
        for _ in range(2000):
            x = rng.getrandbits(w)
            r, rem = M.isqrt(x, w)
            assert r == math.isqrt(x) and rem == x - r * r and 0 <= rem <= 2 * r


def test_same_function_as_the_radix_2_square_root() -> None:
    """arith/isqrt (brief 139b) and this function are the same mathematical function at every width: same values, same packing."""
    for w in range(5, 13):
        assert M.stream(w) == I.stream(w)
    for w in (40, 64):
        for x in M.inputs(w, 300, 7):
            assert M.isqrt(x, w) == I.isqrt(x, w)


def test_radix4_recurrence_equals_isqrt_and_keeps_its_range() -> None:
    """The trace asserts the register widths the RTL relies on (sh below 2**(QW+3), trial values below it, rem <= 2q) at every step."""
    for w in range(5, 15):
        for x in range(1 << w):
            t, res = M.r4_trace(x, w)
            assert res == M.isqrt(x, w) and len(t) == M.steps(w)


def test_radix4_recurrence_large_widths() -> None:
    rng = random.Random(11)
    for w in (31, 32, 48, 64, 100):
        for x in M.inputs(w, 1500, 5) + [rng.getrandbits(w) for _ in range(500)]:
            assert M.r4_trace(x, w)[1] == M.isqrt(x, w)


def test_latency_formulas() -> None:
    assert [M.latency(0, w) for w in (5, 8, 16, 17, 32)] == [3, 3, 5, 6, 9]
    assert [M.latency(1, 32, p) for p in (1, 2, 3, 8, 9)] == [8, 4, 3, 1, 1]
    assert [M.steps(w) for w in (5, 6, 7, 8, 9, 16, 32)] == [2, 2, 2, 2, 3, 4, 8]
