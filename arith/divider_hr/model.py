"""Bit-exact model of the high-radix divider (brief 139c), written from spec.md alone.

``divide``: a and b are W-bit normalised significands (MSB set, so a / b is in (1/2, 2)). The result is Q = floor(a * 4**K / b), 2K + 1 bits, and
R = a * 4**K - Q * b, W bits, 0 <= R < b: an exact quotient with 2K fractional bits and the exact remainder.
``srt_trace`` is the radix-4 SRT recurrence with a carry-save remainder that ``divider_hr_iter`` / ``divider_hr_pipe`` implement, and ``cpa_trace``
the same digits with a carry-propagate remainder (``divider_hr_cpa``), with the register widths of the RTL asserted at every step. The digit
selection is the table ``THR``: for each of the eight values of the three divisor bits below the leading one, four thresholds on the 7-bit
estimate k = floor(32 * 4w) of the partial remainder (the sum of the two truncated carry-save words, in 1/8 units of 4w).
"""
from __future__ import annotations

import random

VARIANTS = {0: "srt4_iter", 1: "srt4_cpa", 2: "srt4_pipe"}

# THR[i] = (m_minus1, m_0, m_1, m_2): digit q is the largest with k >= m_q (-2 if k < m_minus1). Derived by exhaustive search, see
# derive_thresholds(), and checked at every step of every trace.
THR = [(-13, -5, 3, 12), (-15, -6, 4, 14), (-16, -6, 4, 15), (-18, -7, 4, 16), (-20, -8, 5, 18), (-21, -8, 5, 19), (-23, -9, 5, 20), (-25, -10, 6, 22)]


def select(i: int, k: int) -> int:
    m1n, m0, m1, m2 = THR[i]
    return 2 if k >= m2 else 1 if k >= m1 else 0 if k >= m0 else -1 if k >= m1n else -2


def derive_thresholds() -> list[tuple[int, int, int, int]]:
    """Exhaustive search with exact fractions: for each divisor interval i and each estimate k (4w in [k/8, k/8 + 1/4)), the digits q with
    |4w - q*B| <= (2/3) * B for every divisor B in the interval and every 4w in the box that is reachable (|4w| <= (8/3) * B); the thresholds
    are the lowest k at which each digit is the largest feasible one. Returns THR."""
    from fractions import Fraction as Fr
    res = Fr(2, 3)

    def feasible(bl, bh, lo, hi, q):
        pts = {bl, bh}
        for v in (lo, hi, -lo, -hi):
            b = v * Fr(3, 8)
            if bl < b < bh:
                pts.add(b)
        for b in pts:
            xl, xh = max(lo, -Fr(8, 3) * b), min(hi, Fr(8, 3) * b)
            if xl >= xh:
                continue
            if (q - res) * b > xl or xh > (q + res) * b:
                return False
        return True

    out = []
    for i in range(8):
        bl, bh = 1 + Fr(i, 8), 1 + Fr(i + 1, 8)
        seq = []
        for k in range(-48, 48):
            lo, hi = Fr(k, 8), Fr(k + 2, 8)
            if hi <= -Fr(8, 3) * bh or lo >= Fr(8, 3) * bh:
                continue
            f = [q for q in (-2, -1, 0, 1, 2) if feasible(bl, bh, lo, hi, q)]
            assert f, (i, k)
            seq.append((k, max(f)))
        assert all(seq[j][1] <= seq[j + 1][1] for j in range(len(seq) - 1))
        out.append(tuple(min(k for k, q in seq if q >= d) for d in (-1, 0, 1, 2)))
    return out


def qw(k: int) -> int:
    return 2 * k + 1


def divide(a: int, b: int, w: int, k: int) -> tuple[int, int]:
    """The function. a and b must be W-bit with the MSB set."""
    assert w >= 7 and k >= 1 and 1 << (w - 1) <= a < 1 << w and 1 << (w - 1) <= b < 1 << w
    q, r = divmod(a << (2 * k), b)
    return q, r


def _signed(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _digit_inputs(a: int, b: int, w: int):
    return (b >> (w - 4)) & 7


def _otf(q: int, qq: int, qm: int, m: int) -> tuple[int, int]:
    """On-the-fly conversion of one digit: Q' = 4Q + q and QM' = Q' - 1 without a carry-propagate add (mod 2**QW)."""
    qs = [qq, qm]
    msk = (1 << m) - 1
    if q == 2:
        return ((qq << 2) | 2) & msk, ((qq << 2) | 1) & msk
    if q == 1:
        return ((qq << 2) | 1) & msk, (qq << 2) & msk
    if q == 0:
        return (qq << 2) & msk, ((qm << 2) | 3) & msk
    if q == -1:
        return ((qm << 2) | 3) & msk, ((qm << 2) | 2) & msk
    return ((qm << 2) | 2) & msk, ((qm << 2) | 1) & msk


def srt_trace(a: int, b: int, w: int, k: int) -> list[dict]:
    """Carry-save radix-4 SRT, K + 1 steps (the first digit is the integer part, 0..2). Returns one record per step with the digit and the carry-save words
    (W + 3 bits each) and asserts |u| <= 2b/3 after every step, the estimate error (0 or 1 unit), the digit range, and at the end the exact result."""
    assert w >= 7
    ww, msk, m = w + 3, (1 << (w + 3)) - 1, qw(k)
    i = _digit_inputs(a, b, w)
    us, uc, qq, qm = a, 0, 0, (1 << m) - 1
    prev = 0
    recs = []
    for j in range(k + 1):
        if j == 0:
            xs, xc, est = us, 0, a >> (w - 4)
        else:
            xs, xc = (us << 2) & msk, (uc << 2) & msk
            est = _signed(((us >> (w - 6)) & 127) + ((uc >> (w - 6)) & 127), 7)
        q = select(i, est)
        assert -2 <= q <= 2 and (j > 0 or q >= 0)
        mb = abs(q) * b
        if q > 0:
            z, cin = (~mb) & msk, 1
        elif q < 0:
            z, cin = mb & msk, 0
        else:
            z, cin = 0, 0
        s = xs ^ xc ^ z
        c = ((((xs & xc) | (xs & z) | (xc & z)) << 1) & msk) | cin
        us, uc = s, c
        u = _signed(us + uc, ww)
        qq, qm = _otf(q, qq, qm, m)
        assert 3 * abs(u) <= 2 * b, ("partial remainder left the convergence bound", a, b, j, u)
        if j > 0:
            assert u == 4 * prev - q * b                                   # the carry-save step is exact (mod 2**(W+3), and the value fits)
            assert (prev >> (w - 6)) - est in (0, 1), (a, b, j)             # the estimate is the true floor(4w * 8) or one unit below
        prev = u
        recs.append({"digit": q, "us": us, "uc": uc, "u": u, "q": qq, "qm": qm, "est": est})
    u = _signed(us + uc, ww)
    neg = u < 0
    quo, rem = (qm if neg else qq), ((u + b) if neg else u)
    assert 0 <= rem < b and (quo, rem) == divide(a, b, w, k) and quo < 1 << m
    return recs


def cpa_trace(a: int, b: int, w: int, k: int) -> list[dict]:
    """Same digit selection with a W + 1 bit two's-complement partial remainder from a carry-propagate adder (estimate error 0)."""
    m = qw(k)
    i = _digit_inputs(a, b, w)
    u, qq, qm, recs = a, 0, (1 << m) - 1, []
    for j in range(k + 1):
        x = a if j == 0 else u << 2
        est = (a >> (w - 4)) if j == 0 else _signed(u >> (w - 6), 7)
        q = select(i, est)
        u = x - q * b
        assert -(1 << w) <= u < 1 << w and 3 * abs(u) <= 2 * b
        qq, qm = _otf(q, qq, qm, m)
        recs.append({"digit": q, "u": u, "q": qq, "qm": qm, "est": est})
    neg = u < 0
    quo, rem = (qm if neg else qq), ((u + b) if neg else u)
    assert (quo, rem) == divide(a, b, w, k)
    return recs


def latency(variant: int, w: int, k: int, pipe: int = 1) -> int:
    """srt4_iter and srt4_cpa: K + 3 (K + 1 steps, one clock to load, one to fix). srt4_pipe: ceil((K + 1) / PIPE) + 1."""
    return k + 3 if variant in (0, 1) else -(-(k + 1) // pipe) + 1


def throughput_clocks(variant: int, w: int, k: int) -> int:
    return k + 3 if variant in (0, 1) else 1


def out_width(w: int, k: int) -> int:
    return 2 * k + 1 + w


def normalised(w: int) -> range:
    return range(1 << (w - 1), 1 << w)


def edge_values(w: int) -> list[int]:
    lo, hi = 1 << (w - 1), (1 << w) - 1
    s = {lo, lo + 1, hi, hi - 1, (lo * 3) // 2, (lo * 4) // 3 + 1, (lo * 5) // 3, lo + (lo >> 1) - 1, lo + (lo >> 2), hi - (lo >> 3)}
    return sorted(v for v in s if lo <= v <= hi)


def inputs(w: int, k: int, count: int | None = None, seed: int = 1) -> list[int]:
    """Packed in_data = {a, b}; exhaustive over both normalised operands when count is None."""
    if count is None:
        return [(a << w) | b for a in normalised(w) for b in normalised(w)]
    rng = random.Random(seed)
    ev = edge_values(w)
    out = [(a << w) | b for a in ev for b in ev]
    lo, hi = 1 << (w - 1), (1 << w) - 1
    while len(out) < count:
        r = rng.random()
        if r < 0.25:                                                 # a / b near the digit-selection boundaries: ratio close to 2/3, 4/3, 1 and exact multiples
            b = rng.randrange(lo, hi + 1)
            ratio = rng.choice((2 / 3, 5 / 3, 1.0, 0.5, 4 / 3, 1.999999, 0.500001))
            a = min(max(int(b * ratio) + rng.choice((-1, 0, 1)), lo), hi)
        elif r < 0.35:
            b = rng.randrange(lo, hi + 1)
            a = min(max(b, lo), hi) if rng.random() < 0.5 else rng.randrange(lo, hi + 1)
        else:
            a, b = rng.randrange(lo, hi + 1), rng.randrange(lo, hi + 1)
        out.append((a << w) | b)
    return out[:count]


def stream(w: int, k: int, count: int | None = None, seed: int = 1) -> tuple[list[int], list[int]]:
    vin = inputs(w, k, count, seed)
    msk = (1 << w) - 1
    exp = []
    for v in vin:
        q, r = divide(v >> w, v & msk, w, k)
        exp.append((q << w) | r)                                    # out_data = {Q, R}
    return vin, exp
