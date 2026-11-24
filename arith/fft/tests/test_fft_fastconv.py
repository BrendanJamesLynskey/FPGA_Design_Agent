"""Fast convolution (overlap-save and overlap-add on the FFT models) against direct convolution (arith brief 148, phase 0: a Python model; the RTL is phase 1)."""
from __future__ import annotations

import random

import numpy as np
import pytest

from arith.fft_common import fastconv as fc


def taps(n):
    return [0.1 * np.sin(0.3 * i) / (1 + 0.1 * i) for i in range(n)]


@pytest.mark.parametrize("variant", ["sdf", "burst"])
@pytest.mark.parametrize("method", [fc.overlap_save, fc.overlap_add])
def test_equals_direct_convolution_within_the_stated_error(variant, method):
    rng = random.Random(11)
    x = [(rng.randrange(-20000, 20000), 0) for _ in range(900)]
    h = taps(33)
    y = method(x, h, 8, 16, 18, 24, 14, variant)
    ref = np.convolve([a for a, _ in x], h)[:len(x)]
    assert len(y) == len(x)
    assert np.max(np.abs(np.array([a for a, _ in y]) - ref)) < 8.0           # LSB of the output word
    assert max(abs(b) for _, b in y) <= 2                                    # a real filter on a real signal leaves no imaginary part beyond rounding


def test_overlap_save_and_overlap_add_agree_within_rounding():
    rng = random.Random(12)
    x = [(rng.randrange(-20000, 20000), 0) for _ in range(700)]
    h = taps(65)
    a = np.array([p for p, _ in fc.overlap_save(x, h, 9, 16, 18, 24, 14)])
    b = np.array([p for p, _ in fc.overlap_add(x, h, 9, 16, 18, 24, 14)])
    assert np.max(np.abs(a - b)) < 8.0


def test_complex_input_is_filtered_part_by_part_and_a_unit_filter_passes_the_signal():
    rng = random.Random(13)
    x = [(rng.randrange(-15000, 15000), rng.randrange(-15000, 15000)) for _ in range(300)]
    y = fc.overlap_save(x, [1.0], 7, 16, 18, 24, 14)
    assert max(max(abs(a - c), abs(b - d)) for (a, b), (c, d) in zip(y, x)) <= 3
    h = taps(17)
    y = fc.overlap_save(x, h, 7, 16, 18, 24, 14)
    for part in (0, 1):
        ref = np.convolve([v[part] for v in x], h)[:len(x)]
        assert np.max(np.abs(np.array([v[part] for v in y]) - ref)) < 8.0


def test_the_filter_spectrum_must_fit_its_width():
    with pytest.raises(AssertionError):
        fc.filter_spectrum([1.0] * 40, 64, 12, 12)
