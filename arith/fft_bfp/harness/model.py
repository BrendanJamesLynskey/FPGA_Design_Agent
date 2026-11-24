"""Bit-exact model of the block-floating-point FFT (arith brief 161): the unscaled transform of arith/fft (SCALE = 0, W + LOGN bit words), then one exponent per frame and
every word shifted to W bits (fft_ref.bfp_normalise). Python integers only."""
from __future__ import annotations

import fft_ref


def exp_width(w: int, logn: int) -> int:
    return (2 * w + logn - 1).bit_length() + 1            # $clog2(2 * W + LOGN) + 1


def core_frame(variant: str, p: dict, x: list[tuple[int, int]], inverse: int) -> list[tuple[int, int]]:
    """The unscaled core's output frame, in natural order when ORDER = 0 and bit-reversed when ORDER = 1."""
    return fft_ref.fft_frame(variant, x, p["TW"], 0, p["RND"], inverse, 1 if p["ORDER"] == 0 else 0)


def frame(variant: str, p: dict, x: list[tuple[int, int]], inverse: int) -> list[tuple[int, int, int]]:
    """One output frame as the RTL presents it: (real, imaginary, exponent) per word, the exponent the same on every word of the frame; the true value of a word is
    (real + j imaginary) * 2**exponent. The exponent does not depend on the order, so a frame's words in the two orders differ only by the permutation."""
    y, s = fft_ref.bfp_normalise(core_frame(variant, p, x, inverse), p["W"], p["RND"])
    return [(a, b, s) for a, b in y]
