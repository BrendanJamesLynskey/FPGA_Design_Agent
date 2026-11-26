"""The AXI wrapper's word packing and its model mapping (arith brief 148): the wrapper adds no arithmetic."""
from __future__ import annotations

import random

from arith.fft import model as fm
from arith.fft_axis import model


def test_pack_unpack_roundtrip_real_in_the_low_bits():
    rng = random.Random(1)
    for w in (4, 8, 16, 24):
        for _ in range(500):
            re, im = rng.randrange(-(1 << (w - 1)), 1 << (w - 1)), rng.randrange(-(1 << (w - 1)), 1 << (w - 1))
            word = model.pack(im, re, w)
            assert word < 1 << (2 * w) and model.unpack(word, w) == (re, im)
    assert model.pack(0, 1, 8) == 1 and model.pack(1, 0, 8) == 256        # the real part is the low half


def test_the_model_is_the_wrapped_fft_models():
    assert model.frame is fm.frame and model.out_width is fm.out_width
