"""cocotb bench of the floating-point adder variants against fp_add/model.py (arith brief 139e).

`exhaustive` drives every (a, b) pair of a point (2 * (1 + EXP + MAN) up to 16 bits); `randomised` drives every pair of edge patterns (zeros, subnormals, extremes, infinities,
NaNs), pairs that nearly cancel, pairs of close exponents and ARITH_N random pairs."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

import model
import fp_ref
import bench


def step(p):
    def f(v):
        return {"y": model.add(p["EXP"], p["MAN"], p["SUBNORM"], v["a"], v["b"])}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    w = 1 + p["EXP"] + p["MAN"]
    assert 2 * w <= 16
    await bench.start(dut)
    vs = [{"a": a, "b": b} for a, b in itertools.product(range(1 << w), range(1 << w))]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"exhaustive {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    f = fp_ref.Fmt(p["EXP"], p["MAN"])
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["EXP"] * 64 + p["MAN"])
    edges = fp_ref.edge_patterns(f)
    await bench.start(dut)
    vs = [{"a": a, "b": b} for a, b in itertools.product(edges, edges)]
    n = int(os.environ["ARITH_N"])
    for i in range(n):
        a = fp_ref.rand_pattern(rng, f, edges)
        r = i % 4
        b = fp_ref.near_pattern(rng, f, a) if r == 0 else fp_ref.rand_pattern(rng, f, edges)
        vs.append({"a": a, "b": b})
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"randomised {p}")
