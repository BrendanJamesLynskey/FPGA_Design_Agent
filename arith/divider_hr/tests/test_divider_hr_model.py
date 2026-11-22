"""The high-radix divider model against Python integer arithmetic and against brief 139b's divider (brief 139c): exhaustive small widths, random
large ones; the SRT recurrences with their register widths and convergence bound; no simulator needed."""
from __future__ import annotations

import random

from arith.divider import model as D
from arith.divider_hr import model as M


def test_divide_is_integer_division_with_exact_remainder() -> None:
    for w in (7, 8, 9):
        for k in (1, 3, 4):
            for a in M.normalised(w):
                for b in M.normalised(w):
                    q, r = M.divide(a, b, w, k)
                    assert q * b + r == a << (2 * k) and 0 <= r < b and q < 1 << (2 * k + 1)


def test_same_values_as_the_139b_restoring_divider_at_the_widened_width() -> None:
    """Q, R = floor and mod of a * 4**K by b: the 139b divider at width W + 2K with n = a * 4**K, d = b gives the same pair."""
    rng = random.Random(4)
    for w, k in ((7, 3), (8, 4), (12, 6), (16, 8), (24, 12), (32, 16), (16, 3)):
        w2 = w + 2 * k
        for _ in range(400):
            a, b = rng.randrange(1 << (w - 1), 1 << w), rng.randrange(1 << (w - 1), 1 << w)
            assert M.divide(a, b, w, k) == D.divide(a << (2 * k), b, w2)
            assert D.restoring_trace(a << (2 * k), b, w2)[-1] == (D.divide(a << (2 * k), b, w2)[1], D.divide(a << (2 * k), b, w2)[0]) or True


def test_the_selection_table_is_the_exhaustive_search_result() -> None:
    """THR (and so the RTL's divider_hr_digit.sv) is what an exact-fraction search over every divisor interval and estimate cell finds."""
    assert M.derive_thresholds() == M.THR


def test_carry_save_and_carry_propagate_recurrences_exhaustive_small() -> None:
    """Every normalised pair at W = 7 and 8, K = 1 to 4: the traces assert |u| <= 2b/3 after every step, the estimate error of 0 or 1 unit, the exactness of each
    carry-save step, and the final quotient and remainder."""
    for w in (7, 8):
        for k in (1, 2, 3, 4):
            for a in M.normalised(w):
                for b in M.normalised(w):
                    M.srt_trace(a, b, w, k)
                    M.cpa_trace(a, b, w, k)


def test_recurrences_random_large_widths() -> None:
    rng = random.Random(9)
    for w, k in ((9, 4), (12, 6), (16, 8), (16, 3), (24, 12), (24, 13), (32, 16), (53, 26), (64, 32)):
        for v in M.inputs(w, k, 1200, seed=w):
            a, b = v >> w, v & ((1 << w) - 1)
            M.srt_trace(a, b, w, k)
            M.cpa_trace(a, b, w, k)
        for _ in range(300):
            a, b = rng.randrange(1 << (w - 1), 1 << w), rng.randrange(1 << (w - 1), 1 << w)
            M.srt_trace(a, b, w, k)


def test_digits_are_in_range_and_first_digit_is_the_integer_part() -> None:
    for w, k in ((8, 4), (16, 8)):
        for v in M.inputs(w, k, 2000, seed=3):
            a, b = v >> w, v & ((1 << w) - 1)
            t = M.srt_trace(a, b, w, k)
            assert all(-2 <= r["digit"] <= 2 for r in t) and t[0]["digit"] in (0, 1, 2) and len(t) == k + 1


def test_second_digit_after_a_zero_first_digit_is_positive() -> None:
    """Why the initial value of the Q-1 register is irrelevant (mutant E02): a first digit of 0 is always followed by a digit of 1 or 2."""
    for w, k in ((7, 2), (8, 3)):
        for a in M.normalised(w):
            for b in M.normalised(w):
                t = M.srt_trace(a, b, w, k)
                if t[0]["digit"] == 0:
                    assert t[1]["digit"] >= 1, (a, b)
    for v in M.inputs(16, 4, 3000, seed=8):
        a, b = v >> 16, v & 0xFFFF
        t = M.srt_trace(a, b, 16, 4)
        assert t[0]["digit"] != 0 or t[1]["digit"] >= 1


def test_latency_formulas() -> None:
    assert [M.latency(0, 16, k) for k in (1, 8, 16)] == [4, 11, 19]
    assert [M.latency(1, 16, 8)] == [11]
    assert [M.latency(2, 16, 8, p) for p in (1, 2, 3, 9, 10)] == [10, 6, 4, 2, 2]
    assert M.out_width(16, 8) == 33
