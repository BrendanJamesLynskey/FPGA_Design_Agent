"""The rounding model against Python integer arithmetic (brief 139b): exhaustive small widths, random large; no simulator needed."""
from __future__ import annotations

import random
from fractions import Fraction

from arith.fxp_round import model as M


def test_rounding_definitions_exhaustive_small_widths() -> None:
    """Each mode against its textbook definition on exact fractions, every x, every S, W_IN 2 to 9."""
    for w in range(2, 10):
        for s in range(w):
            for x in range(-(1 << (w - 1)), 1 << (w - 1)):
                f = Fraction(x, 1 << s)
                lo = x >> s
                assert M.rnd(x, s, 0) == lo == (f.numerator // f.denominator)
                assert M.rnd(x, s, 1) == ((f + Fraction(1, 2)).__floor__() if s else x)         # half up: floor(x / 2**s + 1/2)
                c = M.rnd(x, s, 2)
                assert abs(Fraction(c) - f) <= Fraction(1, 2)                  # convergent is within half an LSB, with ties to even
                if s and (f - lo) == Fraction(1, 2):
                    assert c % 2 == 0


def test_fold_add_form_equals_the_definition() -> None:
    """The single-adder form with the carry-in (what fxp_round_fold builds) equals the definition for every x, S and mode, W_IN up to 10."""
    for w in range(2, 11):
        for s in range(w):
            for mode in range(3):
                for x in range(-(1 << (w - 1)), 1 << (w - 1)):
                    assert M.fold_add(x, s, mode) == M.rnd(x, s, mode)


def test_error_bounds() -> None:
    """|round(x) - x / 2**s| is below 1 LSB for truncate and at most 1/2 LSB for the two rounding modes, before saturation."""
    for w in range(2, 10):
        for s in range(1, w):
            for x in range(-(1 << (w - 1)), 1 << (w - 1)):
                f = Fraction(x, 1 << s)
                assert 0 <= f - M.rnd(x, s, 0) < 1
                assert abs(M.rnd(x, s, 1) - f) <= Fraction(1, 2)
                assert abs(M.rnd(x, s, 2) - f) <= Fraction(1, 2)


def test_saturation_and_wrap() -> None:
    for w_out in range(2, 9):
        lo, hi = -(1 << (w_out - 1)), (1 << (w_out - 1)) - 1
        for r in range(-300, 300):
            assert M.fit(r, w_out, 1) == max(lo, min(hi, r))
            assert M.fit(r, w_out, 0) == ((r - lo) % (1 << w_out)) + lo


def test_random_large_widths_agree_with_integer_arithmetic() -> None:
    rng = random.Random(11)
    for w in (16, 24, 32, 48, 64):
        for _ in range(3000):
            s = rng.randint(0, w - 1)
            x = rng.randint(-(1 << (w - 1)), (1 << (w - 1)) - 1)
            mode = rng.randint(0, 2)
            assert M.fold_add(x, s, mode) == M.rnd(x, s, mode)
            w_out = rng.randint(2, w + 2)
            y = M.fxp_round(x, w, s, w_out, mode, 1)
            assert -(1 << (w_out - 1)) <= y < (1 << (w_out - 1))


def test_the_max_positive_input_can_round_up_one_past_the_input_range() -> None:
    """The reason the RTL keeps W_IN - S + 1 bits before saturation: the largest x rounds up to 2**(W_IN-S-1)."""
    for w in range(3, 10):
        for s in range(1, w):
            assert M.rnd((1 << (w - 1)) - 1, s, 1) == 1 << (w - s - 1)
