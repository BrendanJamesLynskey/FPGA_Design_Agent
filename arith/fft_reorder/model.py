"""Bit-exact model of the reorder buffer (arith brief 148): the word at position p of a frame leaves at position bitrev(p)."""
from __future__ import annotations

from arith.fft_common.fft_ref import bitrev


def reorder(logn: int, words: list[int]) -> list[int]:
    n = 1 << logn
    assert len(words) == n
    return [words[bitrev(k, logn)] for k in range(n)]
