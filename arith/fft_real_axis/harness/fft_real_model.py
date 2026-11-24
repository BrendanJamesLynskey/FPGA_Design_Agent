"""Bit-exact model of the real-input FFT (arith brief 148): see arith/fft_common/fft_ref.py (real_frame, real_post) for the arithmetic."""
from __future__ import annotations

import fft_ref


def out_width(w: int, logn: int, scale: int) -> int:
    return w + 1 if scale else w + logn + 1


def frame(p: dict, x: list[int]) -> list[tuple[int, int]]:
    """Bins 0 .. N/2 of N real samples (signed integers), as the RTL outputs them."""
    return fft_ref.real_frame("sdf", x, p["TW"], p["SCALE"], p["RND"], 1)
