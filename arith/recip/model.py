"""Bit-exact model of the reciprocal (brief 139c), written from spec.md alone.

``recip``: b is a W-bit normalised significand (MSB set, B = b / 2**(W-1) in [1, 2)). The result Y approximates 1 / B in (1/2, 1] with W
fractional bits: the exact value is Y_exact = 2**(2W-1) / b, and Y is an integer in [2**(W-1), 2**W] (W + 1 bits; 2**W only for B = 1).
Three variants: the seed table alone, the table plus one Newton iteration, the table plus two. All arithmetic is integer with floor
shifts, as in the RTL, and the error Y_exact - Y is measured against exact rational arithmetic (``error``), never assumed.

Seed table: ``seed(F, A, idx)`` = round(2**F / B_mid) for the interval idx of the A bits below the leading one, B_mid its midpoint, computed with
integers only (the RTL computes the same constant at elaboration): ((2**(F+A+2)) + num) // (2 * num), num = 2**(A+1) + 2*idx + 1.
Newton step (y of F bits, F = W + 2 guard bits): t = b * y; d = ((2**(W-1+F)) - t) >> (W-1)  (the residual 1 - B*y in units of 2**-F, floor);
y' = y + ((y * d) >> F). The exact-arithmetic map y -> y * (2 - B * y) never exceeds 1/B and squares the relative error.
"""
from __future__ import annotations

import random
from fractions import Fraction

VARIANTS = {0: "table", 1: "nr1", 2: "nr2"}
GUARD = 2


def iters(variant: int) -> int:
    return variant


def frac_bits(w: int, variant: int) -> int:
    """F, the fractional bits of y inside the datapath: W for the table alone, W + GUARD with a Newton step."""
    return w if variant == 0 else w + GUARD


def seed(f: int, a: int, idx: int) -> int:
    num = (1 << (a + 1)) + 2 * idx + 1
    return ((1 << (f + a + 2)) + num) // (2 * num)


def index(b: int, w: int, a: int) -> int:
    return (b >> (w - 1 - a)) & ((1 << a) - 1)


def newton_step(b: int, y: int, w: int, f: int) -> tuple[int, int]:
    """(y', d): d is the residual word (signed)."""
    t = b * y
    d = ((1 << (w - 1 + f)) - t) >> (w - 1)
    return y + ((y * d) >> f), d


def dw(w: int, a: int, variant: int) -> int:
    """Width of the signed residual word d (bits), from the measured range: |d| < 2**(F - A) for the first step and smaller after."""
    return frac_bits(w, variant) - a + 1


def recip(b: int, w: int, a: int, variant: int) -> int:
    assert w >= 8 and 2 <= a <= w - 2 and 1 << (w - 1) <= b < 1 << w and variant in VARIANTS
    f = frac_bits(w, variant)
    y = seed(f, a, index(b, w, a))
    for _ in range(iters(variant)):
        y, d = newton_step(b, y, w, f)
        assert -(1 << (dw(w, a, variant) - 1)) <= d < 1 << (dw(w, a, variant) - 1), ("residual left its word", b, d)
        assert 0 <= y <= 1 << f
    return y >> (f - w)


def exact_num_den(b: int, w: int) -> tuple[int, int]:
    return 1 << (2 * w - 1), b


def error(b: int, w: int, y: int) -> Fraction:
    """Y_exact - Y in units of the last place (2**-W), exact rational."""
    return Fraction(1 << (2 * w - 1), b) - y


def latency(variant: int, w: int = 0, a: int = 0) -> int:
    """Register stages from input to output: 1 (the table) + 4 per Newton step (multiply, residual, multiply, add)."""
    return 1 + 4 * iters(variant)


def throughput_clocks(variant: int) -> int:
    return 1


def out_width(w: int) -> int:
    return w + 1


def normalised(w: int) -> range:
    return range(1 << (w - 1), 1 << w)


def edge_values(w: int, a: int) -> list[int]:
    lo, hi = 1 << (w - 1), (1 << w) - 1
    s = {lo, lo + 1, hi, hi - 1, (3 * lo) // 2}
    step = 1 << (w - 1 - a)
    for i in range(0, 1 << a, max(1, (1 << a) // 16)):          # interval boundaries of the seed table
        for d in (-1, 0, 1):
            v = lo + i * step + d
            if lo <= v <= hi:
                s.add(v)
    return sorted(s)


def inputs(w: int, a: int, count: int | None = None, seed_: int = 1) -> list[int]:
    if count is None:
        return list(normalised(w))
    rng = random.Random(seed_)
    out = edge_values(w, a)
    while len(out) < count:
        out.append(rng.randrange(1 << (w - 1), 1 << w))
    return out[:count]


def stream(w: int, a: int, variant: int, count: int | None = None, seed_: int = 1) -> tuple[list[int], list[int]]:
    xs = inputs(w, a, count, seed_)
    return xs, [recip(b, w, a, variant) for b in xs]


def error_range(w: int, a: int, variant: int, values=None) -> tuple[Fraction, Fraction]:
    """(min, max) of Y_exact - Y in ulp over all normalised b (or the given values)."""
    lo = hi = None
    for b in (values if values is not None else normalised(w)):
        e = error(b, w, recip(b, w, a, variant))
        lo = e if lo is None or e < lo else lo
        hi = e if hi is None or e > hi else hi
    return lo, hi
