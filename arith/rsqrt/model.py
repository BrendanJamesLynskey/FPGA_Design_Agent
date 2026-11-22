"""Bit-exact model of the reciprocal square root (brief 139c), written from spec.md alone.

``rsqrt``: x is a W-bit word with 2 integer bits and W - 2 fractional bits, X = x / 2**(W-2) in [1, 4) (so 2**(W-2) <= x < 2**W): the
significand of a floating-point value with the exponent made even. The result Y approximates 1 / sqrt(X) in (1/2, 1] with W fractional bits:
Y_exact = 2**W / sqrt(X); Y is an integer in [2**(W-1), 2**W] (W + 1 bits; 2**W only for X = 1). Variants: the seed table alone, the table plus
one Newton iteration, the table plus two. All arithmetic is integer with floor shifts, as in the RTL; the error is measured against the exact
value, never assumed.

Seed table: ``seed(F, A, idx)`` = floor(2**F / sqrt(X_mid)) for the interval idx of width 2**-A of X in [1, 4) (3 * 2**A intervals), X_mid its
midpoint, by integer arithmetic only: isqrt(2**(2F+A+1) // M), M = 2**(A+1) + 2*idx + 1.
Newton step (F = W + 2 guard bits): s = (y * y) >> F; t = x * s; d = (2**(W-2+F) - t) >> (W-2)  (the residual 1 - X*y*y in units of 2**-F);
y' = y + ((y * d) >> (F + 1)). The exact-arithmetic map y -> y * (3 - X * y**2) / 2 never exceeds 1 / sqrt(X) and has error 3/2 e**2.
"""
from __future__ import annotations

import math
import random
from fractions import Fraction

VARIANTS = {0: "table", 1: "nr1", 2: "nr2"}
GUARD = 2


def iters(variant: int) -> int:
    return variant


def frac_bits(w: int, variant: int) -> int:
    return w if variant == 0 else w + GUARD


def table_size(a: int) -> int:
    return 3 << a


def seed(f: int, a: int, idx: int) -> int:
    m = (1 << (a + 1)) + 2 * idx + 1
    return math.isqrt((1 << (2 * f + a + 1)) // m)


def index(x: int, w: int, a: int) -> int:
    return (x >> (w - 2 - a)) - (1 << a)


def newton_step(x: int, y: int, w: int, f: int) -> tuple[int, int, int]:
    """(y', d, s)."""
    s = (y * y) >> f
    t = x * s
    d = ((1 << (w - 2 + f)) - t) >> (w - 2)
    return y + ((y * d) >> (f + 1)), d, s


def dw(w: int, a: int, variant: int) -> int:
    """Width of the signed residual word d: |d| < 2**(F - A + 1) (measured, asserted at every step)."""
    return frac_bits(w, variant) - a + 2


def rsqrt(x: int, w: int, a: int, variant: int) -> int:
    assert w >= 8 and 2 <= a <= w - 3 and 1 << (w - 2) <= x < 1 << w and variant in VARIANTS
    f = frac_bits(w, variant)
    y = seed(f, a, index(x, w, a))
    for _ in range(iters(variant)):
        y, d, s = newton_step(x, y, w, f)
        assert -(1 << (dw(w, a, variant) - 1)) <= d < 1 << (dw(w, a, variant) - 1), ("residual left its word", x, d)
        assert 0 <= s <= 1 << f
        assert 0 <= y <= 1 << f, (x, y)
    return y >> (f - w)


def exact(x: int, w: int) -> Fraction:
    """2**W / sqrt(x / 2**(W-2)) to 2**-64."""
    n = 1 << (3 * w - 2)                                # Y_exact**2 = 2**(3W-2) / x
    return Fraction(math.isqrt((n << 128) // x), 1 << 64)


def error(x: int, w: int, y: int) -> Fraction:
    """Y_exact - Y in units of the last place (2**-W)."""
    return exact(x, w) - y


def latency(variant: int, w: int = 0, a: int = 0) -> int:
    """Register stages: 1 (the table) + 5 per Newton step (square, multiply by x, residual, multiply, add)."""
    return 1 + 5 * iters(variant)


def out_width(w: int) -> int:
    return w + 1


def values(w: int) -> range:
    return range(1 << (w - 2), 1 << w)


def edge_values(w: int, a: int) -> list[int]:
    lo, hi = 1 << (w - 2), (1 << w) - 1
    s = {lo, lo + 1, hi, hi - 1, 1 << (w - 1), (1 << (w - 1)) - 1, (1 << (w - 1)) + 1}
    step = 1 << (w - 2 - a)
    for i in range(0, 3 << a, max(1, (3 << a) // 24)):
        for d in (-1, 0, 1):
            v = lo + i * step + d
            if lo <= v <= hi:
                s.add(v)
    return sorted(s)


def inputs(w: int, a: int, count: int | None = None, seed_: int = 1) -> list[int]:
    if count is None:
        return list(values(w))
    rng = random.Random(seed_)
    out = edge_values(w, a)
    while len(out) < count:
        out.append(rng.randrange(1 << (w - 2), 1 << w))
    return out[:count]


def stream(w: int, a: int, variant: int, count: int | None = None, seed_: int = 1) -> tuple[list[int], list[int]]:
    xs = inputs(w, a, count, seed_)
    return xs, [rsqrt(x, w, a, variant) for x in xs]


def error_range(w: int, a: int, variant: int, vals=None) -> tuple[Fraction, Fraction]:
    lo = hi = None
    for x in (vals if vals is not None else values(w)):
        e = error(x, w, rsqrt(x, w, a, variant))
        lo = e if lo is None or e < lo else lo
        hi = e if hi is None or e > hi else hi
    return lo, hi
