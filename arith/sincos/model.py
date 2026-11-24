"""Bit-exact models of sine and cosine of a phase (arith/sincos/spec.md), brief 139d.

Input phase: an unsigned PH-bit fraction of a turn (phase / 2**PH turns, so 2**PH is a full circle). Outputs s and c: signed OW-bit two's complement numbers,
sin and cos of 2 pi phase / 2**PH scaled by 2**(OW-1), each rounded to nearest (ties upward) and limited to [-(2**(OW-1) - 1), 2**(OW-1) - 1]: +1.0 is
represented as 2**(OW-1) - 1, one place below its exact scaled value. The top two phase bits select the quadrant; the remaining K = PH - 2 bits o give the
angle inside the first quadrant, which every variant evaluates (sine and cosine of a quarter turn times o / 2**K, as non-negative values) before the
quadrant map: q = 0: (s, c) = (S, C); 1: (C, -S); 2: (-S, -C); 3: (-C, S).

Variants: ``lerp`` (table plus linear interpolation), ``poly2`` (table plus quadratic, Horner) and ``cordic`` (rotation mode, one iteration per clock); each has
its own rounding steps, so each has its own model."""
from __future__ import annotations

import math

from arith.tools import fxlib


def ideal(p: dict, phase: int) -> tuple[float, float]:
    """The exact (sin, cos) of the phase, scaled by 2**(OW-1), not rounded."""
    a = 2.0 * math.pi * phase / (1 << p["PH"])
    sc = 1 << (p["OW"] - 1)
    return math.sin(a) * sc, math.cos(a) * sc


def quarter(variant: str, p: dict, o: int) -> tuple[int, int]:
    """(S, C): the non-negative sine and cosine of the quarter-turn angle o / 2**(PH - 2) of a quarter turn, scaled by 2**(OW-1)."""
    ph, ow = p["PH"], p["OW"]
    k = ph - 2
    fb = ow - 1
    hi = (1 << fb) - 1
    if variant in ("lerp", "poly2"):
        sb = p["SB"]
        db = k - sb
        i, d = o >> db, o & ((1 << db) - 1)
        if variant == "lerp":
            s0, s1 = fxlib.rom_lerp("sinq", sb)
            c0, c1 = fxlib.rom_lerp("cosq", sb)
            return fxlib.lerp_eval(s0[i], s1[i], d, db, fb, hi), fxlib.lerp_eval(c0[i], c1[i], d, db, fb, hi)
        sa = fxlib.rom_poly("sinq", sb)
        ca = fxlib.rom_poly("cosq", sb)
        return (fxlib.poly2_eval(sa[0][i], sa[1][i], sa[2][i], d, db, fb, hi), fxlib.poly2_eval(ca[0][i], ca[1][i], ca[2][i], d, db, fb, hi))
    if variant == "cordic":
        nit, g = p["NIT"], p["G"]
        df, zf = fb + g, ph + g
        x = fxlib.rnd(fxlib.kinv_circ(nit, fxlib.TQ), fxlib.TQ - df)
        y = 0
        z = o << (zf - ph)                                  # o / 2**PH turns
        for i in range(nit):
            d = 1 if z >= 0 else -1
            x, y, z = x - d * (y >> i), y + d * (x >> i), z - d * fxlib.rnd(fxlib.atan_turn_q(i), fxlib.TQ - zf)
        return fxlib.clamp(fxlib.rnd(y, g), 0, hi), fxlib.clamp(fxlib.rnd(x, g), 0, hi)
    raise KeyError(variant)


def compute(variant: str, p: dict, phase: int) -> tuple[int, int]:
    """(s, c) as signed Python integers."""
    ph = p["PH"]
    assert 0 <= phase < 1 << ph
    q, o = phase >> (ph - 2), phase & ((1 << (ph - 2)) - 1)
    s, c = quarter(variant, p, o)
    return ((s, c), (c, -s), (-s, -c), (-c, s))[q]


def pattern(v: int, w: int) -> int:
    return v & ((1 << w) - 1)


def step(variant: str, p: dict):
    def f(v):
        s, c = compute(variant, p, v["phase"])
        return {"s": pattern(s, p["OW"]), "c": pattern(c, p["OW"])}
    return f


def input_bits(p: dict) -> int:
    return p["PH"]


def max_error(variant: str, p: dict) -> dict:
    """{"sc": the largest |output - exact| over every phase and both outputs, in units of the last place}."""
    m = 0.0
    for ph in range(1 << p["PH"]):
        s, c = compute(variant, p, ph)
        es, ec = ideal(p, ph)
        m = max(m, abs(s - es), abs(c - ec))
    return {"sc": m}


ERR_KEYS = {"sc": "ERR_MILLI"}


def checker_params(variant: str, p: dict, err_ulp: float | None = None) -> dict:
    """Extra parameters of the harness's SystemVerilog checker: its error bound in 1/1000 ulp (default: this variant's measured maximum at these parameters plus 0.05)."""
    e = {"sc": err_ulp} if err_ulp is not None else {k: v + 0.05 for k, v in max_error(variant, p).items()}
    return {ERR_KEYS[k]: int(round(v * 1000)) for k, v in e.items()}


LATENCY = {"lerp": lambda p: 2, "poly2": lambda p: 3, "cordic": lambda p: p["NIT"]}
