"""The window multiplier's model: the rounding rule and the bound |y| <= |x| against exact rational arithmetic, and the window coefficient tables (arith brief 148)."""
from __future__ import annotations

import itertools
import math
from fractions import Fraction

from arith.fft_common import fft_ref as f
from arith.fft_window import model


def test_rounding_rule_against_rational_arithmetic_and_the_magnitude_bound():
    for wd, ww in ((3, 3), (4, 3), (3, 5)):
        for x, w in itertools.product(range(-(1 << (wd - 1)), 1 << (wd - 1)), range(1 << ww)):
            for rnd in (0, 1):
                y = f.window_mul(x, w, ww, rnd)
                exact = Fraction(x * w, 1 << ww)
                want = math.floor(exact + (Fraction(1, 2) if rnd else 0))
                assert y == want
                assert abs(y) <= abs(x) + (0 if rnd == 0 or x < 0 else 0), (x, w, rnd, y)
                assert -(1 << (wd - 1)) <= y < (1 << (wd - 1))


def test_pinned_examples():
    assert model.window(8, 8, 1, 100, f.to_unsigned(-100, 8), 128) == (50, f.to_unsigned(-50, 8))
    assert model.window(8, 8, 1, 1, 1, 128) == (1, 1)          # 0.5 rounds half up: 1
    assert model.window(8, 8, 0, 1, f.to_unsigned(-1, 8), 128) == (0, f.to_unsigned(-1, 8))    # floor(0.5) = 0, floor(-0.5) = -1


def test_window_tables():
    for kind in ("rect", "hann", "hamming", "blackman"):
        c = f.window_coeffs(kind, 256, 16)
        assert len(c) == 256 and max(c) <= 65535 and min(c) >= 0
    h = f.window_coeffs("hann", 256, 16)
    assert h[0] == 0 and h[128] == 65535                       # the peak is clipped to 1 - 2**-16
    assert all(h[i] == h[256 - i] for i in range(1, 256))      # periodic Hann is symmetric about n = 0
    assert abs(sum(h) / 256 / 65536 - 0.5) < 1e-3
