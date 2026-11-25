"""Bit-exact model of the configurable FFT (arith brief 148): see arith/fft_common/fft_ref.py for the arithmetic and the conventions."""
from __future__ import annotations

from arith.fft_common import fft_ref

VARIANT = {"sdf": "sdf", "burst": "burst"}


def out_width(w: int, logn: int, scale: int) -> int:
    return w if scale else w + logn


def frame(variant: str, p: dict, x: list[tuple[int, int]], inverse: int) -> list[tuple[int, int]]:
    """One frame as the RTL outputs it (signed integers): natural order when ORDER = 0, bit-reversed when ORDER = 1."""
    return fft_ref.fft_frame(VARIANT[variant], x, p["TW"], p["SCALE"], p["RND"], inverse, 1 if p["ORDER"] == 0 else 0)
