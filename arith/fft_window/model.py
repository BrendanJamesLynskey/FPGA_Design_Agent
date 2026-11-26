"""Bit-exact model of the window multiplier (arith brief 148): see arith/fft_common/fft_ref.py."""
from __future__ import annotations

from arith.fft_common import fft_ref


def window(wd: int, ww: int, rnd: int, xr: int, xi: int, w: int) -> tuple[int, int]:
    f = fft_ref
    return (f.to_unsigned(f.window_mul(f.to_signed(xr, wd), w, ww, rnd), wd), f.to_unsigned(f.window_mul(f.to_signed(xi, wd), w, ww, rnd), wd))
