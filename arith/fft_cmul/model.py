"""Bit-exact model of the complex multiplier (arith brief 148): the exact product of two complex numbers with signed parts, as Python integers."""
from __future__ import annotations

from arith.fft_common.fft_ref import to_signed, to_unsigned


def cmul(wa: int, wb: int, ar: int, ai: int, br: int, bi: int) -> tuple[int, int]:
    """Inputs and outputs are bit patterns (unsigned integers of WA, WB and WA+WB+1 bits); the product is exact."""
    ar, ai, br, bi = to_signed(ar, wa), to_signed(ai, wa), to_signed(br, wb), to_signed(bi, wb)
    w = wa + wb + 1
    return to_unsigned(ar * br - ai * bi, w), to_unsigned(ar * bi + ai * br, w)


def cmul3(wa: int, wb: int, ar: int, ai: int, br: int, bi: int) -> tuple[int, int]:
    """The three-multiplication identity, evaluated in Python integers (the second formulation the model is checked against)."""
    ar, ai, br, bi = to_signed(ar, wa), to_signed(ai, wa), to_signed(br, wb), to_signed(bi, wb)
    k1 = br * (ar + ai)
    w = wa + wb + 1
    return to_unsigned(k1 - ai * (br + bi), w), to_unsigned(k1 + ar * (bi - br), w)
