"""The real-input FFT model against numpy.fft.rfft, the identities it rests on and pinned conventions (arith brief 148)."""
from __future__ import annotations

import random

import numpy as np
import pytest

from arith.fft_common import fft_ref as f
from arith.fft_real import model


@pytest.mark.parametrize("variant", ["sdf", "burst"])
@pytest.mark.parametrize("logn", [4, 5, 6, 8, 10])
def test_against_numpy_rfft(variant, logn):
    rng = random.Random(logn)
    n = 1 << logn
    xr = [rng.randrange(-30000, 30000) for _ in range(n)]
    for scale in (1, 0):
        y = np.array([a + 1j * b for a, b in f.real_frame(variant, xr, 18, scale, 1)])
        ref = np.fft.rfft(xr) / (n if scale else 1)
        assert len(y) == n // 2 + 1
        assert np.max(np.abs(y - ref)) < (4 if scale else 8 + n / 8), (variant, logn, scale)


def test_the_model_helper_is_the_sdf_path_and_the_widths_follow_the_spec():
    rng = random.Random(3)
    xr = [rng.randrange(-30000, 30000) for _ in range(64)]
    p = dict(TW=18, SCALE=1, RND=1)
    assert model.frame(p, xr) == f.real_frame("sdf", xr, 18, 1, 1)
    assert model.out_width(16, 7, 1) == 17 and model.out_width(16, 7, 0) == 24


def test_impulse_and_dc_and_nyquist_pinned_examples():
    n = 64
    a = 4000
    imp = [a] + [0] * (n - 1)
    y = f.real_frame("sdf", imp, 18, 0, 1)
    assert all(abs(re - a) <= 2 and abs(im) <= 2 for re, im in y)
    dc = [a] * n
    y = f.real_frame("sdf", dc, 18, 0, 1)
    assert abs(y[0][0] - a * n) <= 8 and all(abs(re) <= 8 and abs(im) <= 8 for re, im in y[1:])
    nyq = [a if i % 2 == 0 else -a for i in range(n)]
    y = f.real_frame("sdf", nyq, 18, 0, 1)
    assert abs(y[n // 2][0] - a * n) <= 8 and all(abs(re) <= 8 and abs(im) <= 8 for re, im in y[:-1])
