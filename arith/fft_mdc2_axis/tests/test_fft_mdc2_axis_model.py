"""The AXI4-Stream 2-parallel FFT's model (arith brief 168): the unscaled 2-parallel transform and the block-floating-point rule, against NumPy and against a brute-force search for the exponent, and the packing of the AXI words."""
from __future__ import annotations

import random

import numpy as np
import pytest

from arith.fft_common import fft_ref as f
from arith.fft_mdc2 import model as m2
from arith.fft_mdc2_axis import model

P = dict(TW=18, RND=1, W=16, LOGN=0)


def rand_frame(n, rng, frac):
    a = max(1, int(frac * (1 << 15)))
    return [(rng.randrange(-a, a), rng.randrange(-a, a)) for _ in range(n)]


@pytest.mark.parametrize("logn", [4, 5, 6, 8, 10])
@pytest.mark.parametrize("frac", [0.65, 0.01, 0.0001])
def test_value_times_two_to_the_exponent_matches_numpy(logn, frac):
    rng = random.Random(logn)
    n = 1 << logn
    x = rand_frame(n, rng, frac)
    xc = np.array([a + 1j * b for a, b in x])
    for inverse in (0, 1):
        p = dict(P, LOGN=logn)
        beats, s = model.frame(p, x, inverse)
        y = np.array([complex(b[0], b[1]) for b in beats] + [complex(b[2], b[3]) for b in beats]) * 2.0 ** s
        ref = np.fft.ifft(xc) * n if inverse else np.fft.fft(xc)
        err = np.max(np.abs(y - ref))
        # the unscaled core's error (about 2 * sqrt(N) + 6 LSB of the wide word) plus the shift's rounding (2**s / sqrt(2) per part)
        assert err < 2 * 2 ** (logn / 2) + 6 + 2.0 ** s, (logn, frac, inverse, err, s)


def test_the_exponent_is_the_smallest_shift_after_which_every_part_fits():
    rng = random.Random(5)
    p = dict(P, LOGN=6, W=12)
    lim = 1 << (p["W"] - 1)

    def fits(parts, s):                                              # a floor shift by s (negative: a left shift) leaves every part in W signed bits
        return all(-lim <= ((v >> s) if s >= 0 else (v << -s)) < lim for v in parts)

    for frac in (0.9, 0.1, 0.001, 0.0):
        x = rand_frame(64, rng, frac * 16)
        parts = [v for w in f.mdc2_frame(x, p["TW"], 0, p["RND"], 0, 1) for v in w]
        beats, s = model.frame(p, x, 0)
        assert all(-lim <= v < lim for b in beats for v in b)
        want = next(t for t in range(-40, 40) if fits(parts, t))     # the smallest shift that fits, by brute force
        assert s == want, (frac, s, want)


def test_the_beats_are_the_two_halves_of_the_spectrum_in_natural_order():
    rng = random.Random(7)
    p = dict(P, LOGN=5, W=16)
    x = rand_frame(32, rng, 0.5)
    beats, s = model.frame(p, x, 0)
    core = m2.frame("par2", dict(TW=p["TW"], SCALE=0, RND=1, ORDER=0, W=16), x, 0)
    nat, y = m2.natural(dict(ORDER=0), core), None
    ys, s2 = f.bfp_normalise(nat, 16, 1)
    assert s == s2 and [(b[0], b[1]) for b in beats] == ys[:16] and [(b[2], b[3]) for b in beats] == ys[16:]


def test_saturation_when_the_rounding_carries_a_part_to_two_to_the_w_minus_one():
    p = dict(P, LOGN=5, W=8, TW=10)
    hi = 127
    col, left = [], (1 << 11) - 1
    for _ in range(32):
        v = min(hi, left)
        col.append(v)
        left -= v
    beats, s = model.frame(p, [(v, 0) for v in col], 0)
    assert s == 4 and beats[0][0] == 127            # 2047 + 8 >> 4 = 128, saturated to 127


def test_pack_in_has_sample_0_in_the_low_half_and_the_real_part_low():
    assert model.pack_in((1, 0), (0, 0), 8) == 1 and model.pack_in((0, 1), (0, 0), 8) == 1 << 8
    assert model.pack_in((0, 0), (1, 0), 8) == 1 << 16 and model.pack_in((0, 0), (0, 1), 8) == 1 << 24
    assert model.pack_in((-1, -1), (-1, -1), 8) == 0xFFFFFFFF


def test_unpack_out_inverts_the_packing_of_four_signed_parts():
    rng = random.Random(1)
    for w in (4, 9, 16, 18):
        for _ in range(200):
            v = tuple(rng.randrange(-(1 << (w - 1)), 1 << (w - 1)) for _ in range(4))
            word = sum((x & ((1 << w) - 1)) << (i * w) for i, x in enumerate(v))
            assert model.unpack_out(word, w) == v


def test_exp_width_and_gap():
    assert model.exp_width(16, 10) == 7 and model.exp_width(8, 5) == 6
    assert [model.gap(n) for n in (4, 5, 6, 10)] == [2, 4, 8, 128]
