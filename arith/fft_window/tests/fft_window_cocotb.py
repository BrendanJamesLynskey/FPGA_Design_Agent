"""cocotb bench of the window multiplier against arith/fft_window/model.py (arith brief 148): `exhaustive` drives every (xr, xi, w) of a point, `randomised` drives edge
values and ARITH_N random vectors."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

from arith.fft_window import model
from arith.tools import arith_common as ac
from arith.tools import bench


def step(p):
    def f(v):
        yr, yi = model.window(p["WD"], p["WW"], p["RND"], v["xr"], v["xi"], v["w"])
        return {"yr": yr, "yi": yi}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    assert 2 * p["WD"] + p["WW"] <= 16
    await bench.start(dut)
    vs = [{"xr": a, "xi": b, "w": c} for a, b, c in itertools.product(range(1 << p["WD"]), range(1 << p["WD"]), range(1 << p["WW"]))]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"exhaustive {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["WD"] * 64 + p["WW"])
    ex, ew = ac.edge_values(p["WD"]), ac.edge_values(p["WW"])
    await bench.start(dut)
    vs = [{"xr": a, "xi": b, "w": c} for a, b, c in itertools.product(ex[:14], ex[-14:], ew)]
    for _ in range(int(os.environ["ARITH_N"])):
        vs.append({"xr": ac.rand_value(rng, p["WD"], ex), "xi": ac.rand_value(rng, p["WD"], ex), "w": ac.rand_value(rng, p["WW"], ew)})
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"randomised {p}")
