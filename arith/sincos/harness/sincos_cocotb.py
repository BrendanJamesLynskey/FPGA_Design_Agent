"""cocotb bench of the sincos variants against sincos/model.py (arith brief 139d).

`exhaustive` drives every input of a point with PH up to 12 bits; `randomised` drives edge values, the break points of the segment tables and ARITH_N random
inputs. The model is the variant's own (ARITH_VARIANT): the variants round differently and are not equal to each other."""
from __future__ import annotations

import os
import random

import cocotb

import model
import harness_common as ac
import bench


@cocotb.test()
async def exhaustive(dut):
    p, lat, var = bench.env_params(), bench.env_latency(), os.environ["ARITH_VARIANT"]
    assert p["PH"] <= 12
    await bench.start(dut)
    vs = [{"phase": x} for x in range(1 << p["PH"])]
    await bench.run_stream(dut, vs, model.step(var, p), max(lat - 1, 0), f"exhaustive {var} {p}")


@cocotb.test()
async def randomised(dut):
    p, lat, var = bench.env_params(), bench.env_latency(), os.environ["ARITH_VARIANT"]
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["PH"] * 64 + p["OW"])
    ph = p["PH"]
    k = ph - 2
    edges = ac.edge_values(ph)
    sb = p.get("SB", 4)
    # the first and last phases of each quadrant, and the neighbourhood of every table break point in every quadrant
    brk = sorted({(q << k) + min((i << max(k - sb, 0)) + o, (1 << k) - 1) for q in range(4) for i in range(1 << sb) for o in (0, 1, (1 << max(k - sb, 0)) - 1)})
    await bench.start(dut)
    vs = [{"phase": x} for x in edges + brk]
    vs += [{"phase": ac.rand_value(rng, ph, edges)} for _ in range(int(os.environ["ARITH_N"]))]
    await bench.run_stream(dut, vs, model.step(var, p), max(lat - 1, 0), f"randomised {var} {p}")
