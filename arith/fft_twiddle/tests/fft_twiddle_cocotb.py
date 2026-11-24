"""cocotb bench of the twiddle generator against arith/fft_twiddle/model.py (arith brief 148): `exhaustive` drives every index of the circle (2**LOGC, up to 4096),
`randomised` drives ARITH_N random indices (a different order, so the ROM sees every transition)."""
from __future__ import annotations

import os
import random

import cocotb

from arith.fft_twiddle import model
from arith.tools import bench


def step(p):
    def f(v):
        wr, wi = model.twiddle(p["LOGC"], p["TW"], v["m"])
        return {"wr": wr, "wi": wi}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    await bench.start(dut)
    vs = [{"m": m} for m in range(1 << p["LOGC"])]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"exhaustive {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGC"])
    await bench.start(dut)
    vs = [{"m": rng.randrange(1 << p["LOGC"])} for _ in range(int(os.environ["ARITH_N"]))]
    await bench.run_stream(dut, vs, step(p), max(lat - 1, 0), f"randomised {p}")
