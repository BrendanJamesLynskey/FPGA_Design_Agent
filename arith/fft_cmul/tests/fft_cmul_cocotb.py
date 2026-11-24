"""cocotb bench of the complex multiplier variants against arith/fft_cmul/model.py (arith brief 148).

`exhaustive` drives every (ar, ai, br, bi) of a point (4 operands, up to 16 bits in all); `randomised` drives every pair of edge values and ARITH_N random vectors."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

from arith.fft_cmul import model
from arith.tools import arith_common as ac
from arith.tools import bench


def step(p):
    def f(v):
        pr, pi = model.cmul(p["WA"], p["WB"], v["ar"], v["ai"], v["br"], v["bi"])
        return {"pr": pr, "pi": pi}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    assert 2 * p["WA"] + 2 * p["WB"] <= 16
    await bench.start(dut)
    vs = [{"ar": a, "ai": b, "br": c, "bi": d} for a, b, c, d in itertools.product(range(1 << p["WA"]), range(1 << p["WA"]), range(1 << p["WB"]), range(1 << p["WB"]))]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"exhaustive {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["WA"] * 64 + p["WB"])
    ea, eb = ac.edge_values(p["WA"]), ac.edge_values(p["WB"])
    await bench.start(dut)
    vs = [{"ar": a, "ai": b, "br": c, "bi": d} for a, b, c, d in itertools.product(ea[:12], ea[-12:], eb[:12], eb[-12:])]
    for _ in range(int(os.environ["ARITH_N"])):
        vs.append({"ar": ac.rand_value(rng, p["WA"], ea), "ai": ac.rand_value(rng, p["WA"], ea), "br": ac.rand_value(rng, p["WB"], eb), "bi": ac.rand_value(rng, p["WB"], eb)})
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"randomised {p}")
