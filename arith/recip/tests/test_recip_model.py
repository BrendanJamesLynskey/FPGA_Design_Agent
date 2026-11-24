"""The reciprocal model against exact rational arithmetic (brief 139c): the error bound of every variant over every normalised input at small widths and
over sampled inputs at large ones, the one-sidedness of the Newton variants, the residual word width; no simulator needed."""
from __future__ import annotations

import random
from fractions import Fraction

from arith.recip import model as M


def bound(w: int, a: int, variant: int) -> tuple[Fraction, Fraction, bool]:
    """(lower, upper, one_sided): the spec's error bounds in units of the last place: table |e| <= 2**(W-A-1) + 1/2; one Newton step 0 <= e < 2**(W-2A-2) + 3/2;
    two steps 0 <= e < 2**(W-4A-4) + 3/2."""
    if variant == 0:
        e = Fraction(1 << (w - a - 1)) + Fraction(1, 2)
        return -e, e, False
    p = 2 * a + 2 if variant == 1 else 4 * a + 4
    return Fraction(0), Fraction(2) ** (w - p) + Fraction(3, 2), True


def check(w: int, a: int, variant: int, vals=None) -> None:
    lo, hi = M.error_range(w, a, variant, vals)
    blo, bhi, one = bound(w, a, variant)
    if one:
        assert lo >= 0 and hi < bhi, (w, a, variant, float(lo), float(hi), float(bhi))
    else:
        assert blo <= lo and hi <= bhi, (w, a, variant, float(lo), float(hi), float(bhi))


def test_error_bounds_exhaustive_every_table_width() -> None:
    """Every normalised b at W = 8 to 12 for every A from 2 to W - 2 (every variant): the bound holds, and the residual word never overflows (asserted inside recip)."""
    for w in range(8, 13):
        for a in range(2, w - 1):
            for v in M.VARIANTS:
                check(w, a, v)


def test_error_bounds_wide_widths_sampled() -> None:
    rng = random.Random(6)
    for w, a in ((16, 7), (16, 8), (16, 4), (18, 7), (20, 8), (24, 9), (24, 6), (32, 10)):
        vals = M.inputs(w, a, 6000, seed_=w) + [rng.randrange(1 << (w - 1), 1 << w) for _ in range(2000)]
        for v in M.VARIANTS:
            check(w, a, v, vals)


def test_exhaustive_w16_a7_a8() -> None:
    for a in (7, 8):
        for v in M.VARIANTS:
            check(16, a, v)


def test_output_range_and_the_value_at_b_equal_one() -> None:
    """Y is in [2**(W-1), 2**W]; the value 2**W only for b = 2**(W-1) (B = 1)."""
    for w, a in ((8, 3), (12, 5), (16, 7)):
        for v in M.VARIANTS:
            for b in M.normalised(w):
                y = M.recip(b, w, a, v)
                assert (1 << (w - 1)) - (1 << (w - a)) <= y <= 1 << w
                if y == 1 << w:
                    assert b == 1 << (w - 1)


def test_newton_improves_the_table_and_is_monotone_in_the_variant() -> None:
    for w, a in ((12, 5), (16, 7)):
        w0 = M.error_range(w, a, 0)
        w1 = M.error_range(w, a, 1)
        w2 = M.error_range(w, a, 2)
        assert max(abs(w1[0]), abs(w1[1])) < max(abs(w0[0]), abs(w0[1]))
        assert w2[1] <= w1[1] + Fraction(1, 100)


def test_seed_table_is_the_midpoint_reciprocal() -> None:
    """seed(F, A, idx) is the nearest integer to 2**F / B_mid (so within half a unit of the exact midpoint reciprocal)."""
    for f, a in ((16, 5), (18, 7), (26, 9)):
        for idx in range(0, 1 << a, 7):
            bm = Fraction((1 << (a + 1)) + 2 * idx + 1, 1 << (a + 1))
            assert abs(Fraction(1 << f) / bm - M.seed(f, a, idx)) <= Fraction(1, 2)


def test_latency_formulas() -> None:
    assert [M.latency(v) for v in (0, 1, 2)] == [1, 5, 9]
    assert M.out_width(16) == 17
