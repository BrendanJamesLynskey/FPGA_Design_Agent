"""The reorder buffer's model: a permutation and an involution for every size, and pinned examples (arith brief 148)."""
from __future__ import annotations

from arith.fft_common.fft_ref import bitrev
from arith.fft_reorder import model


def test_bit_reversal_is_an_involution_and_a_permutation_for_every_size_to_4096():
    for n in range(1, 13):
        seen = set()
        for a in range(1 << n):
            r = bitrev(a, n)
            assert bitrev(r, n) == a
            seen.add(r)
        assert len(seen) == 1 << n


def test_against_string_reversal_and_pinned_examples():
    assert model.reorder(3, list(range(8))) == [0, 4, 2, 6, 1, 5, 3, 7]
    assert model.reorder(2, [10, 11, 12, 13]) == [10, 12, 11, 13]
    for n in (4, 7, 10):
        w = list(range(1 << n))
        assert model.reorder(n, model.reorder(n, w)) == w
        assert model.reorder(n, w) == [int(format(k, f"0{n}b")[::-1], 2) for k in range(1 << n)]
