"""Bit-exact model of the reciprocal-multiply divider (brief 139c), written from spec.md alone.

``quotient``: a and b are W-bit normalised significands (MSB set, a / b in (1/2, 2)). The result Q approximates a * 2**(W-1) / b, a W-bit
integer with W - 1 fractional bits (exact value Q_exact = a * 2**(W-1) / b, a real number); there is no remainder. Two variants with the same
multiplier count and different structure: Newton-Raphson (a reciprocal from the table and IT Newton steps, then one multiply by a; the steps
are in series) and Goldschmidt (a and b are both multiplied by the same factors 2 - D, so the two multiplies of an iteration are independent).
Everything is integer arithmetic with floor shifts, F = W + 2 guard bits, exactly as in the RTL; the error Q_exact - Q is measured against the
exact quotient, never assumed.

Newton: y = seed(b); IT times (t = b * y; d = (2**(W-1+F) - t) >> (W-1); y = y + ((y * d) >> F)); Q = (a * y) >> F.
Goldschmidt: y = seed(b); n = (a * y) >> (W-1); dd = (b * y) >> (W-1); IT times (r = 2**(F+1) - dd; n = (n * r) >> F; dd = (dd * r) >> F, the last
iteration's dd update omitted); Q = n >> (F - (W - 1)).
The seed table and Newton step are those of arith/recip (model.seed, model.newton_step), written out again here so the function stands alone.
"""
from __future__ import annotations

import random
from fractions import Fraction

VARIANTS = {0: "newton", 1: "goldschmidt"}
GUARD = 2


def frac_bits(w: int) -> int:
    return w + GUARD


def seed(f: int, ab: int, idx: int) -> int:
    num = (1 << (ab + 1)) + 2 * idx + 1
    return ((1 << (f + ab + 2)) + num) // (2 * num)


def index(b: int, w: int, ab: int) -> int:
    return (b >> (w - 1 - ab)) & ((1 << ab) - 1)


def dw(w: int, ab: int) -> int:
    return frac_bits(w) - ab + 1


def quotient(a: int, b: int, w: int, ab: int, it: int, variant: int) -> int:
    assert w >= 8 and 2 <= ab <= w - 2 and it >= 1 and 1 << (w - 1) <= a < 1 << w and 1 << (w - 1) <= b < 1 << w and variant in VARIANTS
    f = frac_bits(w)
    y = seed(f, ab, index(b, w, ab))
    if variant == 0:
        for _ in range(it):
            t = b * y
            d = ((1 << (w - 1 + f)) - t) >> (w - 1)
            assert -(1 << (dw(w, ab) - 1)) <= d < 1 << (dw(w, ab) - 1), ("residual left its word", b, d)
            y = y + ((y * d) >> f)
            assert 0 <= y <= 1 << f
        q = (a * y) >> f
    else:
        n = (a * y) >> (w - 1)
        dd = (b * y) >> (w - 1)
        assert n < 1 << (f + 2) and dd < 1 << (f + 1)
        for k in range(it):
            r = (1 << (f + 1)) - dd
            assert 0 < r < 1 << (f + 1)
            n = (n * r) >> f
            assert n < 1 << (f + 2)
            if k < it - 1:
                dd = (dd * r) >> f
                assert dd < 1 << (f + 1)
        q = n >> (f - (w - 1))
    assert 0 <= q < 1 << w
    return q


def exact(a: int, b: int, w: int) -> Fraction:
    return Fraction(a << (w - 1), b)


def error(a: int, b: int, w: int, q: int) -> Fraction:
    return exact(a, b, w) - q


def latency(variant: int, it: int) -> int:
    """Newton: 1 (seed) + 4 per step + 1 (the multiply by a). Goldschmidt: 1 (seed) + 1 (the two first multiplies) + 2 per iteration (residual, multiply)."""
    return 2 + 4 * it if variant == 0 else 2 + 2 * it


def multipliers(variant: int, it: int) -> int:
    """DSP multipliers in the datapath: Newton 2 per step + 1; Goldschmidt 2 + (2 * IT - 1)."""
    return 2 * it + 1


def out_width(w: int) -> int:
    return w


def normalised(w: int) -> range:
    return range(1 << (w - 1), 1 << w)


def edge_values(w: int, ab: int) -> list[int]:
    lo, hi = 1 << (w - 1), (1 << w) - 1
    s = {lo, lo + 1, hi, hi - 1, (3 * lo) // 2, (lo * 4) // 3 + 1, (lo * 5) // 3}
    step = 1 << (w - 1 - ab)
    for i in range(0, 1 << ab, max(1, (1 << ab) // 12)):
        for d in (-1, 0, 1):
            v = lo + i * step + d
            if lo <= v <= hi:
                s.add(v)
    return sorted(s)


def inputs(w: int, ab: int, count: int | None = None, seed_: int = 1) -> list[int]:
    """Packed in_data = {a, b}; every pair when count is None."""
    if count is None:
        return [(a << w) | b for a in normalised(w) for b in normalised(w)]
    rng = random.Random(seed_)
    ev = edge_values(w, ab)
    out = [(a << w) | b for a in ev[::2] for b in ev[::2]]
    lo, hi = 1 << (w - 1), (1 << w) - 1
    while len(out) < count:
        out.append((rng.randrange(lo, hi + 1) << w) | rng.randrange(lo, hi + 1))
    return out[:count]


def stream(w: int, ab: int, it: int, variant: int, count: int | None = None, seed_: int = 1) -> tuple[list[int], list[int]]:
    vin = inputs(w, ab, count, seed_)
    msk = (1 << w) - 1
    return vin, [quotient(v >> w, v & msk, w, ab, it, variant) for v in vin]


def error_range(w: int, ab: int, it: int, variant: int, pairs) -> tuple[Fraction, Fraction]:
    lo = hi = None
    for a, b in pairs:
        e = error(a, b, w, quotient(a, b, w, ab, it, variant))
        lo = e if lo is None or e < lo else lo
        hi = e if hi is None or e > hi else hi
    return lo, hi
