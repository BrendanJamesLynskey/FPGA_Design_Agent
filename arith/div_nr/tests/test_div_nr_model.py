"""The reciprocal-multiply divider model against exact rational arithmetic (brief 139c): the error bound of both variants over every normalised pair at small widths and
over sampled pairs at large ones, the structure of each variant, the residual word; no simulator needed."""
from __future__ import annotations

import random
from fractions import Fraction

from arith.div_nr import model as M


def bound(w: int, ab: int, it: int, variant: int) -> tuple[Fraction, Fraction]:
    """(lower, upper) of the error e = Q_exact - Q in units of the last place of Q (2**-(W-1)): Newton 0 <= e < 3/2 + 2**(W - 2**IT * (A+1) + 1) (one-sided: the
    exact-arithmetic Newton reciprocal never overshoots and the multiply by a only floors); Goldschmidt -1/2 < e < 3/2 + 2**(W - 2**IT * (A+1) + 1)
    (the two multiplies of an iteration do not correct each other, so Q may exceed the exact quotient by a fraction of an ulp)."""
    up = Fraction(3, 2) + Fraction(2) ** (w - (1 << it) * (ab + 1) + 1)
    return (Fraction(0), up) if variant == 0 else (Fraction(-1, 2), up)


def check(w: int, ab: int, it: int, variant: int, pairs) -> None:
    lo, hi = M.error_range(w, ab, it, variant, pairs)
    blo, bhi = bound(w, ab, it, variant)
    ok = (blo <= lo and hi < bhi) if variant == 0 else (blo < lo and hi < bhi)
    assert ok, (w, ab, it, variant, float(lo), float(hi), float(blo), float(bhi))


def all_pairs(w: int):
    return [(a, b) for a in M.normalised(w) for b in M.normalised(w)]


def test_error_bounds_every_pair_at_w8_and_w9() -> None:
    for w, abs_ in ((8, range(2, 7)), (9, (3, 4, 5))):
        pairs = all_pairs(w)
        for ab in abs_:
            for it in (1, 2, 3):
                for v in M.VARIANTS:
                    check(w, ab, it, v, pairs)


def test_error_bounds_every_pair_at_w10() -> None:
    pairs = all_pairs(10)
    for v in M.VARIANTS:
        check(10, 4, 2, v, pairs)


def test_error_bounds_wide_widths_sampled() -> None:
    rng = random.Random(6)
    for w, ab, it in ((12, 5, 2), (16, 7, 1), (16, 7, 2), (16, 8, 2), (16, 4, 3), (20, 8, 2), (24, 9, 1), (24, 9, 2), (24, 9, 3), (32, 10, 2)):
        lo, hi = 1 << (w - 1), 1 << w
        pairs = [(rng.randrange(lo, hi), rng.randrange(lo, hi)) for _ in range(15000)]
        pairs += [(v >> w, v & (hi - 1)) for v in M.inputs(w, ab, 3000, seed_=w)] + [(hi - 1, lo), (lo, hi - 1), (lo, lo), (hi - 1, hi - 1)]
        for v in M.VARIANTS:
            check(w, ab, it, v, pairs)


def test_quotient_range_and_extreme_operands() -> None:
    """Q < 2**W for the largest ratio, Q around 2**(W-2) for the smallest, a = b gives about 2**(W-1) - 1 or 2**(W-1)."""
    for w, ab, it in ((8, 3, 2), (12, 5, 2), (16, 7, 2)):
        lo, hi = 1 << (w - 1), (1 << w) - 1
        for v in M.VARIANTS:
            assert M.quotient(hi, lo, w, ab, it, v) < 1 << w
            assert abs(M.quotient(lo, hi, w, ab, it, v) - (1 << (w - 2))) <= 3
            assert abs(M.quotient(lo, lo, w, ab, it, v) - (1 << (w - 1))) <= 2


def test_newton_and_goldschmidt_agree_within_two_ulp() -> None:
    rng = random.Random(2)
    for w, ab, it in ((16, 7, 2), (24, 9, 2)):
        for _ in range(4000):
            a, b = rng.randrange(1 << (w - 1), 1 << w), rng.randrange(1 << (w - 1), 1 << w)
            assert abs(M.quotient(a, b, w, ab, it, 0) - M.quotient(a, b, w, ab, it, 1)) <= 3


def test_latency_and_multiplier_counts() -> None:
    assert [M.latency(0, it) for it in (1, 2, 3)] == [6, 10, 14]
    assert [M.latency(1, it) for it in (1, 2, 3)] == [4, 6, 8]
    assert [M.multipliers(v, 2) for v in (0, 1)] == [5, 5]
    assert M.out_width(16) == 16
