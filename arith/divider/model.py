"""Bit-exact model of the divider function (brief 139b), written from spec.md alone.

``divide`` is the specification: unsigned W-bit N / D, quotient Q and remainder R, both W bits; D = 0 gives Q = 2**W - 1 and R = N
(the RISC-V convention; the spec says it). ``restoring_trace`` and ``nonrestoring_trace`` are the two digit recurrences the RTL variants
implement, step by step with the register widths of the RTL, so a variant's intermediate values can be compared as well as its result.
``latency`` is the exact clock count of every variant (checked against the simulation by the testbench).
"""
from __future__ import annotations

import random

VARIANTS = {0: "restoring_iter", 1: "nonrestoring_iter", 2: "restoring_pipe", 3: "nonrestoring_pipe"}


def divide(n: int, d: int, w: int) -> tuple[int, int]:
    """The function: Q, R for unsigned W-bit n and d (n and d are range-checked)."""
    assert 0 <= n < 1 << w and 0 <= d < 1 << w
    if d == 0:
        return (1 << w) - 1, n
    return n // d, n % d


def restoring_trace(n: int, d: int, w: int) -> list[tuple[int, int]]:
    """Partial remainder (W bits) and quotient-so-far after each of the W iterations of restoring division."""
    p, q, out = 0, 0, []
    for i in range(w - 1, -1, -1):
        sh = (p << 1) | ((n >> i) & 1)
        assert sh < 1 << w                              # so the trial subtraction needs W + 1 bits, not W + 2
        if sh >= d:
            p, q = sh - d, (q << 1) | 1
        else:
            p, q = sh, q << 1
        out.append((p, q))
    return out


def nonrestoring_trace(n: int, d: int, w: int) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """Signed partial remainder (W+1 bits two's complement, as a Python int) and quotient after each iteration; then the corrected (Q, R)."""
    p, q, out = 0, 0, []
    for i in range(w - 1, -1, -1):
        sh = (p << 1) | ((n >> i) & 1)
        t = sh + d if p < 0 else sh - d
        assert -(1 << w) <= t < (1 << w), "partial remainder left W+1 signed bits"
        p, q = t, (q << 1) | (1 if t >= 0 else 0)
        out.append((p, q))
    if p < 0:
        p += d
    return out, (q, p)


def latency(variant: int, w: int, pipe: int = 1) -> int:
    """Clock edges from the accepting edge to the edge that samples out_valid."""
    if variant == 0:
        return w + 1
    if variant == 1:
        return w + 2
    return -(-w // pipe)        # variants 2 and 3: ceil(W / PIPE)


def throughput_clocks(variant: int, w: int) -> int:
    """Clocks between accepted inputs: one for the pipelines; the whole run for an iterative divider."""
    return {0: w + 1, 1: w + 2}.get(variant, 1)


def edge_values(w: int) -> list[int]:
    m = (1 << w) - 1
    return sorted({0, 1, 2, 3, m, m - 1, m >> 1, (m >> 1) + 1, (m >> 1) - 1, 1 << (w - 1), (1 << (w - 1)) + 1})


def vectors(w: int, count: int | None = None, seed: int = 1) -> list[tuple[int, int]]:
    """Exhaustive for w <= 6 when count is None (or large); otherwise edge pairs, then random pairs with divisors of assorted size."""
    if count is None:
        if w > 8:
            raise ValueError("exhaustive vectors only up to w = 8")
        return [(n, d) for n in range(1 << w) for d in range(1 << w)]
    rng = random.Random(seed)
    e = edge_values(w)
    out = [(a, b) for a in e for b in e]
    while len(out) < count:
        bits = rng.randint(1, w)                     # a divisor of any magnitude, so small divisors (long quotients) are common
        d = rng.getrandbits(bits)
        out.append((rng.getrandbits(w), d))
    return out[:count]


def pack_in(n: int, d: int, w: int) -> int:
    return (n << w) | d                                # in_data = {n, d}


def pack_out(q: int, r: int, w: int) -> int:
    return (q << w) | r                                # out_data = {q, r}


def stream(w: int, count: int | None = None, seed: int = 1) -> tuple[list[int], list[int]]:
    vs = vectors(w, count, seed)
    return [pack_in(n, d, w) for n, d in vs], [pack_out(*divide(n, d, w), w) for n, d in vs]
