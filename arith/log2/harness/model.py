"""Bit-exact models of the log2 function on a mantissa (arith/log2/spec.md), brief 139d.

Input x: an unsigned IW-bit fraction, the mantissa m = 1 + x / 2**IW in [1, 2). Output y: an unsigned OW-bit fraction, log2(m) = y / 2**OW in [0, 1), rounded
to nearest (ties upward) and clamped to [0, 2**OW - 1]. Each variant has its own rounding steps, so each has its own model; they are not equal to each other
(spec.yaml states each one's error against the exact function, in units of the last place of y).

``compute(variant, p, x)`` returns y. ``ideal`` is the exact function, unrounded, in units of the last place; ``max_error`` scans every input."""
from __future__ import annotations

import math

import fxlib

FUNC = "log2"


def ideal(p: dict, x: int) -> float:
    """The exact log2(1 + x/2**IW), in units of 2**-OW (not rounded)."""
    return math.log2(1.0 + x / (1 << p["IW"])) * (1 << p["OW"])


def compute(variant: str, p: dict, x: int) -> int:
    iw, ow = p["IW"], p["OW"]
    assert 0 <= x < 1 << iw
    hi = (1 << ow) - 1
    if variant == "table":
        r = fxlib.rom_direct(FUNC)[x << (fxlib.DIRECT_BITS - iw)]
        return fxlib.clamp(fxlib.rnd(r, fxlib.CF - ow), 0, hi)
    if variant in ("lerp", "poly2"):
        sb = p["SB"]
        db = iw - sb
        i, d = x >> db, x & ((1 << db) - 1)
        if variant == "lerp":
            c0, s1 = fxlib.rom_lerp(FUNC, sb)
            return fxlib.lerp_eval(c0[i], s1[i], d, db, ow, hi)
        a0, a1, a2 = fxlib.rom_poly(FUNC, sb)
        return fxlib.poly2_eval(a0[i], a1[i], a2[i], d, db, ow, hi)
    if variant == "cordic":      # hyperbolic vectoring: z -> atanh((m-1)/(m+1)); ln m = 2 z; log2 m = z * 2 / ln 2
        nit, g = p["NIT"], p["G"]
        df = ow + g
        xx = (2 << df) + (x << (df - iw))
        yy = x << (df - iw)
        z = 0
        for i in fxlib.hyp_seq(nit):
            d = 1 if yy < 0 else -1
            xx, yy, z = xx + d * (yy >> i), yy + d * (xx >> i), z - d * fxlib.rnd(fxlib.atanh_q(i), fxlib.TQ - df)
        return fxlib.clamp(fxlib.rnd(z * fxlib.fl(2.0 / math.log(2.0), fxlib.CQ), fxlib.CQ + g), 0, hi)
    raise KeyError(variant)


def step(variant: str, p: dict):
    def f(v):
        return {"y": compute(variant, p, v["x"])}
    return f


def input_bits(p: dict) -> int:
    return p["IW"]


def max_error(variant: str, p: dict) -> dict:
    """{"y": the largest |compute - ideal| over every input, in units of the last place of y}."""
    return {"y": max(abs(compute(variant, p, x) - ideal(p, x)) for x in range(1 << p["IW"]))}


ERR_KEYS = {"y": "ERR_MILLI"}


def checker_params(variant: str, p: dict, err_ulp: float | None = None) -> dict:
    """Extra parameters of the harness's SystemVerilog checker: its error bound in 1/1000 ulp (default: this variant's measured maximum at these parameters plus 0.05)."""
    e = {"y": err_ulp} if err_ulp is not None else {k: v + 0.05 for k, v in max_error(variant, p).items()}
    return {ERR_KEYS[k]: int(round(v * 1000)) for k, v in e.items()}


LATENCY = {"table": lambda p: p["REG"], "lerp": lambda p: 2, "poly2": lambda p: 3, "cordic": lambda p: p["NIT"] + 1}
