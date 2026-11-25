"""Model of the AXI4-Stream 2-parallel FFT with block floating point (arith brief 168): the unscaled 2-parallel transform of arith/fft_mdc2 (SCALE = 0, W + LOGN bit parts), then one exponent per frame and
every part shifted to W bits (arith/fft_common/fft_ref.py: bfp_normalise, the same rule as arith/fft_bfp). The wrapper adds no arithmetic; this file packs the AXI words. Python integers only."""
from __future__ import annotations

from arith.fft_common import fft_ref
from arith.fft_common.fft_ref import to_signed, to_unsigned


def exp_width(w: int, logn: int) -> int:
    return (2 * w + logn - 1).bit_length() + 1            # $clog2(2 * W + LOGN) + 1


def gap(logn: int) -> int:
    """The idle clocks between two frames that the core needs when they are not back to back: N/8 (0 is also allowed)."""
    return (1 << logn) // 8


def frame(p: dict, x: list[tuple[int, int]], inverse: int) -> tuple[list[tuple[int, int, int, int]], int]:
    """One output frame as the stream presents it: (beats, exponent). Beat k is (re0, im0, re1, im1) = X[k] and X[k + N/2] normalised to W bits, k = 0 .. N/2 - 1 (natural order); the true value of
    every part is part * 2**exponent, to within the error stated in arith/fft_bfp/spec.md (the core is that of arith/fft_mdc2 at SCALE = 0)."""
    words = fft_ref.mdc2_frame(x, p["TW"], 0, p["RND"], inverse, 1)
    h = len(words)
    nat = [(a, b) for a, b, _, _ in words] + [(c, d) for _, _, c, d in words]
    y, s = fft_ref.bfp_normalise(nat, p["W"], p["RND"])
    return [(y[k][0], y[k][1], y[k + h][0], y[k + h][1]) for k in range(h)], s


def pack_in(s0: tuple[int, int], s1: tuple[int, int], w: int) -> int:
    """s_axis_tdata = {im1, re1, im0, re0}, w bits each, two's complement; s0 = x[2m] = (re, im) in the low half, s1 = x[2m + 1] in the high half."""
    return (to_unsigned(s1[1], w) << (3 * w)) | (to_unsigned(s1[0], w) << (2 * w)) | (to_unsigned(s0[1], w) << w) | to_unsigned(s0[0], w)


def pack_beats(x: list[tuple[int, int]], w: int) -> list[int]:
    return [pack_in(x[2 * m], x[2 * m + 1], w) for m in range(len(x) // 2)]


def unpack_out(word: int, w: int) -> tuple[int, int, int, int]:
    """(re0, im0, re1, im1) as signed integers from m_axis_tdata = {im1, re1, im0, re0}."""
    return tuple(to_signed(word >> (i * w), w) for i in range(4))
