"""cocotb bench of the atan2 / magnitude variants against arith/atan2_mag/model.py (arith brief 139d).

`exhaustive` drives every (x, y) pair of a point with W up to 6 bits; `randomised` drives edge-value pairs, pairs on the axes and diagonals, small vectors, and
ARITH_N random pairs. The two variants compute the same numbers (only the latency differs)."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

from arith.atan2_mag import model
from arith.tools import arith_common as ac
from arith.tools import bench


@cocotb.test()
async def exhaustive(dut):
    p, lat, var = bench.env_params(), bench.env_latency(), os.environ["ARITH_VARIANT"]
    assert 2 * p["W"] <= 12
    await bench.start(dut)
    vs = [{"x": x, "y": y} for x, y in itertools.product(range(1 << p["W"]), repeat=2)]
    await bench.run_stream(dut, vs, model.step(var, p), max(lat - 1, 0), f"exhaustive {var} {p}")


@cocotb.test()
async def randomised(dut):
    p, lat, var = bench.env_params(), bench.env_latency(), os.environ["ARITH_VARIANT"]
    w = p["W"]
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + w * 64 + p["PH"])
    m = (1 << w) - 1
    edges = ac.edge_values(w)
    se = sorted(set(rng.sample(edges, min(len(edges), 16))) | {0, m, 1, 1 << (w - 1), (1 << (w - 1)) - 1, (1 << (w - 1)) + 1})
    await bench.start(dut)
    vs = [{"x": x, "y": y} for x, y in itertools.product(se, se)]
    vs += [{"x": v & m, "y": 0} for v in (1, 2, 5, 100, 1 << (w - 2), -1, -2, -7, -100)]           # on the axes
    vs += [{"x": v & m, "y": v & m} for v in (1, 3, 100, 1 << (w - 2), -1, -3, -100)] + [{"x": v & m, "y": -v & m} for v in (1, 3, 100, 1 << (w - 2))]
    vs += [{"x": ac.rand_value(rng, w, edges) if rng.random() < 0.5 else rng.getrandbits(w),
            "y": ac.rand_value(rng, w, edges) if rng.random() < 0.5 else rng.getrandbits(w)} for _ in range(int(os.environ["ARITH_N"]))]
    vs += [{"x": rng.randrange(-8, 9) & m, "y": rng.randrange(-8, 9) & m} for _ in range(200)]              # small vectors: the hardest for the angle
    await bench.run_stream(dut, vs, model.step(var, p), max(lat - 1, 0), f"randomised {var} {p}")
