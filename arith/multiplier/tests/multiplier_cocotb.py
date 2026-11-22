"""cocotb bench of the multiplier variants against arith/multiplier/model.py (arith brief 139a).

`exhaustive` drives every (a, b) of a point with WA + WB up to 12; `randomised` drives edge-value pairs, products that stress long carries
(operands of runs of ones) and ARITH_N random pairs."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

from arith.multiplier import model
from arith.tools import arith_common as ac
from arith.tools import bench


def step(p):
    def f(v):
        return {"p": model.mul(p["WA"], p["WB"], p["SIGNED"], v["a"], v["b"])}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    assert p["WA"] + p["WB"] <= 12
    await bench.start(dut)
    vs = [{"a": a, "b": b} for a, b in itertools.product(range(1 << p["WA"]), range(1 << p["WB"]))]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"exhaustive {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["WA"] * 64 + p["WB"])
    ea, eb = ac.edge_values(p["WA"]), ac.edge_values(p["WB"])
    await bench.start(dut)
    sa = sorted(set(rng.sample(ea, min(len(ea), 20))) | {0, (1 << p['WA']) - 1, 1 << (p['WA'] - 1)})
    sb = sorted(set(rng.sample(eb, min(len(eb), 20))) | {0, (1 << p['WB']) - 1, 1 << (p['WB'] - 1)})
    vs = [{"a": a, "b": b} for a, b in itertools.product(sa, sb)]
    vs += [{"a": ac.rand_value(rng, p["WA"], ea), "b": ac.rand_value(rng, p["WB"], eb)} for _ in range(int(os.environ["ARITH_N"]))]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"randomised {p}")
