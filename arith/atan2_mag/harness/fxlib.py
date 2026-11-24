"""Fixed-point plumbing shared by the elementary-function models (arith brief 139d): rounding, clamping, the constant tables of the table-plus-polynomial
variants and of the CORDIC variants, and the table-plus-polynomial arithmetic itself. Pure Python integers; the one place the constants are defined, so a
model, the generated RTL tables (arith/tools/gen_rtl.py) and the tests cannot disagree.

Conventions (written into every spec.yaml):
  * table and polynomial variants store coefficients with CF = 20 fractional bits (22-bit signed); the datapath keeps CF + DB fractional bits and rounds
    once, to nearest with ties upward, at the end (``rnd``);
  * CORDIC constants are stored with TQ = 28 fractional bits and rounded once more to the datapath's own fractional bits (``rnd`` again);
  * ``>>`` on a negative Python integer is an arithmetic (floor) shift, as ``>>>`` on a signed SystemVerilog vector."""
from __future__ import annotations

import math
from functools import lru_cache

CF = 20           # fractional bits of the table / polynomial coefficients
TQ = 28           # fractional bits of the CORDIC constants
KQ = 18           # fractional bits of the magnitude gain constant (atan2_mag)
CQ = 20           # fractional bits of the ln 2 and 2 / ln 2 constants of the exp2 / log2 CORDIC variants


def rnd(v: int, s: int) -> int:
    """v / 2**s rounded to nearest, ties toward +infinity (add half, then arithmetic shift); s = 0 returns v."""
    return v if s <= 0 else (v + (1 << (s - 1))) >> s


def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def to_signed(x: int, w: int) -> int:
    return x - (1 << w) if x >> (w - 1) else x


def fl(v: float, bits: int) -> int:
    """round(v * 2**bits), ties upward, from a double (53 bits, so the rounding of a 20 to 28-bit constant is not ambiguous in practice)."""
    return int(math.floor(v * (1 << bits) + 0.5))


# ---- the four functions of the table variants, on u in [0, 1) ---------------------------------------------------------------------------------
FUNCS = {
    "exp2": lambda u: 2.0 ** u - 1.0,                  # 2**u - 1: the fractional part of 2**x for x in [0, 1)
    "log2": lambda u: math.log2(1.0 + u),              # log2 of the mantissa 1 + u
    "sinq": lambda u: math.sin(math.pi / 2 * u),       # sine over a quarter turn, u = fraction of the quarter
    "cosq": lambda u: math.cos(math.pi / 2 * u),
}
SB_LERP = (3, 4, 5, 6)         # segment bits the generated lerp tables cover
SB_POLY = (3, 4, 5)            # segment bits the generated polynomial tables cover
DIRECT_BITS = 8                # the direct table has 2**8 entries; narrower inputs use every 2**(8 - IW)-th


@lru_cache(None)
def rom_direct(f: str) -> tuple:
    return tuple(fl(FUNCS[f](k / (1 << DIRECT_BITS)), CF) for k in range(1 << DIRECT_BITS))


@lru_cache(None)
def rom_lerp(f: str, sb: int) -> tuple:
    """(c0, s1): c0[i] = f(i/N) and s1[i] = f((i+1)/N) - f(i/N), both rounded to CF bits, N = 2**sb: the table is exact at its break points."""
    n = 1 << sb
    v = [fl(FUNCS[f](i / n), CF) for i in range(n + 1)]
    return tuple(v[:n]), tuple(v[i + 1] - v[i] for i in range(n))


def _solve3(a, b):
    """Solve the 3 x 3 system a x = b by Gaussian elimination with partial pivoting."""
    m = [row[:] + [bb] for row, bb in zip(a, b)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(3):
            if r != c:
                k = m[r][c] / m[c][c]
                m[r] = [x - k * y for x, y in zip(m[r], m[c])]
    return [m[i][3] / m[i][i] for i in range(3)]


@lru_cache(None)
def rom_poly(f: str, sb: int) -> tuple:
    """(a0, a1, a2): per segment i the quadratic a0 + a1 t + a2 t**2 in t = (position inside the segment) in [0, 1), interpolating f at the three Chebyshev nodes
    of the segment (near-minimax), the coefficients rounded to CF bits."""
    n = 1 << sb
    ts = [0.5 + 0.5 * math.cos((2 * k + 1) * math.pi / 6) for k in range(3)]
    a0, a1, a2 = [], [], []
    for i in range(n):
        c = _solve3([[1.0, t, t * t] for t in ts], [FUNCS[f]((i + t) / n) for t in ts])
        a0.append(fl(c[0], CF))
        a1.append(fl(c[1], CF))
        a2.append(fl(c[2], CF))
    return tuple(a0), tuple(a1), tuple(a2)


def lerp_eval(c0: int, s1: int, d: int, db: int, fb: int, hi: int) -> int:
    """y = c0 + s1 * d / 2**db, rounded once to fb fractional bits and clamped to [0, hi]."""
    return clamp(rnd((c0 << db) + s1 * d, CF + db - fb), 0, hi)


def poly2_eval(a0: int, a1: int, a2: int, d: int, db: int, fb: int, hi: int) -> int:
    """Horner in integers: p1 = (a2 d) >> db (floor), q = a1 + p1, acc = q d + a0 2**db, rounded once to fb fractional bits and clamped to [0, hi]."""
    p1 = (a2 * d) >> db
    q = a1 + p1
    return clamp(rnd(q * d + (a0 << db), CF + db - fb), 0, hi)


# ---- CORDIC constants -------------------------------------------------------------------------------------------------------------------------
def atan_turn_q(i: int) -> int:
    """atan(2**-i) in turns (divided by 2 pi), TQ fractional bits."""
    return fl(math.atan(2.0 ** -i) / (2 * math.pi), TQ)


def atanh_q(i: int) -> int:
    """atanh(2**-i) in radians, TQ fractional bits (i >= 1)."""
    return fl(math.atanh(2.0 ** -i), TQ)


def hyp_seq(n: int) -> list[int]:
    """The shift of each of the first n hyperbolic CORDIC iterations: 1, 2, 3, 4, 4, 5, ..., 13, 13, 14, ... (4, 13 and 40 are repeated for convergence)."""
    s, i = [], 1
    while len(s) < n:
        s.append(i)
        if i in (4, 13, 40) and s.count(i) == 1:
            s.append(i)
        i += 1
    return s[:n]


def kinv_circ(n: int, bits: int) -> int:
    """1 / prod_{i<n} sqrt(1 + 2**-2i), the inverse circular CORDIC gain of n iterations, ``bits`` fractional bits."""
    k = 1.0
    for i in range(n):
        k *= math.sqrt(1.0 + 4.0 ** -i)
    return fl(1.0 / k, bits)


def kinv_hyp(n: int, bits: int) -> int:
    """1 / prod sqrt(1 - 2**-2i) over the first n hyperbolic iterations (repeats included): the inverse hyperbolic gain, ``bits`` fractional bits."""
    k = 1.0
    for i in hyp_seq(n):
        k *= math.sqrt(1.0 - 4.0 ** -i)
    return fl(1.0 / k, bits)


# ---- the SystemVerilog side: constants as case tables ------------------------------------------------------------------------------------
def sv_case_function(name: str, width: int, key_width: int, items: list[tuple[int, int]], signed: bool = False, argname: str = "k") -> str:
    """A SystemVerilog function with a case table, for the generated RTL: ``items`` is (key, value) pairs; the function returns ``width`` bits (signed if asked);
    keys not listed return 0."""
    ty = f"logic signed [{width - 1}:0]" if signed else f"logic [{width - 1}:0]"
    L = [f"    function automatic {ty} {name}(input logic [{key_width - 1}:0] {argname});", f"        case ({argname})"]
    for k, v in items:
        lit = (f"-{width}'sd{-v}" if v < 0 else f"{width}'sd{v}") if signed else f"{width}'d{v}"
        L.append(f"            {key_width}'d{k}: {name} = {lit};")
    L += ["            default: " + name + " = '0;", "        endcase", "    endfunction"]
    return "\n".join(L)
