"""cocotb bench for partition/rtl/part_sys.sv (brief 151): end-to-end latency, throughput and data integrity of the synthetic
system at one (HS, STAGES) point. The expected data is the stage function applied NM times (rnd below is the same arithmetic as
part_stage.sv, written again in Python); random back-pressure on the sink for every handshake type except PLAIN (HS 5, which has
no ready and needs an always-ready sink). Output: JSON line to $PART_OUT."""
from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def rnd(a: int, r: int, w: int) -> int:
    m = (1 << w) - 1
    rot = ((a << 7) | (a >> (w - 7))) & m
    k = (0x9E3779B97F4A7C15 & m) + ((r * 0x632BE59BD9B4E019) & m)
    return (((a + rot) & m) ^ (a >> 3) ^ (k & m)) & m


def expect(x: int, w: int, nm: int, d: int) -> int:
    for i in range(nm):
        for r in range(d):
            x = rnd(x, i * 16 + r, w)
    return x


@cocotb.test()
async def measure(dut):
    w, nm, d, hs, st = (int(getattr(dut, k).value) for k in ("W", "NM", "D", "HS", "STAGES"))
    mask = (1 << w) - 1
    rng = random.Random(7 + hs * 10 + st)
    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    dut.aresetn.value, dut.s_axis_tvalid.value, dut.m_axis_tready.value, dut.s_axis_tdata.value = 0, 0, 0, 0
    for _ in range(3):
        await RisingEdge(dut.aclk)
    await Timer(1, unit="ns")
    dut.aresetn.value = 1
    await RisingEdge(dut.aclk)
    await Timer(1, unit="ns")
    res = {"W": w, "NM": nm, "D": d, "HS": hs, "STAGES": st}

    async def reset():
        dut.aresetn.value, dut.s_axis_tvalid.value, dut.m_axis_tready.value = 0, 0, 0
        for _ in range(3):
            await RisingEdge(dut.aclk)
        await Timer(1, unit="ns")
        dut.aresetn.value = 1
        await RisingEdge(dut.aclk)
        await Timer(1, unit="ns")

    async def run(clocks, pv, pr, count):
        """Offer up to `count` beats; returns (accepted [(clock, data)], delivered [(clock, data)])."""
        await reset()
        k, valid, data, acc, out = 0, 0, 0, [], []
        for t in range(clocks):
            if not valid and k < count and rng.random() < pv:
                valid, data = 1, rng.getrandbits(w)
            mr = 1 if (hs == 5 or rng.random() < pr) else 0
            dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.m_axis_tready.value = valid, data, mr
            await Timer(1, unit="ns")
            sr, mv = int(dut.s_axis_tready.value), int(dut.m_axis_tvalid.value)
            if mv and mr:
                out.append((t, int(dut.m_axis_tdata.value)))
            if valid and (sr or hs == 5):
                acc.append((t, data))
                valid, k = 0, k + 1
            await RisingEdge(dut.aclk)
            await Timer(1, unit="ns")
        return acc, out

    # latency: one beat into the empty system, sink ready: clocks from the accepting clock to the clock the beat is visible
    acc, out = await run(8 * (nm + 2) * max(st, 1) + 20, 1.0, 1.0, 1)
    res["latency_clocks"] = (out[0][0] - acc[0][0]) if out else None
    res["latency_data_ok"] = bool(out) and out[0][1] == expect(acc[0][1], w, nm, d)
    # throughput: always valid, always ready: delivered beats in a window of 400 clocks after the pipeline has filled
    warm = 20 * (nm + 2) * max(st, 1)
    acc, out = await run(warm + 400, 1.0, 1.0, 10 ** 9)
    res["throughput_beats_per_clock"] = sum(1 for tt, _ in out if tt >= warm) / 400.0
    res["throughput_data_ok"] = all(o[1] == expect(a[1], w, nm, d) for a, o in zip(acc, out))
    # data integrity with back-pressure and gaps
    acc, out = await run(3000, 0.7, 0.5, 600)
    res["bp_accepted"], res["bp_delivered"] = len(acc), len(out)
    res["bp_data_ok"] = all(o[1] == expect(a[1], w, nm, d) for a, o in zip(acc, out)) and len(out) <= len(acc)
    with open(os.environ["PART_OUT"], "a") as f:
        f.write(json.dumps(res) + "\n")
