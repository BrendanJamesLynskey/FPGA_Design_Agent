"""Bit-exact model of the 2-parallel FFT (arith brief 161): see arith/fft_common/fft_ref.py (mdc2_frame) for the arithmetic and the conventions."""
from __future__ import annotations

from arith.fft_common import fft_ref


def out_width(w: int, logn: int, scale: int) -> int:
    return w if scale else w + logn


def pairs(x: list[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """The input frame as the clocks present it: clock m carries (re, im) of x[2m] and of x[2m + 1]."""
    return [(x[2 * m][0], x[2 * m][1], x[2 * m + 1][0], x[2 * m + 1][1]) for m in range(len(x) // 2)]


def frame(variant: str, p: dict, x: list[tuple[int, int]], inverse: int) -> list[tuple[int, int, int, int]]:
    """One frame as the RTL outputs it: N/2 words (re0, im0, re1, im1) = X[k] and X[k + N/2] for k = the output position (ORDER = 0) or its bit reversal in LOGN - 1 bits (ORDER = 1)."""
    assert variant == "par2"
    return fft_ref.mdc2_frame(x, p["TW"], p["SCALE"], p["RND"], inverse, 1 if p["ORDER"] == 0 else 0)


def natural(p: dict, words: list[tuple[int, int, int, int]]) -> list[tuple[int, int]]:
    """The N output samples X[0] .. X[N-1] in natural order from the frame's words (either ORDER)."""
    h = len(words)
    out = [None] * (2 * h)
    n = h.bit_length() - 1
    for pos, (a, b, c, d) in enumerate(words):
        k = pos if p["ORDER"] == 0 else fft_ref.bitrev(pos, n)
        out[k], out[k + h] = (a, b), (c, d)
    return out
