"""The square-root model against Python integer arithmetic (brief 139b): exhaustive small widths, random large ones; no simulator needed."""
from __future__ import annotations

import math
import random

from arith.isqrt import model as M


def test_isqrt_exhaustive_small_widths() -> None:
    for w in range(3, 15):
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


def test_restoring_recurrence_equals_isqrt() -> None:
    for w in range(3, 13):
        for x in range(1 << w):
            t = M.restoring_trace(x, w)                   # the trace asserts the widths the RTL relies on
            assert (t[-1][1], t[-1][0]) == M.isqrt(x, w) and len(t) == M.rw(w)


def test_nonrestoring_recurrence_equals_isqrt_and_keeps_its_range() -> None:
    """The remainder stays in [-(2q+1), 2q] after every step (q the root so far): RW + 2 signed bits, the width the RTL keeps."""
    for w in range(3, 13):
        for x in range(1 << w):
            tr, res = M.nonrestoring_trace(x, w)
            assert res == M.isqrt(x, w)
            for k, (rem, q) in enumerate(tr, start=1):
                assert -(2 * q + 1) <= rem <= 2 * q and q < 1 << k and -(1 << (k + 1)) <= rem < 1 << (k + 1)


def test_latency_formulas() -> None:
    assert [M.latency(0, w) for w in (3, 4, 16, 17)] == [3, 3, 9, 10]
    assert [M.latency(1, 16, p) for p in (1, 2, 3, 8, 9)] == [8, 4, 3, 1, 1]
    assert [M.latency(2, 15, p) for p in (1, 2, 3, 8)] == [8, 4, 3, 1]
