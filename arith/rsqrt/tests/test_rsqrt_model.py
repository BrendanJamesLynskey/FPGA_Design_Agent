"""The reciprocal square-root model against exact arithmetic (brief 139c): the error bound of every variant over every input at small widths and over sampled
inputs at large ones, the residual word width, the seed table; no simulator needed."""
from __future__ import annotations

import random
from fractions import Fraction

from arith.rsqrt import model as M


def bound(w: int, a: int, variant: int) -> tuple[Fraction, Fraction]:
    """(lower, upper), units of the last place, open at both ends for the Newton variants: table |e| <= 2**(W-A-2) + 1; one Newton step -1/4 < e < 2**(W-2A-3) + 3/2;
    two steps -1/4 < e < 2**(W-4A-7) + 3/2. (The exact-arithmetic Newton map never overshoots; the small negative side is the truncation of the residual and of the shifts.)"""
    if variant == 0:
        e = Fraction(2) ** (w - a - 2) + 1
        return -e, e
    p = 2 * a + 3 if variant == 1 else 4 * a + 7
    return Fraction(-1, 4), Fraction(2) ** (w - p) + Fraction(3, 2)


def check(w: int, a: int, variant: int, vals=None) -> None:
    lo, hi = M.error_range(w, a, variant, vals)
    blo, bhi = bound(w, a, variant)
    ok = (blo <= lo and hi <= bhi) if variant == 0 else (blo < lo and hi < bhi)
    assert ok, (w, a, variant, float(lo), float(hi), float(blo), float(bhi))


def test_error_bounds_every_input_at_small_widths() -> None:
    """Every x at W = 8 to 12 for every A from 2 to W - 3 (every variant): the bound holds and the residual word never overflows (asserted inside rsqrt)."""
    for w in range(8, 13):
        for a in range(2, w - 2):
            for v in M.VARIANTS:
                check(w, a, v)


def test_error_bounds_wide_widths_sampled() -> None:
    rng = random.Random(6)
    for w, a in ((16, 7), (16, 8), (16, 4), (18, 7), (20, 8), (24, 9), (24, 6), (32, 10)):
        vals = M.inputs(w, a, 6000, seed_=w) + [rng.randrange(1 << (w - 2), 1 << w) for _ in range(2000)]
        for v in M.VARIANTS:
            check(w, a, v, vals)


def test_every_input_at_w14_and_w16() -> None:
    for w, a in ((14, 6), (16, 7)):
        for v in M.VARIANTS:
            check(w, a, v)


def test_output_range_and_the_value_at_x_equal_one() -> None:
    """Y is in about [2**(W-1) - 2**(W-A), 2**W]; the value 2**W only at the bottom of the input range (X = 1)."""
    for w, a in ((8, 3), (12, 5), (16, 7)):
        for v in M.VARIANTS:
            for x in M.values(w):
                y = M.rsqrt(x, w, a, v)
                assert (1 << (w - 1)) - (1 << (w - a)) <= y <= 1 << w
                if y == 1 << w:
                    assert x < (1 << (w - 2)) + (1 << (w - 2 - a))


def test_newton_improves_the_table() -> None:
    for w, a in ((12, 5), (16, 7)):
        t = M.error_range(w, a, 0)
        n1 = M.error_range(w, a, 1)
        assert max(abs(n1[0]), abs(n1[1])) < max(abs(t[0]), abs(t[1]))


def test_seed_table_is_the_floor_of_the_midpoint_value() -> None:
    """seed(F, A, idx) = floor(2**F / sqrt(X_mid)), X_mid the midpoint of interval idx of X in [1, 4): y <= 2**F / sqrt(m / 2**(A+1)) < y + 1, as integer comparisons."""
    for f, a in ((16, 5), (18, 7), (26, 9)):
        for idx in range(0, 3 << a, 11):
            m = (1 << (a + 1)) + 2 * idx + 1
            y = M.seed(f, a, idx)
            assert y * y * m <= 1 << (2 * f + a + 1) < (y + 1) * (y + 1) * m


def test_table_has_three_times_two_to_the_a_intervals() -> None:
    assert M.table_size(7) == 384 and M.index(1 << 14, 16, 7) == 0 and M.index((1 << 16) - 1, 16, 7) == 383


def test_latency_formulas() -> None:
    assert [M.latency(v) for v in (0, 1, 2)] == [1, 6, 11]
    assert M.out_width(16) == 17
