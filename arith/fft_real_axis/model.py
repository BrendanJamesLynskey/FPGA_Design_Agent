"""The AXI4-Stream wrapper of the real-input FFT adds no arithmetic: its model is fft_real's (arith/fft_real/model.py); this file packs the AXI words (arith brief 161)."""
from __future__ import annotations

from arith.fft_common.fft_ref import to_signed, to_unsigned
from arith.fft_real import model as real_model

frame = real_model.frame
out_width = real_model.out_width


def gap(logn: int) -> int:
    """The idle clocks the wrapper enforces after the last beat of a frame (the transform's measured rule)."""
    return (1 << logn) // 8


def pack_in(even: int, odd: int, w: int) -> int:
    """s_axis_tdata = {odd-indexed sample, even-indexed sample}, w bits each, two's complement."""
    return (to_unsigned(odd, w) << w) | to_unsigned(even, w)


def unpack_out(word: int, wx: int) -> tuple[int, int]:
    """(real, imaginary) as signed integers from m_axis_tdata = {imaginary, real}."""
    return to_signed(word & ((1 << wx) - 1), wx), to_signed(word >> wx, wx)
