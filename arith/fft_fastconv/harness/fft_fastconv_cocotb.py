"""cocotb bench of the fast-convolution block against arith/fft_fastconv/model.py (arith brief 161).

The bench drives the three interfaces at once: an AXI4-Stream source (random tvalid gaps, data held until accepted), an AXI4-Stream sink (random tready) and an AXI4-Lite master (address and data in
either order, random delays, a response channel that waits), and compares the output stream with the model bit for bit. Modes:
  directed    a small point: the register defaults, a zero filter (zero output), the filter loaded through the registers, a stream through it; the LATENCY probe (the last input beat of the first block to
              the first output beat, sink always ready) must equal spec.yaml's formula exactly;
  randomised  random taps and a random stream with random stalls on both sides and random register traffic while the stream runs (a commit while BUSY is refused with SLVERR and sets DROPPED), then a
              new filter after the stream drains and more samples (the history carries over); the latency probe first (three blocks with no stalls: the latency of the first, and the period B + N + 1
              of the blocks);
  axil        the register file alone: every access type of the register map in the contract (read-only and unmapped addresses, partial strobes, write-1-to-clear, auto-increment, the address-then-data and
              data-then-address orders, a slow bready and rready), with the AXI4-Lite protocol checker silent;
  saturate    a filter of gain 2**GB and a loud input: the outputs saturate exactly as the model says and STATUS.SAT is set, then cleared by writing 1.
Every checker (axis_checker on both streams, axil_checker on the register interface) must count zero errors."""
from __future__ import annotations

import math
import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from cocotb.utils import get_sim_time

import fcover
import fft_ref as fr
import model
import bench

ID, CFG0, CFG1, STATUS, BLOCKS, CADDR, CRE, CIM = (0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C)
OKAY, SLVERR = 0, 2


def now() -> int:
    return int(get_sim_time("ns")) // 10


def taps(p: dict, rng: random.Random, kind: str | None = None) -> list[float]:
    """A real FIR of L taps whose absolute gain (sum of |h|) is at most 2**GB * 0.9 so that the transform cannot overflow."""
    n = p["L"]
    kind = kind or rng.choice(("lowpass", "random", "highpass", "delta"))
    if kind == "lowpass":
        fc = rng.uniform(0.05, 0.4)
        h = [(math.sin(2 * math.pi * fc * (i - (n - 1) / 2)) / (math.pi * (i - (n - 1) / 2)) if i != (n - 1) / 2 else 2 * fc) * (0.54 - 0.46 * math.cos(2 * math.pi * i / max(1, n - 1))) for i in range(n)]
    elif kind == "highpass":
        h = [(-1) ** i * (0.5 + 0.5 * math.cos(math.pi * (i - (n - 1) / 2) / max(1, n))) / n for i in range(n)]
    elif kind == "delta":
        h = [0.0] * n
        h[rng.randrange(n)] = rng.choice((-1.0, 0.75, 1.0))
    else:
        h = [rng.uniform(-1, 1) / n for _ in range(n)]
    g = sum(abs(v) for v in h)
    lim = (1 << p["GB"]) * 0.9
    return [v * min(1.0, lim / g) for v in h] if g > 0 else h


def hq_for(p: dict, h: list[float]) -> list[tuple[int, int]]:
    return model.filter_spectrum(h, 1 << p["LOGN"], p["WH"], p["FH"])


def samples(p: dict, rng: random.Random, n: int, amp: float = 0.5) -> list[tuple[int, int]]:
    a = int(amp * (1 << (p["W"] - 1)))
    return [(rng.randrange(-a, a + 1), rng.randrange(-a, a + 1)) for _ in range(n)]


class Env:
    """Source, sink and clock bookkeeping around the DUT."""

    def __init__(self, dut, p, rng):
        self.dut, self.p, self.rng = dut, p, rng
        self.src, self.si = [], 0
        self.p_valid, self.p_ready = 1.0, 1.0
        self.out: list[tuple[int, int]] = []
        self.out_t: list[int] = []
        self.in_t: list[int] = []
        self.run = True

    def push(self, xs):
        self.src += list(xs)

    async def source(self):
        d, w = self.dut, self.p["W"]
        pending = False
        while self.run:
            await FallingEdge(d.clk)
            if not pending and self.si < len(self.src) and self.rng.random() < self.p_valid:
                pending = True
            if pending:
                a, b = self.src[self.si]
                d.s_axis_tvalid.value = 1
                d.s_axis_tdata.value = (fr.to_unsigned(b, w) << w) | fr.to_unsigned(a, w)
                if int(d.s_axis_tready.value) == 1:
                    self.in_t.append(now())
                    self.si += 1
                    pending = False
            else:
                d.s_axis_tvalid.value = 0

    async def sink(self):
        d, w = self.dut, self.p["W"]
        while self.run:
            await FallingEdge(d.clk)
            r = 1 if self.rng.random() < self.p_ready else 0
            d.m_axis_tready.value = r
            if r and int(d.m_axis_tvalid.value) == 1:
                v = int(d.m_axis_tdata.value)
                self.out.append((fr.to_signed(v & ((1 << w) - 1), w), fr.to_signed(v >> w, w)))
                self.out_t.append(now())

    def start(self):
        cocotb.start_soon(self.source())
        cocotb.start_soon(self.sink())

    async def drain(self, want: int, limit: int | None = None):
        d = model.derived(self.p)
        limit = limit or 30000 + 80 * d["N"] * (want // d["B"] + 3)                 # far more than any legal schedule needs: a stuck stream fails quickly
        t0 = now()
        while len(self.out) < want:
            await FallingEdge(self.dut.clk)
            assert now() - t0 < limit, f"only {len(self.out)} of {want} output samples after {limit} clocks (stream stuck?)"
        for _ in range(40):                                              # nothing more may follow
            await FallingEdge(self.dut.clk)
        assert len(self.out) == want, f"{len(self.out)} output samples, expected {want}"


async def reset(dut):
    await bench.start(dut)
    dut.aresetn.value = 0
    for nm in ("s_axis_tvalid", "s_axis_tdata", "m_axis_tready", "s_axil_awvalid", "s_axil_awaddr", "s_axil_wvalid", "s_axil_wdata", "s_axil_wstrb", "s_axil_bready", "s_axil_arvalid", "s_axil_araddr", "s_axil_rready"):
        getattr(dut, nm).value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.aresetn.value = 1


# ---- AXI4-Lite master ---------------------------------------------------------------------------------------------------------
async def axil_write(dut, addr, data, strb=0xF, rng=None, order="together", slow_b=0):
    """One write; returns bresp. order: together | addr_first | data_first; the other beat is offered a few clocks later. slow_b: clocks bready is held low after bvalid."""
    rng = rng or random.Random(0)
    gap = rng.randrange(1, 5) if order != "together" else 0
    aw_at, w_at = (0, gap) if order == "addr_first" else (gap, 0)
    aw_done = w_done = False
    c = 0
    while not (aw_done and w_done):
        await FallingEdge(dut.clk)
        awv = (not aw_done) and c >= aw_at
        wv = (not w_done) and c >= w_at
        dut.s_axil_awvalid.value, dut.s_axil_awaddr.value = int(awv), addr
        dut.s_axil_wvalid.value, dut.s_axil_wdata.value, dut.s_axil_wstrb.value = int(wv), data & 0xFFFFFFFF, strb
        if awv and int(dut.s_axil_awready.value):
            aw_done = True
        if wv and int(dut.s_axil_wready.value):
            w_done = True
        c += 1
    await FallingEdge(dut.clk)
    dut.s_axil_awvalid.value = 0
    dut.s_axil_wvalid.value = 0
    dut.s_axil_bready.value = 0
    waited, seen = 0, False
    while True:
        if int(dut.s_axil_bvalid.value) == 1:
            seen = True
        if seen and waited >= slow_b:
            dut.s_axil_bready.value = 1
            resp = int(dut.s_axil_bresp.value)
            await FallingEdge(dut.clk)                                   # transferred at the edge in between
            dut.s_axil_bready.value = 0
            return resp
        if seen:
            waited += 1
        await FallingEdge(dut.clk)
        assert c < 100000


async def axil_read(dut, addr, slow_r=0):
    """One read; returns (rdata, rresp)."""
    await FallingEdge(dut.clk)
    dut.s_axil_araddr.value = addr
    dut.s_axil_arvalid.value = 1
    while int(dut.s_axil_arready.value) != 1:
        await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.s_axil_arvalid.value = 0
    dut.s_axil_rready.value = 0
    waited, seen = 0, False
    while True:
        if int(dut.s_axil_rvalid.value) == 1:
            seen = True
        if seen and waited >= slow_r:
            dut.s_axil_rready.value = 1
            res = (int(dut.s_axil_rdata.value), int(dut.s_axil_rresp.value))
            await FallingEdge(dut.clk)
            dut.s_axil_rready.value = 0
            return res
        if seen:
            waited += 1
        await FallingEdge(dut.clk)


async def status(dut):
    v, r = await axil_read(dut, STATUS)
    assert r == OKAY
    return v


async def wait_idle(dut, limit=3000):
    for _ in range(limit):
        if (await status(dut)) & 1 == 0:
            return
    raise AssertionError("BUSY never cleared")


async def load_filter(dut, hq, rng, order="together"):
    """Write every filter bin through the registers (the commits auto-increment COEF_ADDR); all must be accepted."""
    assert await axil_write(dut, CADDR, 0, rng=rng) == OKAY
    for re, im in hq:
        assert await axil_write(dut, CRE, re, rng=rng, order=order) == OKAY
        assert await axil_write(dut, CIM, im, rng=rng, order=order) == OKAY


def checkers(dut, label):
    """The protocol checkers' error counts must be zero: the repository's RTL has them inside (simulation only); the packaged harness's chk_top.sv adds them around an instance that has none."""
    errs = [(nm, int(getattr(dut, nm).value)) for nm in ("chk_s_errs", "chk_m_errs", "chk_l_errs") if hasattr(dut, nm)]
    assert all(v == 0 for _, v in errs), f"{label}: protocol checker errors: {errs}"
    fcover.cover().dump()


# ---- tests -------------------------------------------------------------------------------------------------------------------------------
@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    d = model.derived(p)
    await reset(dut)
    # the register defaults
    assert (await axil_read(dut, ID)) == (0x46435631, OKAY)
    assert (await axil_read(dut, CFG0)) == ((p["L"] << 16) | (p["W"] << 8) | p["LOGN"], OKAY)
    assert (await axil_read(dut, CFG1)) == ((p["GB"] << 16) | (p["FH"] << 8) | p["WH"], OKAY)
    assert (await status(dut)) & 1 == 1, "BUSY must be 1 while the memories are cleared after reset"
    await wait_idle(dut)
    assert (await status(dut)) == 0
    # the cleared filter is zero: a block of any input gives zeros
    env = Env(dut, p, rng)
    env.p_valid = 0.7
    env.start()
    env.push(samples(p, rng, d["B"]))
    await env.drain(d["B"])
    assert all(v == (0, 0) for v in env.out), "an unloaded (zero) filter must give a zero output"
    got = env.out_t[0] - env.in_t[d["B"] - 1]
    assert got == lat, f"latency {got} clocks, spec.yaml says {lat}"
    st = model.Stream(p)
    st.feed(hq_for(p, [0.0] * p["L"]), env.src[:d["B"]])
    assert st.out == env.out
    # load a filter and stream through it
    h = taps(p, rng, "lowpass" if p["L"] > 2 else "delta")
    hq = hq_for(p, h)
    await wait_idle(dut)
    await load_filter(dut, hq, rng)
    assert (await axil_read(dut, CADDR))[0] == 0, "COEF_ADDR wraps at N after N commits"
    x = samples(p, rng, 3 * d["B"] + 5)
    env.p_valid, env.p_ready = 0.8, 0.6
    n0 = len(env.out)
    env.push(x)
    await env.drain(n0 + 3 * d["B"])
    st.feed(hq, x)
    assert env.out == st.out, f"output stream differs from the model at sample {next(i for i, (a, b) in enumerate(zip(env.out, st.out)) if a != b)}"
    assert (await axil_read(dut, BLOCKS))[0] == 4
    env.run = False
    cv = fcover.cover()
    cv.hit("blocks", 4)
    cv.hit("filter_loaded")
    cv.hit("zero_filter_block")
    cv.hit("stalled_source", int(env.p_valid < 1))
    cv.hit("stalled_sink", int(env.p_ready < 1))
    checkers(dut, "directed")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 5)
    d = model.derived(p)
    await reset(dut)
    await wait_idle(dut)
    h = taps(p, rng)
    hq = hq_for(p, h)
    await load_filter(dut, hq, rng, order=rng.choice(("together", "addr_first", "data_first")))
    # latency probe on the first block, then random traffic on the same environment
    env = Env(dut, p, rng)
    env.start()
    st = model.Stream(p)
    x0 = samples(p, rng, 3 * d["B"])                                      # three blocks, source always valid and sink always ready: latency of the first and the block period
    env.push(x0)
    await env.drain(3 * d["B"])
    got = env.out_t[0] - env.in_t[d["B"] - 1]
    assert got == lat, f"latency {got} clocks, spec.yaml says {lat}"
    period = (env.in_t[d["B"]] - env.in_t[0], env.in_t[2 * d["B"]] - env.in_t[d["B"]])
    assert period == (d["B"] + d["N"] + 1,) * 2, f"block period {period} clocks, spec.yaml says B + N + 1 = {d['B'] + d['N'] + 1}"
    st.feed(hq, x0)
    assert env.out == st.out
    # a sink that takes nothing: the input must stop once the output FIFO (4 N words) is committed, nothing is lost or overwritten, and every sample comes out when the sink wakes up
    kb = (4 * d["N"]) // d["B"] + 3
    x_st = samples(p, rng, kb * d["B"])
    s0 = env.si
    env.p_ready = 0.0
    env.push(x_st)
    for _ in range(kb * (d["B"] + d["N"] + 1) + 4 * d["N"] + 200):
        await FallingEdge(dut.clk)
    taken = env.si - s0
    assert taken <= ((4 * d["N"]) // d["B"] + 1) * d["B"], f"{taken} samples accepted while the sink took nothing: more than the output FIFO can hold results for"
    assert taken >= ((4 * d["N"]) // d["B"]) * d["B"] - d["B"], f"only {taken} samples accepted while the sink took nothing"
    env.p_ready = 1.0
    st.feed(hq, x_st)
    await env.drain(len(st.out))
    assert env.out == st.out, "after a long stall of the sink the output differs from the model (a result was lost or overwritten)"
    # a longer stream with stalls on both sides and register traffic in parallel
    env.p_valid, env.p_ready = rng.choice((1.0, 0.5, 0.2)), rng.choice((1.0, 0.5, 0.15))
    k = max(3, int(os.environ["ARITH_N"]) // (d["N"] * 2))
    x1 = samples(p, rng, k * d["B"] + rng.randrange(d["B"]), amp=rng.choice((0.1, 0.5, 0.9)))
    n0 = len(env.out)
    env.push(x1)
    refused = 0
    t_start = now()
    while len(env.out) < n0 + k * d["B"]:
        assert now() - t_start < 30000 + 80 * d["N"] * (k + 3), "the stream does not finish (stuck?)"
        if rng.random() < 0.6:                                            # a commit of the value the bin already holds: harmless whether it is accepted or refused
            a = rng.randrange(d["N"])
            await axil_write(dut, CADDR, a, rng=rng)
            await axil_write(dut, CRE, hq[a][0], rng=rng)
            resp = await axil_write(dut, CIM, hq[a][1], rng=rng)
            if resp == SLVERR:
                refused += 1
                assert (await status(dut)) & 2, "a refused commit must set DROPPED"
                assert await axil_write(dut, STATUS, 2) == OKAY
        else:
            await status(dut)
    st.feed(hq, x1)
    await env.drain(len(st.out))
    assert env.out == st.out, f"output stream differs from the model at sample {next(i for i, (a, b) in enumerate(zip(env.out, st.out)) if a != b)}"
    # a new filter after the stream drained: the history of the last L - 1 samples carries over
    await wait_idle(dut)
    h2 = taps(p, rng)
    hq2 = hq_for(p, h2)
    await load_filter(dut, hq2, rng)
    x2 = samples(p, rng, 2 * d["B"])
    n1 = len(env.out)
    env.push(x2)
    st.feed(hq2, x2)
    await env.drain(len(st.out))
    assert env.out == st.out, "after a filter change the output differs from the model"
    env.run = False
    cv = fcover.cover()
    cv.hit("blocks", st.blocks)
    cv.hit("filter_reloaded")
    cv.hit("refused_commit", refused)
    cv.hit("stalled_source", int(env.p_valid < 1))
    cv.hit("stalled_sink", int(env.p_ready < 1))
    cv.hit("slow_sink", int(env.p_ready <= 0.5))
    checkers(dut, "randomised")
    dut._log.info(f"refused commits while busy: {refused}")


@cocotb.test()
async def axil(dut):
    p = bench.env_params()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 9)
    d = model.derived(p)
    wm = (1 << p["WH"]) - 1
    await reset(dut)
    # during the clear after reset a commit is refused
    assert (await status(dut)) & 1 == 1
    assert await axil_write(dut, CRE, 5, rng=rng) == OKAY
    assert await axil_write(dut, CIM, 6, rng=rng) == SLVERR, "a commit while the memories are being cleared must be refused"
    assert (await status(dut)) & 2, "DROPPED"
    assert await axil_write(dut, STATUS, 2) == OKAY and (await status(dut)) & 2 == 0, "DROPPED is cleared by writing 1 to bit 1"
    await wait_idle(dut)
    # read-only registers and unmapped addresses
    for a in (ID, CFG0, CFG1, BLOCKS):
        v0 = (await axil_read(dut, a))[0]
        assert await axil_write(dut, a, 0xFFFFFFFF, rng=rng) == SLVERR, f"write to read-only {a:#x}"
        assert (await axil_read(dut, a))[0] == v0, "a refused write must change nothing"
    for a in (0x20, 0x24, 0x3C):
        assert (await axil_read(dut, a)) == (0, SLVERR), f"read of the unmapped address {a:#x}"
        assert await axil_write(dut, a, 1, rng=rng) == SLVERR
    # byte address bits [1:0] are ignored
    assert (await axil_read(dut, ID + 3)) == (0x46435631, OKAY)
    # partial strobes are refused with no effect
    assert await axil_write(dut, CADDR, 3, rng=rng) == OKAY and (await axil_read(dut, CADDR))[0] == 3 % d["N"]
    for strb in (0x0, 0x1, 0x7, 0xE, 0x8):
        assert await axil_write(dut, CADDR, 1, strb=strb, rng=rng) == SLVERR
    assert (await axil_read(dut, CADDR))[0] == 3 % d["N"]
    # COEF_ADDR: upper bits ignored; staging registers read back sign-extended; the commit auto-increments and wraps
    assert await axil_write(dut, CADDR, 0xFFFFFFFF, rng=rng) == OKAY and (await axil_read(dut, CADDR))[0] == d["N"] - 1
    neg = (1 << (p["WH"] - 1)) | 1
    assert await axil_write(dut, CRE, neg, rng=rng, order="addr_first") == OKAY
    assert (await axil_read(dut, CRE))[0] == (neg | (0xFFFFFFFF ^ wm)) & 0xFFFFFFFF, "COEF_RE reads back sign-extended"
    assert await axil_write(dut, CIM, 7, rng=rng, order="data_first") == OKAY
    assert (await axil_read(dut, CADDR))[0] == 0, "the commit at the last bin wraps COEF_ADDR to 0"
    assert (await axil_read(dut, CIM))[0] == 7
    # slow response channels
    assert await axil_write(dut, CADDR, 2, rng=rng, slow_b=5) == OKAY
    assert (await axil_read(dut, CADDR, slow_r=7)) == (2, OKAY)
    # many random accesses with random order, strobes and delays: only the checker and the final state are watched
    for _ in range(40):
        a = rng.choice((CADDR, CRE, CIM, STATUS, 0x40 - 4, ID))
        await axil_write(dut, a, rng.getrandbits(32), strb=rng.choice((0xF, 0xF, 0xF, 0x3)), rng=rng, order=rng.choice(("together", "addr_first", "data_first")), slow_b=rng.randrange(3))
        await axil_read(dut, rng.choice((ID, CFG0, STATUS, CADDR, CRE, CIM, 0x28)), slow_r=rng.randrange(3))
    # while a block is in flight the commit is refused and DROPPED is set
    await wait_idle(dut)
    env = Env(dut, p, rng)
    env.start()
    env.push(samples(p, rng, d["B"]))
    for _ in range(3000):
        if (await status(dut)) & 1:
            break
    else:
        raise AssertionError("BUSY never rose after a block was collected")
    a0 = (await axil_read(dut, CADDR))[0]
    await axil_write(dut, CRE, 1, rng=rng)
    assert await axil_write(dut, CIM, 1, rng=rng) == SLVERR
    assert (await axil_read(dut, CADDR))[0] == a0
    assert (await status(dut)) & 2
    await env.drain(d["B"])
    await wait_idle(dut)
    assert (await axil_read(dut, BLOCKS))[0] == 1
    env.run = False
    cv = fcover.cover()
    for nm in ("axil_unmapped", "axil_readonly_write", "axil_partial_strobe", "axil_refused_commit", "axil_autoincrement_wrap", "axil_status_w1c", "axil_order_variants"):
        cv.hit(nm)
    checkers(dut, "axil")


@cocotb.test()
async def saturate(dut):
    p = bench.env_params()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 21)
    d = model.derived(p)
    await reset(dut)
    await wait_idle(dut)
    h = [0.0] * p["L"]
    h[0] = (1 << p["GB"]) * 0.95                                           # a gain of about 2**GB: a loud input saturates
    hq = hq_for(p, h)
    await load_filter(dut, hq, rng)
    assert (await status(dut)) & 4 == 0
    env = Env(dut, p, rng)
    env.start()
    x = samples(p, rng, 2 * d["B"], amp=0.95)
    env.push(x)
    st = model.Stream(p)
    st.feed(hq, x)
    await env.drain(len(st.out))
    assert env.out == st.out
    assert st.sat > 0, "the point is meant to saturate"
    assert (await status(dut)) & 4, "STATUS.SAT must be set"
    assert await axil_write(dut, STATUS, 4) == OKAY and (await status(dut)) & 4 == 0, "SAT is cleared by writing 1 to bit 2"
    # a stream that saturates only the IMAGINARY parts must set SAT too
    loud = int(0.95 * (1 << (p["W"] - 1)))
    x2 = [(0, rng.choice((-1, 1)) * loud) for _ in range(2 * d["B"])]
    n1 = len(st.out)
    env.push(x2)
    st.feed(hq, x2)
    await env.drain(len(st.out))
    assert env.out == st.out
    assert (await status(dut)) & 4, "STATUS.SAT must be set by a saturating imaginary part alone"
    assert await axil_write(dut, STATUS, 4) == OKAY and (await status(dut)) & 4 == 0
    env.run = False
    fcover.cover().hit("saturated_outputs", st.sat)
    checkers(dut, "saturate")
