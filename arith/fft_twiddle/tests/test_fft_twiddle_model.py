"""The twiddle table's model against high-precision values, its stated error bound and exact symmetries (arith brief 148)."""
from __future__ import annotations

import math

from arith.fft_common import fft_ref as f
from arith.fft_twiddle import model


def test_error_against_the_real_cosine_is_within_the_stated_bound_for_every_angle_and_width():
    worst = 0.0
    for tw in range(4, 29):
        s = 2 ** (tw - 2)
        bound = 0.5 + 2.0 ** -(32 - tw) + 1e-9
        for idx in range(4096):
            wr, wi = f.twiddle(idx, tw)
            a = 2 * math.pi * idx / 4096
            e = max(abs(wr - s * math.cos(a)), abs(wi + s * math.sin(a)))
            worst = max(worst, e)
            assert e <= bound, (tw, idx, e)
    assert worst > 0.4          # the bound is not vacuous: the double rounding does reach half a unit


def test_exact_values_and_the_scale():
    for tw in (4, 8, 16, 28):
        s = 2 ** (tw - 2)
        assert f.twiddle(0, tw) == (s, 0)
        assert f.twiddle(1024, tw) == (0, -s)           # exp(-j pi/2) = -j
        assert f.twiddle(2048, tw) == (-s, 0)
        assert f.twiddle(3072, tw) == (0, s)


def test_quarter_turn_symmetry_is_exact_for_every_index():
    for tw in (4, 9, 16, 28):
        for idx in range(4096):
            wr, wi = f.twiddle(idx, tw)
            wr2, wi2 = f.twiddle((idx + 1024) % 4096, tw)
            assert (wr2, wi2) == (wi, -wr), (tw, idx)       # exp(-j(a + pi/2)) = -j exp(-j a): wr' = wi, wi' = -wr


def test_smaller_circles_read_every_nth_angle():
    for logc in (2, 5, 8, 11):
        assert model.twiddle(logc, 16, 3) == tuple(f.to_unsigned(v, 16) for v in f.twiddle(3 * (4096 >> logc), 16))


def test_master_table_is_correctly_rounded_cosine():
    assert f.COS_MASTER[0] == 1 << 30 and f.COS_MASTER[1024] == 0
    for i in (1, 17, 512, 777, 1023):
        assert abs(f.COS_MASTER[i] - (1 << 30) * math.cos(2 * math.pi * i / 4096)) <= 0.5 + 1e-3
