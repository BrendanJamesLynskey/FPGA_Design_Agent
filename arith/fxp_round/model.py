"""Bit-exact model of the fixed-point rounding and saturation function (brief 139b), written from spec.md alone.

Input: a signed W_IN-bit integer x (two's complement). Drop the S low (fractional) bits with a rounding mode, then fit the result to a
signed W_OUT-bit integer by wrapping or saturating. Modes: 0 truncate (round toward minus infinity: the arithmetic shift), 1 round half
up (ties toward plus infinity), 2 convergent (ties to the even result). ``fold_add`` is the single-adder form the RTL uses: add a constant
and, for convergent, the bit that will be the result's LSB as a carry-in, then drop the S low bits.
"""
from __future__ import annotations

import random

VARIANTS = {0: "fold_add", 1: "inc_after", 2: "two_stage"}
MODES = {0: "truncate", 1: "round_half_up", 2: "convergent"}


def to_signed(v: int, w: int) -> int:
    v &= (1 << w) - 1
    return v - (1 << w) if v >> (w - 1) else v


def rnd(x: int, s: int, mode: int) -> int:
    """The specification of rounding, with exact integers: the integer nearest x / 2**s by the mode."""
    if s == 0:
        return x
    fl, rem, half = x >> s, x & ((1 << s) - 1), 1 << (s - 1)       # Python's >> is the arithmetic (floor) shift
    if mode == 0:
        return fl
    if mode == 1:
        return fl + (1 if rem >= half else 0)
    if rem > half or (rem == half and (fl & 1)):                   # convergent: a tie goes to the even result
        return fl + 1
    return fl


def fold_add(x: int, s: int, mode: int) -> int:
    """The RTL's form: one addition with a mode constant and a carry-in, then an arithmetic shift. Equal to rnd for every x."""
    if s == 0:
        return x
    half = 1 << (s - 1)
    const, cin = {0: (0, 0), 1: (half, 0), 2: (half - 1, (x >> s) & 1)}[mode]
    return (x + const + cin) >> s


def fit(r: int, w_out: int, sat: int) -> int:
    lo, hi = -(1 << (w_out - 1)), (1 << (w_out - 1)) - 1
    if sat:
        return max(lo, min(hi, r))
    return to_signed(r, w_out)


def fxp_round(x: int, w_in: int, s: int, w_out: int, mode: int, sat: int) -> int:
    assert -(1 << (w_in - 1)) <= x < (1 << (w_in - 1)) and 0 <= s < w_in and w_out >= 2
    return fit(rnd(x, s, mode), w_out, sat)


def latency(variant: int) -> int:
    return 2 if variant == 2 else 1


def error_bound_lsb(mode: int) -> tuple[int, int]:
    """(numerator, denominator) of the largest |round(x) - x / 2**s| in output LSBs, before saturation: truncate 1 (strictly less), half-up 1/2, convergent 1/2."""
    return (1, 1) if mode == 0 else (1, 2)


def edge_values(w: int) -> list[int]:
    lo, hi = -(1 << (w - 1)), (1 << (w - 1)) - 1
    return sorted({lo, lo + 1, -2, -1, 0, 1, 2, hi - 1, hi, lo // 2, hi // 2})


def inputs(w_in: int, count: int | None = None, seed: int = 1) -> list[int]:
    """Every x (as an unsigned bit pattern) when count is None, else edge values plus random values with random numbers of low-bit structure (ties are common)."""
    if count is None:
        return list(range(1 << w_in))
    rng = random.Random(seed)
    out = [v & ((1 << w_in) - 1) for v in edge_values(w_in)]
    while len(out) < count:
        v = rng.getrandbits(w_in)
        k = rng.randint(0, w_in)
        out.append(((v >> k) << k) | ((1 << (k - 1)) if k else 0) if rng.random() < 0.4 else v)   # a tie pattern: ...1000 in the low k bits
    return [v & ((1 << w_in) - 1) for v in out[:count]]


def stream(w_in: int, s: int, w_out: int, mode: int, sat: int, count: int | None = None, seed: int = 1) -> tuple[list[int], list[int]]:
    xs = inputs(w_in, count, seed)
    return xs, [fxp_round(to_signed(v, w_in), w_in, s, w_out, mode, sat) & ((1 << w_out) - 1) for v in xs]
