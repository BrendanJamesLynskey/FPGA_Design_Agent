"""cocotb bench of the multiply-accumulate variants against the cycle-accurate mac/model.py (arith brief 139a).

`exhaustive` drives every (a, b) packed-operand pair of a point whose operand bits total at most 12 (lanes included), once with clr on the first
sample of each row and then with random en, clr and one reset in a quiet gap; `randomised` drives edge values and ARITH_N random samples with random
en and clr, and a synchronous reset now and then (also while samples are in flight: the model drops them)."""
from __future__ import annotations

import itertools
import os
import random

import cocotb

import model
import harness_common as ac
import bench


def mk(p, lat):
    return model.MacModel(p["WA"], p["WB"], p["LANES"], p["ACCW"], p["SIGNED"], lat)


def vec(rst, en, clr, a, b):
    return {"rst": rst, "en": en, "clr": clr, "a": a, "b": b}


def stepper(m):
    def f(v):
        return {"acc": m.step(v["rst"], v["en"], v["clr"], v["a"], v["b"])}
    return f


@cocotb.test()
async def exhaustive(dut):
    p, lat = bench.env_params(), bench.env_latency()
    na, nb = p["LANES"] * p["WA"], p["LANES"] * p["WB"]
    assert na + nb <= 12
    rng = random.Random(7)
    await bench.start(dut)
    m = mk(p, lat)
    await bench.run_stream(dut, [vec(1, 0, 0, 0, 0)] * 2, stepper(m), 0, "reset")
    pairs = list(itertools.product(range(1 << na), range(1 << nb)))
    vs = [vec(0, 1, int(i % (1 << nb) == 0), a, b) for i, (a, b) in enumerate(pairs)]
    vs += [vec(0, rng.getrandbits(1) | rng.getrandbits(1), int(rng.random() < 0.1), a, b) for a, b in pairs]
    vs += [vec(1, 0, 0, 0, 0)] + [vec(0, 1, 0, a, b) for a, b in pairs[:64]]
    await bench.run_stream(dut, vs, stepper(m), 0, f"exhaustive {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["WA"] * 64 + p["WB"] + p["LANES"])
    n_vec = int(os.environ["ARITH_N"])
    ea, eb = ac.edge_values(p["WA"]), ac.edge_values(p["WB"])

    def lane_pack(w, edges, n):
        v = 0
        for k in range(n):
            v |= ac.rand_value(rng, w, edges) << (k * w)
        return v

    await bench.start(dut)
    m = mk(p, lat)
    vs = [vec(1, 0, 0, 0, 0)] * 2
    for i in range(n_vec):
        r = rng.random()
        vs.append(vec(int(r < 0.01), int(rng.random() < 0.85), int(rng.random() < 0.08), lane_pack(p["WA"], ea, p["LANES"]), lane_pack(p["WB"], eb, p["LANES"])))
    # a long run with no clr and en always on, so a narrow accumulator wraps many times
    vs += [vec(0, 1, int(i == 0), lane_pack(p["WA"], ea, p["LANES"]), lane_pack(p["WB"], eb, p["LANES"])) for i in range(max(200, n_vec // 4))]
    await bench.run_stream(dut, vs, stepper(m), 0, f"randomised {p}")
