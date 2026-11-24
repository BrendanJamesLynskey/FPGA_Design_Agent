"""cocotb bench of the real-input FFT against arith/fft_real/model.py (arith brief 148). `directed` drives impulses, tones, DC, Nyquist and corner values (two real samples per clock),
`randomised` drives random frames; every output frame (N/2 + 1 bins) is compared bit for bit, the latency from in_sof to out_sof is compared with ARITH_LAT and out_valid must be
N/2 + 1 consecutive clocks. Frames are separated by at least the legal gap of the spec."""
from __future__ import annotations

import math
import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

from arith.fft_common import frames as fr
from arith.fft_real import model
from arith.tools import bench


def real_frames_directed(n: int, w: int, rng: random.Random) -> list[list[int]]:
    fs = 1 << (w - 1)
    out = []
    for p in sorted({0, 1, 2, n // 2, n - 2, n - 1} | {rng.randrange(n) for _ in range(6)}):
        f = [0] * n
        f[p] = round(0.9 * fs * rng.choice((-1, 1)))
        out.append(f)
    for k in sorted({0, 1, 2, n // 4, n // 2 - 1, n // 2} | {rng.randrange(n // 2 + 1) for _ in range(6)}):
        ph = rng.uniform(0, 6.28)
        out.append([round(0.9 * fs * math.cos(2 * math.pi * k * i / n + ph)) for i in range(n)])
    out.append([round(0.9 * fs)] * n)
    out.append([round(0.9 * fs) * (1 if i % 2 == 0 else -1) for i in range(n)])
    out.append([-fs] * n)
    out.append([-fs if i % 2 == 0 else fs - 1 for i in range(n)])
    return out


def real_frame_random(n: int, w: int, rng: random.Random) -> list[int]:
    fs = 1 << (w - 1)
    kind = rng.randrange(3)
    if kind == 0:
        return [rng.randrange(-fs, fs) for _ in range(n)]
    if kind == 1:
        a = max(1, fs >> 8)
        return [rng.randrange(-a, a + 1) for _ in range(n)]
    return [rng.randrange(-fs, fs) if rng.random() < 0.1 else 0 for _ in range(n)]


async def run(dut, p, lat, xs, rng, label):
    n = 1 << p["LOGN"]
    h = n // 2
    wx = model.out_width(p["W"], p["LOGN"], p["SCALE"])
    await bench.start(dut)
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.in_sof.value = 0
    dut.in_even.value = 0
    dut.in_odd.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    frs = [fr.Frame([(fr.to_unsigned(x[2 * m], p["W"]), fr.to_unsigned(x[2 * m + 1], p["W"])) for m in range(h)], 0, h // 4 + rng.choice((0, 0, 1, 5, h))) for x in xs]
    outs, starts = await fr.run_frames(dut, frs, h, ("in_even", "in_odd"), ("out_re", "out_im"), [wx, wx], lat + 3 * n + 200, False, label, n_out=h + 1)
    assert len(outs) == len(xs), f"{label}: {len(outs)} output frames for {len(xs)} input frames"
    for i, (o, x, s) in enumerate(zip(outs, xs, starts)):
        want = [tuple(v) for v in model.frame(p, x)]
        got = [tuple(w) for w in o.words]
        bad = [k for k in range(h + 1) if got[k] != want[k]]
        assert not bad, f"{label}: frame {i}: {len(bad)} bins differ ({bad}), first {bad[0]}: got {got[bad[0]]}, model {want[bad[0]]}"
        assert o.start - s + 1 == lat, f"{label}: frame {i}: latency {o.start - s + 1}, stated {lat}"


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    await run(dut, p, lat, real_frames_directed(1 << p["LOGN"], p["W"], rng), rng, f"directed {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 31)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    await run(dut, p, lat, [real_frame_random(n, p["W"], rng) for _ in range(k)], rng, f"randomised {p}")
