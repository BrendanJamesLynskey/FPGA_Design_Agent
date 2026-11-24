"""The complex multiplier's model against an independent formulation and pinned examples (arith brief 148)."""
from __future__ import annotations

import itertools
import random

from arith.fft_cmul import model
from arith.fft_common.fft_ref import to_signed, to_unsigned


def test_three_multiplication_identity_equals_the_four_multiplication_form_exhaustively():
    for wa, wb in ((2, 2), (3, 2), (2, 3), (3, 3), (4, 2)):
        for a, b, c, d in itertools.product(range(1 << wa), range(1 << wa), range(1 << wb), range(1 << wb)):
            assert model.cmul(wa, wb, a, b, c, d) == model.cmul3(wa, wb, a, b, c, d)


def test_identity_on_random_wide_operands():
    rng = random.Random(7)
    for _ in range(4000):
        wa, wb = rng.randrange(2, 40), rng.randrange(2, 40)
        v = [rng.getrandbits(wa), rng.getrandbits(wa), rng.getrandbits(wb), rng.getrandbits(wb)]
        assert model.cmul(wa, wb, *v) == model.cmul3(wa, wb, *v)


def test_pinned_examples_and_the_output_never_overflows():
    # (3 + 4j) * (2 - 1j) = 10 + 5j
    assert model.cmul(8, 8, 3, 4, 2, to_unsigned(-1, 8)) == (10, 5)
    # the most negative values: (-128 - 128j) * (-128 - 128j) = 0 + 32768j, which needs 17 bits as a signed number: WA + WB + 1 = 17
    pr, pi = model.cmul(8, 8, to_unsigned(-128, 8), to_unsigned(-128, 8), to_unsigned(-128, 8), to_unsigned(-128, 8))
    assert to_signed(pr, 17) == 0 and to_signed(pi, 17) == 32768
    # j * j = -1
    assert model.cmul(4, 4, 0, 1, 0, 1) == (to_unsigned(-1, 9), 0)
