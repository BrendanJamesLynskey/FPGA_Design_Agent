"""Bit-exact model of the twiddle generator (arith brief 148): see arith/fft_common/fft_ref.py for the table and the rounding."""
from __future__ import annotations

from arith.fft_common import fft_ref


def twiddle(logc: int, tw: int, m: int) -> tuple[int, int]:
    """(wr, wi) as bit patterns of TW bits: cos and -sin of 2 pi m / 2**logc, scale 2**(tw-2)."""
    wr, wi = fft_ref.tw_for(m, 1 << logc, tw)
    return fft_ref.to_unsigned(wr, tw), fft_ref.to_unsigned(wi, tw)
