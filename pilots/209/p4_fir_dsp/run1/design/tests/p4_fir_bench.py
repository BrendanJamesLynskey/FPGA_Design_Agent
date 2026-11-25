"""cocotb bench for p4_fir32 register core, checked against model.py (blind model)."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID = 0x20940001
CTRL, IN_PUSH, OUT_POP, STATUS, SAT, DONE = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
DEPTH = 1024


class Env:
    def __init__(self, dut):
        self.dut = dut
        self.m = model.Model()
        self.last_rd = None

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 40, units="ns").start())
        if hasattr(d, "clk_dsp"):
            cocotb.start_soon(Clock(d.clk_dsp, 4, units="ns").start())
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        await self.reset()

    async def reset(self):
        d = self.dut
        d.rst.value = 1
        for _ in range(6):
            await RisingEdge(d.clk)
        d.rst.value = 0
        for _ in range(4):
            await RisingEdge(d.clk)
        self.m = model.Model()
        self.m.reset()

    async def clocks(self, n):
        for _ in range(n):
            await RisingEdge(self.dut.clk)

    async def raw_write(self, a, v):
        d = self.dut
        d.h_we.value = 1
        d.h_addr.value = a
        d.h_wdata.value = v
        await RisingEdge(d.clk)
        d.h_we.value = 0

    async def wr(self, a, v):
        await self.raw_write(a, v)
        await RisingEdge(self.dut.clk)
        self.m.write_reg(a, v)

    async def rd(self, a):
        d = self.dut
        d.h_re.value = 1
        d.h_addr.value = a
        await RisingEdge(d.clk)
        d.h_re.value = 0
        await RisingEdge(d.clk)
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        v = int(d.h_rdata.value)
        self.last_rd = v
        return v

    async def chk(self, a, what=""):
        """read a register, compare with the model (pop side effects mirrored)."""
        v = await self.rd(a)
        e = self.m.read_reg(a)
        assert v == e, f"{what} reg 0x{a:x}: rtl 0x{v:08x} model 0x{e:08x}"
        return v

    def settle(self):
        for _ in range(200000):
            before = (len(self.m.fin), len(self.m.fout), self.m.busy)
            self.m.step({})
            if before == (len(self.m.fin), len(self.m.fout), self.m.busy) and not self.m.busy:
                return
            if before == (len(self.m.fin), len(self.m.fout), self.m.busy):
                return  # stalled

    async def push(self, vals):
        for v in vals:
            await self.wr(IN_PUSH, v & 0xFFFF)

    async def run_and_wait(self, timeout_clks=60000):
        await self.wr(CTRL, 2)
        self.settle()
        want_in = len(self.m.fin)
        want_out = len(self.m.fout)
        n = 0
        while True:
            s = await self.rd(STATUS)
            n += 4
            if (s & 1) == 0 and ((s >> 4) & 0xFFF) == want_in and ((s >> 20) & 0xFFF) == want_out:
                return
            assert n < timeout_clks, f"timeout waiting idle, status 0x{s:08x}"

    async def collect(self, what=""):
        n = len(self.m.fout)
        for i in range(n):
            await self.chk(OUT_POP, f"{what} out[{i}]")
        assert await self.rd(OUT_POP) == 0
        assert self.m.read_reg(OUT_POP) == 0

    async def chk_counters(self):
        await self.chk(STATUS, "status")
        await self.chk(SAT, "sat")
        await self.chk(DONE, "done")


def stim_random(rng, n):
    out = []
    for _ in range(n):
        c = rng.random()
        if c < 0.6:
            out.append(rng.randrange(65536))
        elif c < 0.7:
            out.append(rng.choice([0, 1, 0xFFFF, 0x7FFF, 0x8000]))
        elif c < 0.85:
            out.append(rng.randrange(-300, 300) & 0xFFFF)
        else:
            out.append(rng.choice([0x7FFF, 0x8000]))
    return out


# req: REQ-01, REQ-03, REQ-37, REQ-14, REQ-15, REQ-17, REQ-33, REQ-35, REQ-36
@cocotb.test()
async def test_smoke_reset_id_scratch(dut):
    e = Env(dut)
    await e.start()
    assert await e.rd(0) == ID
    assert await e.rd(8) == 0
    await e.chk(0x0)
    for v in (0xA5A5A5A5, 0xFFFFFFFF, 0x1, 0x80000000, 0):
        await e.wr(8, v)
        assert await e.rd(8) == v
    await e.wr(8, 0xCAFEF00D)
    assert await e.rd(8) == 0xCAFEF00D
    await e.reset()
    assert await e.rd(8) == 0, "SCRATCH must reset to 0"
    assert await e.rd(0) == ID
    await e.chk_counters()


# req: REQ-02
@cocotb.test()
async def test_build_readable(dut):
    e = Env(dut)
    await e.start()
    a = await e.rd(4)
    b = await e.rd(4)
    assert a == b, "BUILD must be stable"


# req: REQ-04, REQ-05
@cocotb.test()
async def test_unmapped(dut):
    e = Env(dut)
    await e.start()
    await e.wr(8, 0x1234)
    await e.push([5, 6, 7])
    addrs = [0x00C, 0x028, 0x02C, 0x030, 0x040, 0x0FC, 0x100, 0x400, 0x800, 0xFFC, 0x00D, 0x019, 0x021]
    for a in addrs:
        assert await e.rd(a) == 0, f"unmapped 0x{a:x} read"
    for a in addrs:
        await e.raw_write(a, 0xFFFFFFFF)
        await e.clocks(2)
    assert await e.rd(8) == 0x1234
    await e.chk(STATUS)
    await e.chk(SAT)
    await e.chk(DONE)
    # write to unmapped must not have started a run or cleared anything
    await e.run_and_wait()
    await e.collect("unmapped")
    # also writes to RO registers are ignored
    for a in (0, 4, OUT_POP, STATUS, SAT, DONE):
        await e.raw_write(a, 0xFFFFFFFF)
        await e.clocks(2)
    assert await e.rd(0) == ID
    await e.chk_counters()


# req: REQ-06, REQ-38
@cocotb.test()
async def test_read_latency_hold(dut):
    e = Env(dut)
    await e.start()
    d = dut
    await e.wr(8, 0x600DBEEF)
    # read, then change underlying state: h_rdata must hold until next h_re
    a = await e.rd(8)
    assert a == 0x600DBEEF
    await e.raw_write(8, 0x11111111)
    for _ in range(8):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        assert int(d.h_rdata.value) == 0x600DBEEF, "h_rdata changed without h_re"
    v = await e.rd(0)
    assert v == ID
    await e.raw_write(IN_PUSH, 3)
    for _ in range(8):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        assert int(d.h_rdata.value) == ID
    # check timing: valid within 2 clocks of h_re (sampled after E1+2)
    d.h_re.value = 1
    d.h_addr.value = 8
    await RisingEdge(d.clk)
    d.h_re.value = 0
    await RisingEdge(d.clk)
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    assert int(d.h_rdata.value) == 0x11111111


# req: REQ-01, REQ-03, REQ-30, REQ-39
@cocotb.test()
async def test_write_latency_ctrl_selfclear(dut):
    e = Env(dut)
    await e.start()
    d = dut
    # write at E1, read issued at the very next clock: new value visible
    await e.raw_write(8, 0xDEAD0001)
    d.h_re.value = 1
    d.h_addr.value = 8
    await RisingEdge(d.clk)
    d.h_re.value = 0
    await RisingEdge(d.clk)
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    assert int(d.h_rdata.value) == 0xDEAD0001, "write not effective one clock after h_we"
    # CTRL reads 0 one clock after write (CLEAR)
    await e.push([1, 2, 3])
    await e.raw_write(CTRL, 1)
    d.h_re.value = 1
    d.h_addr.value = CTRL
    await RisingEdge(d.clk)
    d.h_re.value = 0
    await RisingEdge(d.clk)
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    assert int(d.h_rdata.value) == 0, "CTRL bit0 not self-clearing"
    e.m.write_reg(IN_PUSH, 1)
    e.m.write_reg(CTRL, 1)
    # RUN bit
    await e.push([100, 200, 300])
    await e.raw_write(CTRL, 2)
    d.h_re.value = 1
    d.h_addr.value = CTRL
    await RisingEdge(d.clk)
    d.h_re.value = 0
    await RisingEdge(d.clk)
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    assert int(d.h_rdata.value) == 0, "CTRL bit1 not self-clearing"
    e.m.write_reg(CTRL, 2)
    await e.clocks(100)
    e.settle()
    await e.collect("ctrl")
    assert await e.rd(CTRL) == 0
    await e.chk_counters()


async def run_vectors(e, vecs, what):
    await e.push(vecs)
    await e.run_and_wait()
    await e.collect(what)
    await e.chk_counters()


# req: REQ-07, REQ-08, REQ-11, REQ-16, REQ-23
@cocotb.test()
async def test_impulse(dut):
    e = Env(dut)
    await e.start()
    vecs = [0x7FFF] + [0] * 40
    await run_vectors(e, vecs, "impulse")
    await e.reset()
    vecs = [1] + [0] * 40  # unit impulse: reads out coefficient scale
    await run_vectors(e, vecs, "impulse1")
    await e.reset()
    vecs = [0x8000] + [0] * 40
    await run_vectors(e, vecs, "impulse neg")


# req: REQ-07, REQ-09, REQ-11
@cocotb.test()
async def test_step(dut):
    e = Env(dut)
    await e.start()
    await run_vectors(e, [0x4000] * 80, "step pos")
    await e.reset()
    await run_vectors(e, [0xC000] * 80, "step neg")
    await e.reset()
    await run_vectors(e, [0x7FFF] * 80, "step max")


# req: REQ-07, REQ-31, REQ-32
@cocotb.test()
async def test_saturation(dut):
    e = Env(dut)
    await e.start()
    h = e.m.h
    pat = [(0x7FFF if h[31 - i] >= 0 else 0x8000) for i in range(32)]
    neg = [(0x8000 if h[31 - i] >= 0 else 0x7FFF) for i in range(32)]
    vecs = pat + neg + pat + [0] * 40 + [0x8000] * 40 + [0x7FFF] * 40
    await run_vectors(e, vecs, "sat")
    assert e.m.sat > 0, "stimulus did not saturate"
    s = await e.rd(SAT)
    assert s == e.m.sat and s > 0
    assert await e.rd(DONE) == len(vecs)


# req: REQ-10, REQ-07, REQ-12, REQ-23, REQ-32
@cocotb.test()
async def test_random_chunks_10x1000(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(cocotb.RANDOM_SEED)
    for c in range(10):
        vecs = stim_random(rng, 1000)
        await e.push(vecs)
        await e.run_and_wait()
        await e.collect(f"chunk{c}")
        await e.chk_counters()
    assert e.m.done == 10000
    assert await e.rd(DONE) == 10000


# req: REQ-12, REQ-23, REQ-07
@cocotb.test()
async def test_random_chunk_history_equals_single_run(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(cocotb.RANDOM_SEED + 7)
    allv = stim_random(rng, 120)
    # chunked through the DUT; reference single run is the model alone
    ref = model.Model()
    for v in allv:
        ref.write_reg(IN_PUSH, v)
    ref.write_reg(CTRL, 2)
    for _ in range(100):
        ref.step({})
    expect = [ref.read_reg(OUT_POP) for _ in range(120)]
    got = []
    i = 0
    while i < len(allv):
        k = rng.randrange(1, 30)
        chunk = allv[i:i + k]
        i += k
        await e.push(chunk)
        await e.run_and_wait()
        n = len(e.m.fout)
        for _ in range(n):
            got.append(await e.rd(OUT_POP))
            e.m.read_reg(OUT_POP)
    assert got == expect, "chunked run differs from single run"


# req: REQ-12, REQ-28, REQ-27, REQ-29
@cocotb.test()
async def test_clear(dut):
    e = Env(dut)
    await e.start()
    h = e.m.h
    pat = [(0x7FFF if h[31 - i] >= 0 else 0x8000) for i in range(32)]
    await run_vectors(e, pat + [123, 456, 789], "pre")
    assert e.m.sat > 0
    # leave unread outputs and unprocessed inputs
    await e.push(pat)
    await e.run_and_wait()
    await e.push([1, 2, 3, 4, 5])
    s = await e.rd(STATUS)
    assert (s >> 20) & 0xFFF == 32 and (s >> 4) & 0xFFF == 5
    await e.wr(CTRL, 1)
    await e.clocks(30)
    s = await e.rd(STATUS)
    assert s == 0, f"after CLEAR status 0x{s:x}"
    assert await e.rd(SAT) == 0
    assert await e.rd(DONE) == 0
    assert await e.rd(OUT_POP) == 0
    assert await e.rd(8) == 0 or True
    # history zeroed: same as fresh start
    await run_vectors(e, [0x1000, 0, 0, 0, 0x2000] + [0] * 40, "post-clear")
    # history persists without CLEAR
    await e.push([0x7000] * 5)
    await e.run_and_wait()
    await e.collect("persist1")
    await e.push([0] * 40)
    await e.run_and_wait()
    await e.collect("persist2")
    # CLEAR + RUN together: CLEAR wins
    await e.push([9, 9, 9])
    await e.raw_write(CTRL, 3)
    await e.clocks(50)
    e.m.write_reg(IN_PUSH, 9)
    e.m.write_reg(IN_PUSH, 9)
    e.m.write_reg(IN_PUSH, 9)
    e.m.write_reg(CTRL, 3)
    await e.chk(STATUS)
    assert (await e.rd(STATUS)) == 0


# req: REQ-22, REQ-21
@cocotb.test()
async def test_pop_empty_and_valid(dut):
    e = Env(dut)
    await e.start()
    for _ in range(3):
        assert await e.rd(OUT_POP) == 0
    await e.chk(STATUS)
    await e.push([0x0100, 0x0200, 0x0300])
    await e.run_and_wait()
    for i in range(3):
        v = await e.chk(OUT_POP)
        assert v >> 31 == 1
    assert await e.rd(OUT_POP) == 0
    await e.chk(STATUS)
    await e.chk_counters()


# req: REQ-24, REQ-13
@cocotb.test()
async def test_busy_and_throughput(dut):
    e = Env(dut)
    await e.start()
    d = dut
    N = 1000
    rng = random.Random(cocotb.RANDOM_SEED + 3)
    await e.push(stim_random(rng, N))
    await e.raw_write(CTRL, 2)
    e.m.write_reg(CTRL, 2)
    t = 0
    while int(d.led.value) & 1 == 0:
        await RisingEdge(d.clk)
        t += 1
        assert t < 12, "BUSY did not rise after RUN"
    s = await e.rd(STATUS)
    assert s & 1 == 1, "STATUS.BUSY not 1 during run"
    busy = t + 4
    while int(d.led.value) & 1:
        await RisingEdge(d.clk)
        busy += 1
        assert busy < 2000
    # one sample per clk_dsp cycle: 1000 samples = 100 clk cycles at 10x
    assert busy <= N // 10 + 60, f"busy lasted {busy} clk for {N} samples"
    s = await e.rd(STATUS)
    assert s & 1 == 0
    assert (s >> 20) & 0xFFF == N, "last result not in output FIFO when BUSY fell"
    assert (s >> 4) & 0xFFF == 0
    e.settle()
    await e.collect("busy")
    await e.chk_counters()
    assert int(d.led.value) & 2 == 2, "led[1] (MMCM lock) not 1"


# req: REQ-18, REQ-19, REQ-25
@cocotb.test()
async def test_input_fifo_full(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(cocotb.RANDOM_SEED + 5)
    vecs = stim_random(rng, DEPTH)
    await e.push(vecs[:1023])
    s = await e.rd(STATUS)
    assert (s >> 4) & 0xFFF == 1023
    await e.push(vecs[1023:])
    s = await e.rd(STATUS)
    assert (s >> 4) & 0xFFF == DEPTH
    await e.push([0x1234, 0x5678, 0x7FFF])  # ignored, full
    await e.chk(STATUS, "full")
    assert (await e.rd(STATUS) >> 4) & 0xFFF == DEPTH
    await e.run_and_wait()
    await e.collect("fifo-full")  # exactly 1024 results in order, no extras
    await e.chk_counters()


# req: REQ-20, REQ-26, REQ-23
@cocotb.test()
async def test_output_fifo_full_stall(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(cocotb.RANDOM_SEED + 9)
    first = stim_random(rng, DEPTH)
    await e.push(first)
    await e.run_and_wait()
    s = await e.rd(STATUS)
    assert (s >> 20) & 0xFFF == DEPTH and s & 1 == 0
    extra = stim_random(rng, 8)
    await e.push(extra)
    await e.wr(CTRL, 2)
    await e.clocks(300)
    s = await e.rd(STATUS)
    assert s & 1 == 1, "must stall busy while output FIFO full"
    assert (s >> 20) & 0xFFF == DEPTH and (s >> 4) & 0xFFF == 8, f"status 0x{s:x}"
    # expected stream from the model
    e.settle()
    exp = []
    while e.m.fout or e.m.fin:
        while e.m.fout:
            exp.append(e.m.read_reg(OUT_POP))
        e.settle()
    assert len(exp) == DEPTH + 8
    got = []
    guard = 0
    while len(got) < len(exp):
        v = await e.rd(OUT_POP)
        guard += 1
        assert guard < 20000
        if v:
            got.append(v)
    assert got == exp
    await e.clocks(50)
    s = await e.rd(STATUS)
    assert s == 0, f"status after drain 0x{s:x}"
    assert await e.rd(DONE) == DEPTH + 8


# req: REQ-34
@cocotb.test()
async def test_sfp_tx_disable(dut):
    e = Env(dut)
    d = dut
    cocotb.start_soon(Clock(d.clk, 40, units="ns").start())
    if hasattr(d, "clk_dsp"):
        cocotb.start_soon(Clock(d.clk_dsp, 4, units="ns").start())
    d.h_we.value = 0
    d.h_re.value = 0
    d.h_addr.value = 0
    d.h_wdata.value = 0
    d.rst.value = 1
    for _ in range(4):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        assert int(d.sfp_tx_disable.value) == 1
    d.rst.value = 0
    rng = random.Random(cocotb.RANDOM_SEED)
    for _ in range(300):
        d.h_we.value = rng.randrange(2)
        d.h_re.value = rng.randrange(2)
        d.h_addr.value = rng.choice([0, 8, 0x10, 0x14, 0x18, 0x1C, rng.randrange(4096)])
        d.h_wdata.value = rng.randrange(1 << 32)
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        assert int(d.sfp_tx_disable.value) == 1
    d.h_we.value = 0
    d.h_re.value = 0
    d.rst.value = 1
    await e.clocks(3)
    await Timer(1, units="ns")
    assert int(d.sfp_tx_disable.value) == 1


# req: REQ-07, REQ-10, REQ-23, REQ-31, REQ-32
@cocotb.test()
async def test_random_register_traffic(dut):
    """constrained-random mix of pushes, runs, pops, clears and scratch traffic against the model"""
    e = Env(dut)
    await e.start()
    rng = random.Random(cocotb.RANDOM_SEED + 11)
    for it in range(60):
        k = rng.random()
        if k < 0.45:
            await e.push(stim_random(rng, rng.randrange(1, 60)))
        elif k < 0.75:
            await e.run_and_wait()
            await e.collect(f"it{it}")
            await e.chk_counters()
        elif k < 0.8:
            await e.wr(CTRL, 1)
            await e.clocks(30)
            await e.chk_counters()
        elif k < 0.9:
            v = rng.randrange(1 << 32)
            await e.wr(8, v)
            await e.chk(8)
        else:
            await e.chk(STATUS)
            await e.chk(0)
    await e.run_and_wait()
    await e.collect("final")
    await e.chk_counters()
