"""Reference and bit-exact models of the FFT suite (brief 148). Python integers only; NumPy is used by the tests as the independent check.

Conventions (the RTL equals these, bit for bit):
  * data: signed W-bit two's-complement real and imaginary parts; twiddle: signed TW bits with scale 2**(TW-2) (so +1.0 and -1.0 are exact, 0 is exact);
  * twiddle table: a master quarter-wave table of cos(2 pi i / 4096), i = 0..1024, correctly rounded to 30 fractional bits; a twiddle is that master value
    rounded half up to TW-2 fractional bits (so a double rounding, stated) and given its sign by the quadrant: the table is symmetric about zero;
  * rounding of a shift right by k: RND = 1 adds 2**(k-1) first (round half up), RND = 0 floors (truncation);
  * SCALE = 1 halves the result of every radix-2 add and subtract (total 1/N), SCALE = 0 does not (the word grows one bit per butterfly stage);
  * inverse transforms swap real and imaginary parts at the input and at the output: ifft(x) = swap(fft(swap(x))), conjugate-twiddle free.
"""
from __future__ import annotations

from decimal import Decimal, getcontext

MASTER_LOG = 12                      # the master circle has 4096 points
MASTER_FRAC = 30                     # fractional bits of the master table
QUARTER = 1 << (MASTER_LOG - 2)      # 1024


def _cos_table() -> list[int]:
    getcontext().prec = 60
    pi = Decimal("3.14159265358979323846264338327950288419716939937510582097494")
    out = []
    for i in range(QUARTER + 1):
        x = pi * i / (2 * QUARTER)            # i * 2 pi / 4096
        x2 = x * x
        term, s, k = Decimal(1), Decimal(1), 0
        while abs(term) > Decimal(10) ** -55:
            k += 2
            term = -term * x2 / (k * (k - 1))
            s += term
        v = s * (1 << MASTER_FRAC)
        out.append(int((v + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR")))
    return out


COS_MASTER = _cos_table()


def rshift_round(v: int, k: int, rnd: int) -> int:
    if k <= 0:
        return v << -k
    return (v + (1 << (k - 1)) >> k) if rnd else (v >> k)


def twiddle(idx: int, tw: int) -> tuple[int, int]:
    """(wr, wi) = (cos, -sin) of 2 pi idx / 4096, idx in 0..4095, as signed integers of scale 2**(tw-2)."""
    idx %= 1 << MASTER_LOG
    q, r = divmod(idx, QUARTER)
    sh = MASTER_FRAC - (tw - 2)
    assert sh >= 0, "TW is at most 32"

    def c(i: int) -> int:
        return (COS_MASTER[i] + (1 << (sh - 1)) >> sh) if sh else COS_MASTER[i]

    cr, sr = c(r), c(QUARTER - r)
    cos, sin = [(cr, sr), (-sr, cr), (-cr, -sr), (sr, -cr)][q]
    return cos, -sin


def tw_for(m: int, circle: int, tw: int) -> tuple[int, int]:
    """Twiddle exp(-j 2 pi m / circle), circle a power of two up to 4096."""
    return twiddle(m * ((1 << MASTER_LOG) // circle), tw)


def cmul_round(xr: int, xi: int, wr: int, wi: int, tw: int, rnd: int) -> tuple[int, int]:
    """(xr + j xi) * (wr + j wi), exact products, then one rounded shift by tw-2 (the twiddle scale)."""
    return rshift_round(xr * wr - xi * wi, tw - 2, rnd), rshift_round(xr * wi + xi * wr, tw - 2, rnd)


def bitrev(a: int, n: int) -> int:
    return int(format(a, f"0{n}b")[::-1], 2) if n else 0


def _bf(a, b, scale, rnd):
    s = (a[0] + b[0], a[1] + b[1])
    d = (a[0] - b[0], a[1] - b[1])
    if scale:
        s = (rshift_round(s[0], 1, rnd), rshift_round(s[1], 1, rnd))
        d = (rshift_round(d[0], 1, rnd), rshift_round(d[1], 1, rnd))
    return s, d


def sdf_frame(x: list[tuple[int, int]], tw: int, scale: int, rnd: int) -> list[tuple[int, int]]:
    """Radix-2^2 single-path delay feedback FFT of one frame: natural order in, BIT-REVERSED order out (before any inverse swap)."""
    n = len(x).bit_length() - 1
    assert 1 << n == len(x) and n >= 3
    cur, m = list(x), len(x)
    stage = 0
    while stage + 1 < n:                              # a pair of stages with block size m
        nxt = []
        for b0 in range(0, len(cur), m):
            blk = cur[b0:b0 + m]
            h = m // 2
            top, bot = zip(*[_bf(blk[i], blk[i + h], scale, rnd) for i in range(h)])
            u = list(top) + list(bot)                  # stage A output order: sums, then differences
            v = []
            q = m // 4
            for hh in range(2):
                half = u[hh * h:(hh + 1) * h]
                sums, difs = [], []
                for j in range(q):
                    a2, b2 = half[j], half[j + q]
                    if hh == 1:
                        b2 = (b2[1], -b2[0])           # times -j
                    s, d = _bf(a2, b2, scale, rnd)
                    sums.append(s)
                    difs.append(d)
                v += sums + difs
            if m >= 8:
                for t in range(m):
                    g, i = divmod(t, q)
                    k = 2 * (g & 1) + (g >> 1)
                    wr, wi = tw_for(k * i, m, tw)
                    v[t] = cmul_round(v[t][0], v[t][1], wr, wi, tw, rnd)
            nxt += v
        cur, m, stage = nxt, m // 4, stage + 2
    if stage < n:                                       # odd n: a last plain radix-2 stage, block size 2
        nxt = []
        for b0 in range(0, len(cur), 2):
            s, d = _bf(cur[b0], cur[b0 + 1], scale, rnd)
            nxt += [s, d]
        cur = nxt
    return cur


def burst_frame(x: list[tuple[int, int]], tw: int, scale: int, rnd: int) -> list[tuple[int, int]]:
    """In-place radix-2 decimation-in-frequency FFT (the burst variant): natural in, bit-reversed positions out. Every butterfly multiplies its difference by W_M^i
    (rounded; exact for i = 0)."""
    n = len(x).bit_length() - 1
    mem = list(x)
    m = len(x)
    while m >= 2:
        h = m // 2
        for b0 in range(0, len(mem), m):
            for i in range(h):
                s, d = _bf(mem[b0 + i], mem[b0 + i + h], scale, rnd)
                wr, wi = tw_for(i, m, tw)
                mem[b0 + i], mem[b0 + i + h] = s, cmul_round(d[0], d[1], wr, wi, tw, rnd)
        m = h
    return mem


def fft_frame(variant: str, x, tw, scale, rnd, inverse=0, natural=1):
    """One frame as the RTL outputs it: ``x`` is a list of (re, im); returns the output list in the order ORDER says."""
    xs = [(b, a) for a, b in x] if inverse else list(x)
    y = (sdf_frame if variant == "sdf" else burst_frame)(xs, tw, scale, rnd)
    n = len(x).bit_length() - 1
    if natural:
        y = [y[bitrev(k, n)] for k in range(len(x))]
    return [(b, a) for a, b in y] if inverse else y


def real_frame(variant: str, xr: list[int], tw: int, scale: int, rnd: int, natural: int = 1):
    """Real-input FFT of N real samples (xr) by an N/2 complex transform plus post-processing (see arith/fft/spec.md). Returns bins 0 .. N/2 as (re, im)."""
    nn = len(xr)
    z = [(xr[2 * i], xr[2 * i + 1]) for i in range(nn // 2)]
    zf = fft_frame(variant, z, tw, scale, rnd, 0, 1)
    return real_post(zf, nn, tw, scale, rnd)


def real_post(zf, nn, tw, scale, rnd):
    """X[k] = (Z[k] + conj Z[h-k]) / 2 + W_N^k * (-j) * (Z[k] - conj Z[h-k]) / 2, h = N/2, k = 0..h, from natural-order Z (scaled by the transform's own scaling).
    Even part E = (Z[k] + conj Z[h-k]), odd part O = (Z[k] - conj Z[h-k]) with the quarter turn folded in: -j*O = (O.im, -O.re). E and O are shifted right by 1 (SCALE = 0: X = E/2 + W (-j O)/2, the plain spectrum) or by 2 (SCALE = 1: the
    half-size transform was already scaled by 2/N, so the result is X / N like the complex transform's), rounded as RND says."""
    h = nn // 2
    out = []
    for k in range(h + 1):
        a = zf[k % h]
        b = zf[(h - k) % h]
        bc = (b[0], -b[1])
        e = (a[0] + bc[0], a[1] + bc[1])
        o = (a[0] - bc[0], a[1] - bc[1])
        e = (rshift_round(e[0], 1 + scale, rnd), rshift_round(e[1], 1 + scale, rnd))
        o = (rshift_round(o[0], 1 + scale, rnd), rshift_round(o[1], 1 + scale, rnd))
        jo = (o[1], -o[0])
        wr, wi = tw_for(k, nn, tw)
        p = cmul_round(jo[0], jo[1], wr, wi, tw, rnd)
        out.append((e[0] + p[0], e[1] + p[1]))
    return out


# ---- window multiplier and window coefficients ------------------------------------------------------------------------
def window_mul(x: int, w: int, ww: int, rnd: int) -> int:
    """round(x * w / 2**ww) for a signed x and an unsigned coefficient w of ww bits (RND = 1 half up, 0 floor)."""
    return rshift_round(x * w, ww, rnd)


def window_coeffs(kind: str, n: int, ww: int) -> list[int]:
    """Periodic (DFT-even) window of n points as unsigned ww-bit coefficients of scale 2**ww, rounded to nearest and clipped to 2**ww - 1 (so the peak 1.0 becomes 1 - 2**-ww)."""
    import math
    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        v = {"rect": 1.0, "hann": 0.5 - 0.5 * math.cos(ph), "hamming": 0.54 - 0.46 * math.cos(ph),
             "blackman": 0.42 - 0.5 * math.cos(ph) + 0.08 * math.cos(2 * ph)}[kind]
        out.append(min((1 << ww) - 1, max(0, int(v * (1 << ww) + 0.5))))
    return out


def to_signed(v: int, w: int) -> int:
    v &= (1 << w) - 1
    return v - (1 << w) if v >> (w - 1) else v


def to_unsigned(v: int, w: int) -> int:
    return v & ((1 << w) - 1)


# ---- block floating point (brief 161) ---------------------------------------------------------------------------------------
def bfp_exponent(words: list[tuple[int, int]], wo: int) -> int:
    """The frame exponent s: the smallest right shift (negative: a left shift) after which every part of every word fits wo signed bits.
    The OR of the ones-complement magnitudes (x for x >= 0, -x - 1 for x < 0) of all parts has bit length BL, so the largest part needs BL + 1 bits including the sign: s = BL + 1 - wo."""
    acc = 0
    for a, b in words:
        acc |= (a if a >= 0 else ~a) | (b if b >= 0 else ~b)
    return acc.bit_length() + 1 - wo


def bfp_normalise(words: list[tuple[int, int]], wo: int, rnd: int) -> tuple[list[tuple[int, int]], int]:
    """(output words, exponent s): every part shifted right by s (rounded half up when rnd = 1, floor otherwise; a negative s shifts left, exactly) and, when the rounding carries a
    positive part to 2**(wo-1), saturated to 2**(wo-1) - 1. The true (unscaled) value of a part is its output times 2**s, to within the stated error."""
    s = bfp_exponent(words, wo)
    hi = (1 << (wo - 1)) - 1

    def one(x: int) -> int:
        return x << -s if s <= 0 else min(hi, rshift_round(x, s, rnd))

    return [(one(a), one(b)) for a, b in words], s
