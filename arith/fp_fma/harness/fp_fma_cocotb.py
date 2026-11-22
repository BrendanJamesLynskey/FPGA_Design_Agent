"""cocotb bench of the fused multiply-add and its unfused cascade against fp_fma/model.py (arith brief 139e).

The model is chosen by the parameter set: `fma` (one rounding) when it has STAGES (the fused variant), `cascade` (two roundings) when it has STAGES_M. `exhaustive` drives every (a, b, c) triple of a point (3 * (1 + EXP + MAN) up to 18 bits); `randomised` drives edge patterns (zeros, subnormals, extremes,
infinities, NaNs) in all three operands, products that nearly cancel the addend, addends of the exponent of the product, exact-tie products with an addend far below them (the sticky bit), and ARITH_N random triples."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

import fp_ref
import model
import bench


def step(p):
    fn = model.cascade if "STAGES_M" in p else model.fma

    def f(v):
        return {"y": fn(p["EXP"], p["MAN"], p["SUBNORM"], v["a"], v["b"], v["c"])}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    w = 1 + p["EXP"] + p["MAN"]
    assert 3 * w <= 18
    await bench.start(dut)
    vs = [{"a": a, "b": b, "c": c} for a, b, c in itertools.product(range(1 << w), repeat=3)]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"exhaustive {p}")


def _addend_near_product(rng, f, a, b, edges):
    """A c whose magnitude is close to a * b (massive cancellation when the signs oppose), or a few binades away."""
    q = fp_ref.fp_mul(f, 1, a, b)
    if (q >> f.man) & f.emax_field == f.emax_field:
        return fp_ref.rand_pattern(rng, f, edges)
    s, e, m = fp_ref.unpack(f, q)
    e2 = max(0, min(f.emax_field - 1, e + rng.choice((-3, -2, -1, 0, 0, 0, 1, 2, 3))))
    m2 = (m ^ rng.getrandbits(rng.randrange(0, f.man + 1))) & ((1 << f.man) - 1) if rng.random() < 0.7 else m
    return ((s ^ rng.choice((0, 1, 1))) << (f.w - 1)) | (e2 << f.man) | m2


def _tie_with_tiny_addend(rng, f):
    """A product that is an exact tie (a = 1 + 2**-j, b = 1 + 2**-k with j + k = MAN + 1: the discarded half of the product is exactly one half) and an addend so small that it is
    entirely below the product's rounding position: the result depends on that addend only through the sticky bit (or the lack of it)."""
    j = rng.randrange(1, f.man + 1)
    k = f.man + 1 - j
    if not 1 <= k <= f.man:
        j, k = 1, f.man
    ea = rng.randrange(max(1, f.bias - 2), min(f.emax_field - 1, f.bias + 3))
    eb = rng.randrange(max(1, f.bias - 2), min(f.emax_field - 1, f.bias + 3))
    a = (rng.getrandbits(1) << (f.w - 1)) | (ea << f.man) | (1 << (f.man - j))
    b = (rng.getrandbits(1) << (f.w - 1)) | (eb << f.man) | (1 << (f.man - k))
    ec = max(0, ea + eb - f.bias - (3 * (f.man + 1) + 3) - rng.randrange(0, 6))
    c = (rng.getrandbits(1) << (f.w - 1)) | (ec << f.man) | rng.getrandbits(f.man)
    return a, b, c


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    f = fp_ref.Fmt(p["EXP"], p["MAN"])
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["EXP"] * 64 + p["MAN"])
    edges = fp_ref.edge_patterns(f)
    await bench.start(dut)
    small = rng.sample(edges, min(len(edges), 14))
    vs = [{"a": a, "b": b, "c": c} for a, b, c in itertools.product(small, small, small)]
    n = int(os.environ["ARITH_N"])
    for i in range(n):
        a = fp_ref.rand_pattern(rng, f, edges)
        b = fp_ref.partner_pattern(rng, f, a) if i % 3 == 0 else fp_ref.rand_pattern(rng, f, edges)
        r = i % 4
        if r < 2:
            c = _addend_near_product(rng, f, a, b, edges)
        elif r == 2:
            c = fp_ref.partner_pattern(rng, f, a)
        else:
            c = fp_ref.rand_pattern(rng, f, edges)
        if i % 8 == 7:
            a, b, c = _tie_with_tiny_addend(rng, f)
        vs.append({"a": a, "b": b, "c": c})
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"randomised {p}")
