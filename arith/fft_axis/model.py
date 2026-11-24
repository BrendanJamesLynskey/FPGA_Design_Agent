"""The AXI4-Stream wrapper adds no arithmetic: its model is the FFT variant's (arith/fft/model.py); this file maps the wrapper's variant names to it and packs AXI words."""
from __future__ import annotations

from arith.fft import model as fft_model
from arith.fft_common.fft_ref import to_unsigned

frame = fft_model.frame
out_width = fft_model.out_width


def pack(im: int, re: int, w: int) -> int:
    """tdata = {imaginary, real}, each w bits, two's complement."""
    return (to_unsigned(im, w) << w) | to_unsigned(re, w)


def unpack(word: int, w: int) -> tuple[int, int]:
    """(real, imaginary) as signed integers from tdata."""
    from arith.fft_common.fft_ref import to_signed
    return to_signed(word & ((1 << w) - 1), w), to_signed(word >> w, w)
