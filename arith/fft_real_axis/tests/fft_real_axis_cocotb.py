"""cocotb bench of the AXI4-Stream real-input FFT wrapper (arith brief 161): frames of N real samples in as N/2 beats (tdata = {odd sample, even sample}, tlast on the last beat), frames of
N/2 + 1 bins out as beats (tdata = {imaginary, real}, tlast on the last), compared bit for bit with the model of the wrapped core (arith/fft_real/model.py). The wrapper's protocol checkers
(arith/fft_common/axis_checker.sv) must count zero errors.

`directed`: the real-FFT bench's frames with the source streaming back to back (tvalid held high, waiting on tready): the wrapper itself must open the gap, which the bench MEASURES between the last
transferred beat of a frame and the first of the next and requires to equal N/8 exactly; the first-beat latency must equal the stated latency exactly. `randomised`: random frames with random idle
clocks between frames. `checker`: a deliberate violation (a stalled sink; a source that pauses inside a frame) that the checkers must count."""
from __future__ import annotations

import math
import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

from arith.fft_common import fcover
from arith.fft_real_axis import model
from arith.tools import bench


def real_frames_directed(n: int, w: int, rng: random.Random) -> list[list[int]]:
    """Impulses, tones, DC, Nyquist and corner values of N real samples (the stimuli of arith/fft_real's bench)."""
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


def proto_errors(dut):
    """The protocol checkers' error counts: the repository's RTL has them inside (simulation only); the packaged harness's chk_top.sv adds them around an instance that has none."""
    return [(nm, int(getattr(dut, nm).value)) for nm in ("chk_s_errs", "chk_m_errs") if hasattr(dut, nm)]


async def reset(dut):
    await bench.start(dut)
    dut.aresetn.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.m_axis_tready.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.aresetn.value = 1


async def run(dut, p, lat, xs, rng, idle, label):
    n = 1 << p["LOGN"]
    h = n // 2
    wx = model.out_width(p["W"], p["LOGN"], p["SCALE"])
    beats = [[(model.pack_in(x[2 * m], x[2 * m + 1], p["W"]), int(m == h - 1)) for m in range(h)] for x in xs]
    fi, bi, wait, t = 0, 0, idle(rng), 0
    first_t, last_t, outs, cur, out_first = [], [], [], None, []
    tail = 0
    while True:
        await FallingEdge(dut.clk)
        mv = int(dut.m_axis_tvalid.value)
        if mv:
            d, last = int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value)
            if cur is None:
                cur = []
                out_first.append(t)
            cur.append(model.unpack_out(d, wx))
            assert (last == 1) == (len(cur) == h + 1), f"{label}: tlast on beat {len(cur)} of {h + 1} (clock {t})"
            if last:
                outs.append(cur)
                cur = None
            tail = 0
        else:
            tail += 1
        tv, data, last_b = 0, 0, 0
        if fi < len(xs):
            can = int(dut.s_axis_tready.value) == 1
            if bi == 0 and wait > 0:
                wait -= 1
            else:
                tv = 1
                data, last_b = beats[fi][bi]
            dut.s_axis_tvalid.value = tv
            dut.s_axis_tdata.value = data
            dut.s_axis_tlast.value = last_b
            if tv and can:
                if bi == 0:
                    first_t.append(t)
                if bi == h - 1:
                    last_t.append(t)
                bi += 1
                if bi == h:
                    bi, fi = 0, fi + 1
                    wait = idle(rng)
        else:
            dut.s_axis_tvalid.value = 0
        t += 1
        if fi >= len(xs) and tail > lat + 4 * n + 200:
            break
        assert t < 600000, f"{label}: the run does not finish"
    assert len(outs) == len(xs), f"{label}: {len(outs)} output frames for {len(xs)}"
    for i, (o, x) in enumerate(zip(outs, xs)):
        want = [tuple(v) for v in model.frame(p, x)]
        assert [tuple(v) for v in o] == want, f"{label}: frame {i} differs from the model"
        assert out_first[i] - first_t[i] == lat, f"{label}: frame {i}: first-beat latency {out_first[i] - first_t[i]}, stated {lat}"
    errs = proto_errors(dut)
    assert all(v == 0 for _, v in errs), f"{label}: protocol checker errors: {errs}"
    cv = fcover.cover()
    for i in range(len(xs)):
        cv.hit("frames")
        if i:
            cv.hit("gap_enforced" if first_t[i] - last_t[i - 1] - 1 == model.gap(p["LOGN"]) else "gap_other")
    cv.dump()
    return first_t, last_t


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    n = 1 << p["LOGN"]
    xs = real_frames_directed(n, p["W"], rng)
    await reset(dut)
    first_t, last_t = await run(dut, p, lat, xs, rng, lambda r: 0, f"directed {p}")
    for i in range(1, len(xs)):                                        # idle clocks between the last transferred beat of a frame and the first of the next
        idle_clocks = first_t[i] - last_t[i - 1] - 1
        assert idle_clocks == model.gap(p["LOGN"]), f"frame {i}: the wrapper opened a gap of {idle_clocks} clocks, the rule is N/8 = {model.gap(p['LOGN'])}"


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 5)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    xs = [real_frame_random(n, p["W"], rng) for _ in range(k)]
    await reset(dut)
    await run(dut, p, lat, xs, rng, lambda r: r.choice((0, 0, 1, 3, n // 8, n // 2)), f"randomised {p}")


@cocotb.test()
async def checker(dut):
    """The protocol checkers can fail: a stalled sink (the output cannot be stalled) and a source that pauses inside a frame (the core streams)."""
    p = bench.env_params()
    n = 1 << p["LOGN"]
    h = n // 2
    rng = random.Random(77)
    await reset(dut)
    x = real_frame_random(n, p["W"], rng)
    beats = [(model.pack_in(x[2 * m], x[2 * m + 1], p["W"]), int(m == h - 1)) for m in range(h)]
    # a pause inside a frame: beat 0 and 1, then tvalid low for one clock, then the rest
    for i, (d, l) in enumerate(beats):
        await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, d, l
        if i == 1:
            await FallingEdge(dut.clk)
            dut.s_axis_tvalid.value = 0
            await FallingEdge(dut.clk)
            dut.s_axis_tvalid.value = 1
    await FallingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0
    if not hasattr(dut, "chk_s_errs"):
        return                                                         # no protocol checker around this instance: nothing to show
    assert int(dut.chk_s_errs.value) > 0, "the checker did not flag a pause inside a frame"
    for _ in range(3 * n):
        await FallingEdge(dut.clk)
        dut.m_axis_tready.value = 0
    assert int(dut.chk_m_errs.value) > 0, "the checker did not flag a stalled sink on the no-stall interface"
