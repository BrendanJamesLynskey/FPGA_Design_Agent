"""The AXI wrapper's word packing and its model mapping (arith brief 161): the wrapper adds no arithmetic."""
from __future__ import annotations

import random

from arith.fft_real import model as rm
from arith.fft_real_axis import model


def test_pack_in_has_the_odd_sample_in_the_high_half():
    assert model.pack_in(1, 0, 8) == 1 and model.pack_in(0, 1, 8) == 256
    assert model.pack_in(-1, -1, 8) == 0xFFFF and model.pack_in(-128, 127, 8) == (127 << 8) | 0x80


def test_unpack_out_has_the_real_part_in_the_low_half():
    rng = random.Random(1)
    for wx in (5, 9, 17, 27):
        for _ in range(500):
            re, im = rng.randrange(-(1 << (wx - 1)), 1 << (wx - 1)), rng.randrange(-(1 << (wx - 1)), 1 << (wx - 1))
            word = ((im & ((1 << wx) - 1)) << wx) | (re & ((1 << wx) - 1))
            assert model.unpack_out(word, wx) == (re, im)


def test_the_model_is_the_wrapped_core_model():
    assert model.frame is rm.frame and model.out_width is rm.out_width


def test_the_enforced_gap_is_n_over_8():
    assert [model.gap(n) for n in (4, 5, 6, 10)] == [2, 4, 8, 128]
