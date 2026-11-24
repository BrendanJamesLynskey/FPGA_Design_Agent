"""cocotb bench of the AXI4-Stream FFT wrappers (arith brief 148): frames in as AXI4-Stream beats (tdata = {imaginary, real}, tlast on the last beat, tuser = inverse on the first beat), frames
out as beats, compared bit for bit with the model of the wrapped variant. The wrapper's own protocol checkers (arith/fft_common/axis_checker.sv: valid stability, data stability, no unknowns,
tlast on the right beat, no stall for the streaming variant, no pause inside a frame where the variant forbids it) must count zero errors.

`directed`: the frames of the FFT bench, no pauses, tready high: the first-beat to first-beat latency must equal the stated latency exactly. `randomised`: random frames; the burst variant is
driven with random tvalid pauses inside frames, random pauses between frames and random m_axis_tready (the sdf variant, which cannot pause, with the legal gaps); the latency is then a lower bound
for burst. `checker`: a deliberate protocol violation (a stalled sink on the no-stall variant, a withdrawn tvalid on the stalling variant) that the checker must count."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

from arith.fft_axis import model
from arith.fft_common import frames as fr
from arith.tools import bench

VARIANT = os.environ.get("ARITH_VARIANT", "sdf")


async def reset(dut):
    await bench.start(dut)
    dut.aresetn.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tuser.value = 0
    dut.m_axis_tready.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.aresetn.value = 1


async def run(dut, p, lat, xs, invs, rng, pause_in, pause_between, p_notready, exact, label):
    n = 1 << p["LOGN"]
    w = p["W"]
    wo = model.out_width(w, p["LOGN"], p["SCALE"])
    beats = [[(model.pack(b, a, w), int(i == n - 1)) for i, (a, b) in enumerate(x)] for x in xs]
    fi, bi, wait, t = 0, 0, rng.choice((0, 3)) if pause_between else 0, 0
    first_t, outs, cur, out_first = [], [], None, []
    tail = 0
    while True:
        await FallingEdge(dut.clk)
        # the sink
        mv = int(dut.m_axis_tvalid.value)
        ready = 0 if (p_notready and rng.random() < p_notready) else 1
        dut.m_axis_tready.value = ready
        if mv:
            d, last = int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value)
            if ready:
                if cur is None:
                    cur = []
                    out_first.append(t)
                cur.append(model.unpack(d, wo))
                assert (last == 1) == (len(cur) == n), f"{label}: tlast on beat {len(cur)} of {n} (clock {t})"
                if last:
                    outs.append(cur)
                    cur = None
            tail = 0
        else:
            tail += 1
        # the source
        tv = 0
        data = last_b = 0
        if fi < len(xs):
            can = int(dut.s_axis_tready.value) == 1
            if bi == 0 and wait > 0:
                wait -= 1
            elif bi > 0 and pause_in and rng.random() < pause_in:
                pass
            else:
                tv = 1
                data, last_b = beats[fi][bi]
            dut.s_axis_tuser.value = invs[fi] if bi == 0 else 1 - invs[fi]
            dut.s_axis_tvalid.value = tv
            dut.s_axis_tdata.value = data
            dut.s_axis_tlast.value = last_b
            if tv and can:
                if bi == 0:
                    first_t.append(t)
                bi += 1
                if bi == n:
                    bi, fi = 0, fi + 1
                    wait = (n // 4 + rng.choice((0, 0, 1, 9)) if VARIANT == "sdf" else rng.choice((0, 0, 2, 11))) if pause_between else 0
                    if VARIANT == "sdf" and pause_between and rng.random() < 0.4:
                        wait = 0
        else:
            dut.s_axis_tvalid.value = 0
        t += 1
        if fi >= len(xs) and tail > lat + 4 * n + 200:
            break
        assert t < 600000, f"{label}: the run does not finish"
    assert len(outs) == len(xs), f"{label}: {len(outs)} output frames for {len(xs)}"
    for i, (o, x, inv) in enumerate(zip(outs, xs, invs)):
        want = [tuple(v) for v in model.frame(VARIANT, p, x, inv)]
        assert [tuple(v) for v in o] == want, f"{label}: frame {i} differs from the model"
        l = out_first[i] - first_t[i]
        assert (l == lat) if exact else (l >= lat), f"{label}: frame {i}: first-beat latency {l}, stated {lat}"
    assert int(dut.chk_s_errs.value) == 0 and int(dut.chk_m_errs.value) == 0, f"{label}: protocol checker errors: source {int(dut.chk_s_errs.value)}, sink {int(dut.chk_m_errs.value)}"


def invs_for(k, rng):
    return [rng.randrange(2) for _ in range(k)]


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    n = 1 << p["LOGN"]
    xs = fr.directed_frames(n, p["W"], rng, max_pos=8, max_tones=8)
    await reset(dut)
    # no pauses: back to back for the streaming variant; for burst the source waits for tready between frames (that wait is what 'back to back' means there)
    await run(dut, p, lat, xs, invs_for(len(xs), rng), rng, 0, 0, 0, True, f"directed {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 5)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    burst = VARIANT == "burst"
    await reset(dut)
    await run(dut, p, lat, xs, invs_for(k, rng), rng, 0.2 if burst else 0, 1, 0.4 if burst else 0, not burst, f"randomised {p}")


@cocotb.test()
async def checker(dut):
    """The protocol checkers can fail: a stalled sink on the streaming variant, a withdrawn tvalid on the stalling variant."""
    p = bench.env_params()
    n = 1 << p["LOGN"]
    rng = random.Random(77)
    await reset(dut)
    x = fr.random_frame(n, p["W"], rng)
    beats = [(model.pack(b, a, p["W"]), int(i == n - 1)) for i, (a, b) in enumerate(x)]
    if VARIANT == "sdf":
        for i, (d, l) in enumerate(beats):
            await FallingEdge(dut.clk)
            dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value, dut.s_axis_tuser.value = 1, d, l, 0
        await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value = 0
        for _ in range(4 * n):
            await FallingEdge(dut.clk)
            dut.m_axis_tready.value = 0
        assert int(dut.chk_m_errs.value) > 0, "the checker did not flag a stalled sink on the no-stall interface"
    else:
        await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, beats[0][0], 0
        await FallingEdge(dut.clk)                       # accepted (idle: tready high); the frame is loading, the source now withdraws tvalid... not a violation while tready is high
        dut.s_axis_tvalid.value = 0
        await FallingEdge(dut.clk)
        # make tready low: complete the frame so the core computes, then present a beat and withdraw it while tready is low
        for d, l in beats[1:]:
            dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, d, l
            await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, 0x1234, 0
        await FallingEdge(dut.clk)
        assert int(dut.s_axis_tready.value) == 0
        dut.s_axis_tvalid.value = 0                      # withdrawn while tready was low
        await FallingEdge(dut.clk)
        await FallingEdge(dut.clk)
        assert int(dut.chk_s_errs.value) > 0, "the checker did not flag a withdrawn tvalid"
