"""Bit-exact reference arithmetic for IEEE-754-style binary formats, shared by arith/fp_add, fp_mul and fp_fma (arith brief 139e).

A format is (EXP, MAN): EXP exponent bits, MAN stored fraction bits, 1 sign bit, W = 1 + EXP + MAN. binary32 is (8, 23), bfloat16 (8, 7), binary16 (5, 10);
(2, 2), (3, 2) and similar tiny formats are used to check every input. Values are Python integers (the bit pattern) and exact rationals (fractions.Fraction):
every operation is computed EXACTLY (no intermediate rounding) and rounded once, so the model is correct by construction and has no dependence on the
host's floating point. It is written from the IEEE 754-2019 text; Berkeley SoftFloat (BSD licence, www.jhauser.us/arithmetic/SoftFloat.html) is
cited as the usual software reference and none of its code was copied. The checks in tests/ are against NumPy's float32 and float16 (hardware IEEE) and against
an enumeration of every value of a tiny format.

Conventions (all of them stated in spec.md "what a user could guess wrong"):
  * rounding: round to nearest, ties to even, always. No other mode, no exception flags.
  * NaN: any NaN input, or an invalid operation (inf - inf, 0 * inf, 0 * inf + c), gives the canonical quiet NaN: sign 0, exponent all ones, fraction msb 1 and the
    rest 0. Payloads are not propagated and signs of NaNs are ignored.
  * infinity: exponent all ones, fraction 0. An overflowing result rounds to infinity (round-to-nearest).
  * subnormals (SUBNORM = 1): full gradual underflow as IEEE 754. SUBNORM = 0 is "flush to zero": a subnormal INPUT is read as a zero of the same sign
    (denormals-are-zero) and a result whose magnitude, rounded to MAN + 1 significant bits with an unbounded exponent range, is below the smallest normal
    number is replaced by a zero of the result's sign (tininess after rounding, as the RTL decides it).
  * zero results: an exact zero sum of nonzero operands of opposite sign is +0; (+0) + (-0) is +0; (-0) + (-0) is -0; a product's zero has the xor of the signs; a
    fused multiply-add whose product and addend are both zero takes their common sign, else +0; a nonzero exact result that rounds or flushes to zero keeps its sign.
"""
from __future__ import annotations

import random
from fractions import Fraction


class Fmt:
    def __init__(self, exp: int, man: int):
        self.exp, self.man = exp, man
        self.w = 1 + exp + man
        self.bias = (1 << (exp - 1)) - 1
        self.emax_field = (1 << exp) - 1                 # the all-ones exponent field: infinity and NaN
        self.emin = 1 - self.bias                        # unbiased exponent of the smallest normal number

    def qnan(self) -> int:
        return (self.emax_field << self.man) | (1 << (self.man - 1))

    def inf(self, sign: int) -> int:
        return (sign << (self.w - 1)) | (self.emax_field << self.man)

    def zero(self, sign: int) -> int:
        return sign << (self.w - 1)


def unpack(f: Fmt, x: int) -> tuple[int, int, int]:
    assert 0 <= x < 1 << f.w
    return x >> (f.w - 1), (x >> f.man) & f.emax_field, x & ((1 << f.man) - 1)


def classify(f: Fmt, x: int, subnorm: int) -> tuple[str, int, Fraction]:
    """('nan'|'inf'|'fin', sign, exact magnitude as a Fraction); a subnormal is a zero when subnorm = 0."""
    s, e, m = unpack(f, x)
    if e == f.emax_field:
        return ("nan" if m else "inf"), s, Fraction(0)
    if e == 0:
        if not subnorm or m == 0:
            return "fin", s, Fraction(0)
        return "fin", s, Fraction(m) * Fraction(2) ** (f.emin - f.man)
    return "fin", s, Fraction((1 << f.man) | m) * Fraction(2) ** (e - f.bias - f.man)


def _floor_log2(q: Fraction) -> int:
    """floor(log2 q) for a positive Fraction, exactly."""
    e = q.numerator.bit_length() - q.denominator.bit_length()
    if Fraction(2) ** e > q:
        e -= 1
    return e


def round_pack(f: Fmt, sign: int, q: Fraction, subnorm: int) -> int:
    """Round the exact magnitude q >= 0 to nearest-even in the format and pack it with `sign` (see the conventions above)."""
    if q == 0:
        return f.zero(sign)
    e = _floor_log2(q)
    qe = (max(e, f.emin) if subnorm else e) - f.man          # exponent of the last kept bit: clamped at the subnormal step, or unbounded for flush-to-zero
    n = q / Fraction(2) ** qe
    r = n.numerator // n.denominator
    rem = n - r
    if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and (r & 1)):
        r += 1
    if r >> (f.man + 1):                                      # the rounding carried out of the significand
        r >>= 1
        qe += 1
    if r >> f.man == 0:                                       # subnormal (only reachable with subnorm = 1)
        return (sign << (f.w - 1)) | r
    efield = qe + f.man + f.bias
    if efield >= f.emax_field:
        return f.inf(sign)
    if efield <= 0:                                           # flush to zero (subnorm = 0)
        return f.zero(sign)
    return (sign << (f.w - 1)) | (efield << f.man) | (r & ((1 << f.man) - 1))


def _signed(sign: int, q: Fraction) -> Fraction:
    return -q if sign else q


def fp_add(f: Fmt, subnorm: int, a: int, b: int) -> int:
    ka, sa, qa = classify(f, a, subnorm)
    kb, sb, qb = classify(f, b, subnorm)
    if ka == "nan" or kb == "nan":
        return f.qnan()
    if ka == "inf" or kb == "inf":
        if ka == "inf" and kb == "inf" and sa != sb:
            return f.qnan()
        return f.inf(sa if ka == "inf" else sb)
    q = _signed(sa, qa) + _signed(sb, qb)
    if q == 0:
        return f.zero(sa & sb if (qa == 0 and qb == 0) else 0)
    return round_pack(f, 1 if q < 0 else 0, abs(q), subnorm)


def fp_mul(f: Fmt, subnorm: int, a: int, b: int) -> int:
    ka, sa, qa = classify(f, a, subnorm)
    kb, sb, qb = classify(f, b, subnorm)
    s = sa ^ sb
    if ka == "nan" or kb == "nan":
        return f.qnan()
    if ka == "inf" or kb == "inf":
        if qa == 0 and ka != "inf" or qb == 0 and kb != "inf":      # infinity times a zero
            return f.qnan()
        return f.inf(s)
    return round_pack(f, s, qa * qb, subnorm)


def fp_fma(f: Fmt, subnorm: int, a: int, b: int, c: int) -> int:
    """a * b + c with one rounding."""
    ka, sa, qa = classify(f, a, subnorm)
    kb, sb, qb = classify(f, b, subnorm)
    kc, sc, qc = classify(f, c, subnorm)
    sp = sa ^ sb
    if "nan" in (ka, kb, kc):
        return f.qnan()
    a_zero, b_zero = ka == "fin" and qa == 0, kb == "fin" and qb == 0
    if (ka == "inf" and b_zero) or (kb == "inf" and a_zero):
        return f.qnan()
    if ka == "inf" or kb == "inf":
        if kc == "inf" and sc != sp:
            return f.qnan()
        return f.inf(sp)
    if kc == "inf":
        return f.inf(sc)
    prod = qa * qb
    q = _signed(sp, prod) + _signed(sc, qc)
    if q == 0:
        return f.zero(sp & sc if (prod == 0 and qc == 0) else 0)
    return round_pack(f, 1 if q < 0 else 0, abs(q), subnorm)


def fma_cascade(f: Fmt, subnorm: int, a: int, b: int, c: int) -> int:
    """The unfused multiply then add: the product is rounded to the format, then the sum is rounded again."""
    return fp_add(f, subnorm, fp_mul(f, subnorm, a, b), c)


# ---- an independent formulation of round-to-nearest-even, by enumeration (used by the tests on tiny formats) ------------
def finite_values(f: Fmt, subnorm: int) -> list[tuple[Fraction, int]]:
    """Every finite non-negative value of the format with its pattern (positive zero once). With subnorm = 0 the normal grid is EXTENDED downwards by eight binades
    (their patterns have an exponent field <= 0, so a caller can see which results are below the smallest normal number), which is the unbounded-exponent
    rounding that flush-to-zero is defined on."""
    out = [(Fraction(0), 0)]
    for e in range(0 if subnorm else -8, f.emax_field):
        for m in range(1 << f.man):
            if e == 0 and m == 0 and subnorm:
                continue
            p = (e << f.man) | m
            v = Fraction(m) * Fraction(2) ** (f.emin - f.man) if (e == 0 and subnorm) else Fraction((1 << f.man) | m) * Fraction(2) ** (e - f.bias - f.man)
            out.append((v, p))
    return sorted(out)


def nearest_even(f: Fmt, subnorm: int, q: Fraction, table: list | None = None) -> int | None:
    """The pattern of the finite value nearest to q >= 0 (ties to the even pattern), or None if q is beyond the rounding threshold of the largest finite number
    (where round-to-nearest overflows to infinity: at or above the midpoint between the largest finite value and the next power of two)."""
    t = table if table is not None else finite_values(f, subnorm)
    vmax = t[-1][0]
    ulp = vmax - t[-2][0]
    if q >= vmax + ulp / 2:
        return None
    best = None
    for v, p in t:
        d = abs(v - q)
        if best is None or d < best[0] or (d == best[0] and (p & 1) == 0 and (best[1] & 1) == 1):
            best = (d, p)
    return best[1]


# ---- classes of operands for stimulus --------------------------------------------------------------------------------
def edge_patterns(f: Fmt) -> list[int]:
    """Patterns where floating-point arithmetic breaks, for both signs: zeros, the smallest and largest subnormals, the smallest and largest normals, one and the
    neighbours of one, infinities, NaNs (quiet, signalling, with payload)."""
    out = set()
    for s in (0, 1):
        sh = s << (f.w - 1)
        one = f.bias << f.man
        out |= {sh, sh | 1, sh | ((1 << f.man) - 1), sh | (1 << f.man), sh | ((1 << f.man) + 1), sh | one, sh | (one + 1), sh | (one - 1),
                sh | ((f.emax_field - 1) << f.man), sh | (((f.emax_field - 1) << f.man) | ((1 << f.man) - 1)), sh | ((f.emax_field - 1) << f.man) | 1,
                sh | (f.emax_field << f.man), sh | (f.emax_field << f.man) | 1, sh | (f.emax_field << f.man) | (1 << (f.man - 1)),
                sh | (f.emax_field << f.man) | ((1 << f.man) - 1), sh | ((one << 1) & ((1 << (f.w - 1)) - 1)), sh | (one >> 1) | 0}
    return sorted(x & ((1 << f.w) - 1) for x in out)


def rand_pattern(rng: random.Random, f: Fmt, edges: list[int]) -> int:
    """A random pattern: a fifth an edge value, a fifth with the exponent field of an ordinary small range, a fifth with a mantissa that has trailing zeros
    (exact and tie cases), a fifth fully uniform, a fifth a subnormal."""
    r = rng.random()
    s = rng.getrandbits(1)
    if r < 0.15:
        return rng.choice(edges)
    if r < 0.35:
        lo = max(1, f.bias - 3)
        e = rng.randrange(lo, min(f.emax_field, f.bias + 4))
        return (s << (f.w - 1)) | (e << f.man) | rng.getrandbits(f.man)
    if r < 0.55:
        m = rng.getrandbits(f.man) & ~((1 << rng.randrange(f.man + 1)) - 1)
        return (s << (f.w - 1)) | (rng.randrange(0, f.emax_field) << f.man) | m
    if r < 0.70:
        return (s << (f.w - 1)) | rng.getrandbits(f.man) | (rng.randrange(0, 2) << f.man)         # subnormal or smallest normal
    return rng.getrandbits(f.w)


def near_pattern(rng: random.Random, f: Fmt, x: int) -> int:
    """A pattern close to -x or x in magnitude: the same exponent field or one apart, a mantissa that differs in the low bits (massive cancellation when added)."""
    s, e, m = unpack(f, x)
    e2 = max(0, min(f.emax_field - 1, e + rng.choice((-1, 0, 0, 1))))
    m2 = (m ^ rng.getrandbits(rng.randrange(1, f.man + 1))) & ((1 << f.man) - 1)
    return ((s ^ rng.choice((0, 1, 1))) << (f.w - 1)) | (e2 << f.man) | m2


def partner_pattern(rng: random.Random, f: Fmt, x: int) -> int:
    """A partner of x for a product: its exponent is chosen so that the product's exponent lands near the underflow, the subnormal step or the overflow limit."""
    _, e, _ = unpack(f, x)
    target = rng.choice((-f.man - 2, -f.man, -2, -1, 0, 1, 2, f.emax_field - 3, f.emax_field - 2, f.emax_field - 1, f.emax_field, rng.randrange(0, f.emax_field)))
    e2 = max(0, min(f.emax_field - 1, target - e + f.bias))
    return (rng.getrandbits(1) << (f.w - 1)) | (e2 << f.man) | rng.getrandbits(f.man)
