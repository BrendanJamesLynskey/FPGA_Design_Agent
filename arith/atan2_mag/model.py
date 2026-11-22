"""Bit-exact model of atan2 and vector magnitude by CORDIC in vectoring mode (arith/atan2_mag/spec.md), brief 139d.

Inputs x and y: W-bit two's complement. Outputs: ang, an unsigned PH-bit fraction of a turn, atan2(y, x) / (2 pi) modulo 1 rounded to nearest (ties upward);
mag, an unsigned W-bit number, sqrt(x**2 + y**2) rounded to nearest and clamped to [0, 2**W - 1]. For x = y = 0 the result is mag 0 and the angle the model
returns (pinned by ``compute``: the CORDIC iterations alternate), not a defined angle.

The vector is first reflected into the half plane x >= 0 (negate both when x < 0, add half a turn to the angle), then NIT iterations rotate it onto the x
axis (sigma = +1 when y >= 0, rotating clockwise by atan(2**-i)), accumulating the angle in turns; the final x is the magnitude times the CORDIC gain, and is
multiplied by the constant 1 / gain (KQ = 18 fractional bits). The two variants, ``cordic`` (a register after every iteration) and ``cordic_g2`` (a register
after every GRP iterations), compute the same numbers and differ only in latency and combinational depth."""
from __future__ import annotations

import math

from arith.tools import fxlib


def ideal(p: dict, x: int, y: int) -> tuple[float, float]:
    """(angle in units of 2**-PH turns, in [0, 2**PH), magnitude), exact, not rounded."""
    w, ph = p["W"], p["PH"]
    xs, ys = fxlib.to_signed(x, w), fxlib.to_signed(y, w)
    a = math.atan2(ys, xs) / (2 * math.pi)
    return (a % 1.0) * (1 << ph), math.hypot(xs, ys)


def compute(variant: str, p: dict, x: int, y: int) -> tuple[int, int]:
    """(ang, mag)."""
    w, ph, nit, g = p["W"], p["PH"], p["NIT"], p["G"]
    xs, ys = fxlib.to_signed(x, w), fxlib.to_signed(y, w)
    off = 0
    if xs < 0:
        xs, ys, off = -xs, -ys, 1 << (ph - 1)
    zf = ph + g
    X, Y, Z = xs << g, ys << g, 0
    for i in range(nit):
        s = 1 if Y >= 0 else -1
        X, Y, Z = X + s * (Y >> i), Y - s * (X >> i), Z + s * fxlib.rnd(fxlib.atan_turn_q(i), fxlib.TQ - zf)
    ang = (fxlib.rnd(Z, g) + off) & ((1 << ph) - 1)
    mag = fxlib.clamp(fxlib.rnd(X * fxlib.kinv_circ(nit, fxlib.KQ), fxlib.KQ + g), 0, (1 << w) - 1)
    return ang, mag


def step(variant: str, p: dict):
    def f(v):
        a, m = compute(variant, p, v["x"], v["y"])
        return {"ang": a, "mag": m}
    return f


def angle_error(p: dict, got: int, want: float) -> float:
    """The circular difference of two angles in units of the last place."""
    d = abs(got - want) % (1 << p["PH"])
    return min(d, (1 << p["PH"]) - d)


def input_bits(p: dict) -> int:
    return 2 * p["W"]


def max_error(variant: str, p: dict) -> dict:
    """{"ang": largest angle error, "mag": largest magnitude error} over every input, in last places; the origin is left out (its angle is not defined)."""
    ea = em = 0.0
    n = 1 << p["W"]
    for x in range(n):
        for y in range(n):
            if fxlib.to_signed(x, p["W"]) == 0 and fxlib.to_signed(y, p["W"]) == 0:
                continue
            a, m = compute(variant, p, x, y)
            ia, im = ideal(p, x, y)
            ea, em = max(ea, angle_error(p, a, ia)), max(em, abs(m - im))
    return {"ang": ea, "mag": em}


ERR_KEYS = {"ang": "ERR_MILLI", "mag": "ERR_MAG_MILLI"}


def max_error_sampled(variant: str, p: dict, n: int = 30000) -> dict:
    """The same maxima over a sample: every vector with both coordinates in [-32, 32) (the hardest for the angle) and n seeded random vectors. For W too large to scan."""
    import random
    rng = random.Random(139)
    w = p["W"]
    m = (1 << w) - 1
    ea = em = 0.0
    pts = [((x & m), (y & m)) for x in range(-32, 32) for y in range(-32, 32)] + [(rng.getrandbits(w), rng.getrandbits(w)) for _ in range(n)]
    for x, y in pts:
        if fxlib.to_signed(x, w) == 0 and fxlib.to_signed(y, w) == 0:
            continue
        a, mg = compute(variant, p, x, y)
        ia, im = ideal(p, x, y)
        ea, em = max(ea, angle_error(p, a, ia)), max(em, abs(mg - im))
    return {"ang": ea, "mag": em}


def checker_params(variant: str, p: dict, err_ulp: float | None = None) -> dict:
    """Extra parameters of the harness's SystemVerilog checker: its angle and magnitude error bounds in 1/1000 ulp. Default: this variant's measured maxima at these
    parameters plus 0.05 when W <= 7 (every input scanned), else the maxima over a sample (see max_error_sampled) plus 0.25; pass --err-ulp to state your own."""
    if err_ulp is not None:
        e = {k: err_ulp for k in ERR_KEYS}
    elif p["W"] <= 7:
        e = {k: v + 0.05 for k, v in max_error(variant, p).items()}
    else:
        e = {k: v + 0.25 for k, v in max_error_sampled(variant, p).items()}
    return {ERR_KEYS[k]: int(round(v * 1000)) for k, v in e.items()}


LATENCY = {"cordic": lambda p: p["NIT"] + 2, "cordic_g2": lambda p: -(-p["NIT"] // p["GRP"]) + 2}
