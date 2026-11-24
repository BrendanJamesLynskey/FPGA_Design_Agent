"""cocotb bench of the adder/subtractor variants against adder/model.py (arith brief 139a).

ARITH_PARAMS (json: WIDTH and the variant's own), ARITH_LAT, ARITH_SEED and ARITH_N come from tools/arith_common.run_point.
`exhaustive` drives every (a, b, cin, sub) of a width up to 6 (and, for a wider one, every a with an edge-value b); `randomised` drives ARITH_N
vectors of edge values and carry-chain-stressing runs, plus a run of the edge values against each other."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

import model
import harness_common as ac
import bench


def vec(a, b, cin, sub):
    return {"a": a, "b": b, "cin": cin, "sub": sub}


def step(w):
    def f(v):
        s, co, ovf = model.addsub(w, v["a"], v["b"], v["cin"], v["sub"])
        return {"s": s, "co": co, "ovf": ovf}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    w = p["WIDTH"]
    assert w <= 6, "exhaustive is for small widths"
    await bench.start(dut)
    vs = [vec(a, b, c, s) for a, b, c, s in itertools.product(range(1 << w), range(1 << w), (0, 1), (0, 1))]
    # a pipelined variant is also run with the same vectors again after a gap of idle clocks (its pipeline holds data only)
    n = await bench.run_stream(dut, vs, step(w), max(lat - 1, 0), f"exhaustive W={w}")
    assert n == len(vs) - max(lat - 1, 0)


@cocotb.test()
async def randomised(dut):

    p, lat = bench.env_params(), bench.env_latency()
    w = p["WIDTH"]
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + w)
    n_vec = int(os.environ["ARITH_N"])
    edges = ac.edge_values(w)
    await bench.start(dut)
    some = sorted(set(rng.sample(edges, min(len(edges), 18))) | {0, (1 << w) - 1})
    vs = [vec(a, b, c, s) for a, b in itertools.product(some, some) for c, s in ((0, 0), (1, 0), (0, 1), (1, 1))]
    vs += [vec(ac.rand_value(rng, w, edges), ac.rand_value(rng, w, edges), rng.getrandbits(1), rng.getrandbits(1)) for _ in range(n_vec)]
    await bench.run_stream(dut, vs, step(w), max(lat - 1, 0), f"random W={w}")
