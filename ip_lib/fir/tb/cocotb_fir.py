"""cocotb benches for ip_lib/fir. The benches drive and sample only; every expected value comes from
ip_lib/fir/model.py. Two tests:
  fir_variant  one variant (toplevel `fir`): coefficient loads, random input gaps and output back-pressure, a reload
               mid-stream, extreme values; then the measured latency and initiation interval against LATENCY and II
  fir_diff     the differential test (toplevel `fir_diff_tb`): every variant gets the same coefficients and samples,
               and their output streams must agree with each other and with the model
"""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, with_timeout

from ip_lib.fir import model


class Port:
    """The handles of one fir instance; `pre` is the instance's signal prefix in fir_diff_tb ('' for fir itself)."""

    def __init__(self, dut, pre=""):
        g = lambda n: getattr(dut, pre + n)
        self.busy, self.c_valid, self.c_ready, self.c_data, self.c_last = (g(n) for n in ("busy", "c_valid", "c_ready", "c_data", "c_last"))
        self.s_valid, self.s_ready, self.s_data = g("s_valid"), g("s_ready"), g("s_data")
        self.m_valid, self.m_ready, self.m_data = g("m_valid"), g("m_ready"), g("m_data")
        for s in (self.c_valid, self.c_data, self.c_last, self.s_valid, self.s_data, self.m_ready):
            s.value = 0


async def wait_ready(dut, p: Port):
    for _ in range(2000):
        await RisingEdge(dut.clk)
        if p.busy.value == 0:
            return
    raise AssertionError("busy never fell")


async def load(dut, p: Port, h: list[int]):
    """One coefficient load, c_valid held high from the first beat to the last."""
    for i, c in enumerate(h):
        p.c_valid.value = 1
        p.c_data.value = c
        p.c_last.value = int(i == len(h) - 1)
        while True:
            await RisingEdge(dut.clk)
            if p.c_ready.value == 1:
                break
    p.c_valid.value = 0
    p.c_last.value = 0


async def send(dut, p: Port, xs: list[int], rng: random.Random, gap: float):
    for x in xs:
        while rng.random() < gap:
            p.s_valid.value = 0
            await RisingEdge(dut.clk)
        p.s_valid.value = 1
        p.s_data.value = x
        while True:
            await RisingEdge(dut.clk)
            if p.s_ready.value == 1:
                break
    p.s_valid.value = 0


async def collect(dut, p: Port, n: int, rng: random.Random, stall: float, out: list[int]):
    while len(out) < n:
        p.m_ready.value = int(rng.random() >= stall)
        await RisingEdge(dut.clk)
        if p.m_valid.value == 1 and p.m_ready.value == 1:
            out.append(p.m_data.value.to_signed())
    p.m_ready.value = 0


def stimulus(taps, data_w, coef_w, seed):
    rng = random.Random(seed)
    lo_d, hi_d = -(1 << (data_w - 1)), (1 << (data_w - 1)) - 1
    lo_c, hi_c = -(1 << (coef_w - 1)), (1 << (coef_w - 1)) - 1
    h1 = [rng.randint(lo_c, hi_c) for _ in range(taps)]
    h2 = [lo_c] * taps                                   # the most negative coefficients: the full-precision corner
    x1 = [rng.randint(lo_d, hi_d) for _ in range(5 * taps + 40)]
    x2 = [lo_d] * (taps + 3) + [hi_d, lo_d] * 8 + [rng.randint(lo_d, hi_d) for _ in range(30)]
    return [(h1, x1), (h2, x2)]


async def run_stream(dut, p: Port, segs, seed, gap=0.3, stall=0.3):
    """Load and stream each segment in turn: the next load starts once every result of the last one is out."""
    rng = random.Random(seed + 1)
    got = []
    for i, (h, xs) in enumerate(segs):
        if i:
            # the first sample of a later segment is already offered when the load starts: the contract says no sample
            # is taken while c_valid is high, so it must wait and then use the new coefficients
            p.s_valid.value = 1
            p.s_data.value = xs[0]
        await load(dut, p, h)
        n = len(got) + len(xs)
        c = cocotb.start_soon(collect(dut, p, n, rng, stall, got))
        await with_timeout(send(dut, p, xs, rng, gap), 400 * len(xs) + 2000, "ns")
        await with_timeout(c, 400 * len(xs) + 2000, "ns")
    return got


async def measure(dut, p: Port):
    """Latency of one sample into an idle filter, then the spacing of accepted samples with the input always valid."""
    p.m_ready.value = 1
    for _ in range(4):
        await RisingEdge(dut.clk)
    p.s_valid.value = 1
    p.s_data.value = 1
    await RisingEdge(dut.clk)
    while p.s_ready.value != 1:
        await RisingEdge(dut.clk)
    p.s_valid.value = 0
    lat = 0
    while True:
        await ReadOnly()
        lat += 1
        if p.m_valid.value == 1:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    for _ in range(4):
        await RisingEdge(dut.clk)
    p.s_valid.value = 1
    taken = []
    for cyc in range(400):
        await RisingEdge(dut.clk)
        if p.s_valid.value == 1 and p.s_ready.value == 1:
            taken.append(cyc)
    p.s_valid.value = 0
    ii = [b - a for a, b in zip(taken, taken[1:])]
    return lat, ii


@cocotb.test()
async def fir_variant(dut):
    taps, dw, cw = int(dut.TAPS.value), int(dut.DATA_W.value), int(dut.COEF_W.value)
    impl, fold = os.environ["FIR_IMPL"], int(dut.FOLD.value)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    p = Port(dut)
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await wait_ready(dut, p)
    seed = 63 + taps + 7 * dw + 13 * cw
    segs = stimulus(taps, dw, cw, seed)
    got = await run_stream(dut, p, segs, seed)
    want = model.fir_segments(segs)
    bad = [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w]
    assert len(got) == len(want) and not bad, f"{impl}: {len(bad)} mismatches, first {bad[:3]}"
    t = model.fir_timing(impl, taps, fold)
    rtl = {"latency": int(dut.LATENCY.value), "ii": int(dut.II.value)}
    assert rtl == {k: t[k] for k in rtl}, f"{impl}: RTL localparams {rtl}, model {t}"
    lat, ii = await measure(dut, p)
    assert lat == t["latency"], f"{impl}: measured latency {lat}, declared {t['latency']}"
    assert ii and min(ii) == max(ii) == t["ii"], f"{impl}: measured II {sorted(set(ii))}, declared {t['ii']}"
    dut._log.info(f"fir {impl} TAPS {taps}: {len(got)} outputs bit-exact, latency {lat}, II {ii[0]}")


@cocotb.test()
async def fir_diff(dut):
    taps, dw, cw = int(dut.TAPS.value), int(dut.DATA_W.value), int(dut.COEF_W.value)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    ports = {impl: Port(dut, impl + "_") for impl in model.IMPLS}
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for p in ports.values():
        await wait_ready(dut, p)
    segs = stimulus(taps, dw, cw, 630)
    # each variant takes the same values at its own pace; the gap and stall patterns differ per variant on purpose
    tasks = {impl: cocotb.start_soon(run_stream(dut, p, segs, 630 + i, gap=0.2 * i, stall=0.15 * i))
             for i, (impl, p) in enumerate(ports.items())}
    outs = {impl: await t for impl, t in tasks.items()}
    want = model.fir_segments(segs)
    ref = outs["dsp_bram"]
    for impl, o in outs.items():
        assert o == ref, f"{impl} differs from dsp_bram at {[i for i, (a, b) in enumerate(zip(o, ref)) if a != b][:3]}"
    assert ref == want, "the variants agree with each other but not with the model"
    dut._log.info(f"fir_diff: {len(ref)} outputs identical across {', '.join(outs)} and equal to the model")
