"""The 2-parallel FFT model against NumPy's FFT and the identities the contract states (arith brief 161)."""
from __future__ import annotations

import random

import numpy as np
import pytest

from arith.fft_common import fft_ref as f
from arith.fft_mdc2 import model

P = dict(TW=18, SCALE=1, RND=1, ORDER=0, W=16)


def rand_frame(n, rng, frac=0.65):
    a = int(frac * (1 << 15))
    return [(rng.randrange(-a, a), rng.randrange(-a, a)) for _ in range(n)]


@pytest.mark.parametrize("logn", [4, 5, 6, 7, 8, 10])
def test_against_numpy_scaled_and_unscaled(logn):
    rng = random.Random(logn)
    n = 1 << logn
    x = rand_frame(n, rng)
    xc = np.array([a + 1j * b for a, b in x])
    for scale in (1, 0):
        for inverse in (0, 1):
            p = dict(P, SCALE=scale)
            y = np.array([a + 1j * b for a, b in model.natural(p, model.frame("par2", p, x, inverse))])
            ref = (np.fft.ifft(xc) * n if inverse else np.fft.fft(xc)) / (n if scale else 1)
            err = np.max(np.abs(y - ref))
            assert err < (5.0 if scale else 2 * 2 ** (logn / 2) + 6), (logn, scale, inverse, err)


def test_the_pair_at_clock_k_is_x_k_and_x_k_plus_half():
    rng = random.Random(1)
    x = rand_frame(32, rng)
    w = model.frame("par2", P, x, 0)
    nat = model.natural(P, w)
    assert [(a, b) for a, b, _, _ in w] == nat[:16] and [(c, d) for _, _, c, d in w] == nat[16:]


def test_bit_reversed_order_is_the_pairs_permuted_in_logn_minus_one_bits():
    rng = random.Random(2)
    x = rand_frame(64, rng)
    nat = model.frame("par2", dict(P, ORDER=0), x, 0)
    br = model.frame("par2", dict(P, ORDER=1), x, 0)
    assert br == [nat[f.bitrev(p, 5)] for p in range(32)]


def test_inverse_is_the_swap_of_a_forward_transform():
    rng = random.Random(3)
    x = rand_frame(32, rng)
    inv = model.frame("par2", P, x, 1)
    fwd = model.frame("par2", P, [(b, a) for a, b in x], 0)
    assert inv == [(b, a, d, c) for a, b, c, d in fwd]


def test_input_pairs_are_even_and_odd_samples():
    x = [(i, -i) for i in range(8)]
    assert model.pairs(x) == [(0, 0, 1, -1), (2, -2, 3, -3), (4, -4, 5, -5), (6, -6, 7, -7)]


def test_impulse_gives_a_over_n_when_scaled():
    n = 64
    x = [(0, 0)] * n
    x[0] = (16000, 0)
    out = model.natural(P, model.frame("par2", P, x, 0))
    assert all(abs(a - 16000 / n) <= 1 and abs(b) <= 1 for a, b in out)
