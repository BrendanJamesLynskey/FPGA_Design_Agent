"""The divider model against Python integer arithmetic (brief 139b): exhaustive small widths, random large ones; no simulator needed."""
from __future__ import annotations

import random

from arith.divider import model as M


def test_divide_exhaustive_small_widths() -> None:
    for w in range(1, 9):
        for n in range(1 << w):
            for d in range(1, 1 << w):
                assert M.divide(n, d, w) == (n // d, n % d)


def test_divide_by_zero_convention() -> None:
    for w in (1, 2, 8, 33, 64):
        for n in (0, 1, (1 << w) - 1):
            assert M.divide(n, 0, w) == ((1 << w) - 1, n)


def test_divide_random_large_widths() -> None:
    rng = random.Random(7)
    for w in (16, 24, 32, 48, 64, 96, 128):
        for _ in range(2000):
            n, d = rng.getrandbits(w), rng.getrandbits(rng.randint(1, w))
            q, r = M.divide(n, d, w)
            if d:
                assert (q, r) == (n // d, n % d) and q * d + r == n and r < d
            else:
                assert (q, r) == ((1 << w) - 1, n)


def test_restoring_recurrence_equals_division() -> None:
    for w in range(2, 9):
        for n, d in M.vectors(w):
            t = M.restoring_trace(n, d, w)
            assert len(t) == w and (t[-1][1], t[-1][0]) == M.divide(n, d, w)
            assert all(p < (1 << w) for p, _ in t)           # the partial remainder always fits W bits (the trace also asserts the shifted value does)


def test_nonrestoring_recurrence_equals_division_and_keeps_its_range() -> None:
    for w in range(2, 9):
        for n, d in M.vectors(w):
            tr, qr = M.nonrestoring_trace(n, d, w)          # the trace asserts the W+1 signed-bit range itself
            assert qr == M.divide(n, d, w) and len(tr) == w


def test_latency_formulas() -> None:
    assert [M.latency(0, w) for w in (4, 8, 32)] == [5, 9, 33]
    assert [M.latency(1, w) for w in (4, 8, 32)] == [6, 10, 34]
    assert [M.latency(2, 8, p) for p in (1, 2, 3, 8, 9)] == [8, 4, 3, 1, 1]
    assert [M.latency(3, 7, p) for p in (1, 2, 3, 7)] == [7, 4, 3, 1]
    assert M.throughput_clocks(0, 8) == 9 and M.throughput_clocks(2, 8) == 1
