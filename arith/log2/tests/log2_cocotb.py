"""cocotb bench of the log2 variants against arith/log2/model.py (arith brief 139d).

`exhaustive` drives every input of a point with IW up to 12 bits; `randomised` drives edge values, the break points of the segment tables and ARITH_N random
inputs. The model is the variant's own (ARITH_VARIANT): the variants round differently and are not equal to each other."""
from __future__ import annotations

import os
import random

import cocotb

from arith.log2 import model
from arith.tools import arith_common as ac
from arith.tools import bench


@cocotb.test()
async def exhaustive(dut):
    p, lat, var = bench.env_params(), bench.env_latency(), os.environ["ARITH_VARIANT"]
    assert p["IW"] <= 12
    await bench.start(dut)
    vs = [{"x": x} for x in range(1 << p["IW"])]
    await bench.run_stream(dut, vs, model.step(var, p), max(lat - 1, 0), f"exhaustive {var} {p}")


@cocotb.test()
async def randomised(dut):
    p, lat, var = bench.env_params(), bench.env_latency(), os.environ["ARITH_VARIANT"]
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["IW"] * 64 + p["OW"])
    iw = p["IW"]
    edges = ac.edge_values(iw)
    sb = p.get("SB", 4)
    brk = sorted({min((i << max(iw - sb, 0)) + o, (1 << iw) - 1) for i in range(1 << sb) for o in (0, 1, (1 << max(iw - sb, 0)) - 1)})
    await bench.start(dut)
    vs = [{"x": x} for x in edges + brk]
    vs += [{"x": ac.rand_value(rng, iw, edges)} for _ in range(int(os.environ["ARITH_N"]))]
    await bench.run_stream(dut, vs, model.step(var, p), max(lat - 1, 0), f"randomised {var} {p}")
