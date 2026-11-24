"""cocotb bench of the reorder buffer against arith/fft_reorder/model.py (arith brief 148): `directed` sends frames of consecutive numbers (every word distinct, so a wrong address shows
at once) back to back and with gaps, `randomised` sends random words with random gaps (0 and 1 are allowed: a frame may follow another with no gap, or after any idle time).
Every output frame is compared with the model, the latency from in_sof to out_sof must be N + 1, and out_valid must be N consecutive clocks."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

from arith.fft_common import frames as fr
from arith.fft_reorder import model
from arith.tools import bench


async def run(dut, p, lat, frs, label):
    n = 1 << p["LOGN"]
    await bench.start(dut)
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.in_sof.value = 0
    dut.in_d.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    outs, starts = await fr.run_frames(dut, frs, n, ("in_d",), ("out_d",), [p["WD"]], lat + 2 * n + 40, False, label)
    assert len(outs) == len(frs), f"{label}: {len(outs)} output frames for {len(frs)} input frames"
    for i, (o, f, s) in enumerate(zip(outs, frs, starts)):
        want = model.reorder(p["LOGN"], [fr.to_signed(w[0], p["WD"]) for w in f.words])
        got = [w[0] for w in o.words]
        assert got == want, f"{label}: frame {i} differs at word {[k for k in range(n) if got[k] != want[k]][0]}"
        assert o.start - s + 1 == lat, f"{label}: frame {i}: latency {o.start - s + 1}, stated {lat}"


def frames_of(p, rng, k, mode):
    n = 1 << p["LOGN"]
    out = []
    for i in range(k):
        words = [(rng.getrandbits(p["WD"]),) if mode == "randomised" else ((i * n + j + 1) & ((1 << p["WD"]) - 1),) for j in range(n)]
        out.append(fr.Frame(words, 0, rng.choice((0, 0, 0, 1, 2, n, 3 * n // 2))))
    return out


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    await run(dut, p, lat, frames_of(p, rng, 6, "directed"), "directed %s" % p)


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 5)
    await run(dut, p, lat, frames_of(p, rng, max(4, int(os.environ["ARITH_N"]) // (1 << p["LOGN"])), "randomised"), "randomised %s" % p)
