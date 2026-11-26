import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID, BUILD, SCRATCH, CTRL, IN_PUSH, OUT_POP, STATUS, SAT, DONE = 0, 4, 8, 16, 20, 24, 28, 32, 36


class Env:
    def __init__(self, dut):
        self.dut = dut
        self.m = model.Model()

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk25, 40, units="ns").start())
        if hasattr(d, "clk_dsp"):
            cocotb.start_soon(Clock(d.clk_dsp, 4, units="ns").start())
        for n in ("h_we", "h_re", "h_addr", "h_wdata"):
            getattr(d, n).value = 0
        if hasattr(d, "rst"):
            d.rst.value = 1
            for _ in range(8):
                await RisingEdge(d.clk25)
            d.rst.value = 0
        for _ in range(40):
            await RisingEdge(d.clk25)
        self.m.reset()

    async def wr(self, addr, val):
        d = self.dut
        d.h_we.value = 1
        d.h_addr.value = addr
        d.h_wdata.value = val
        await RisingEdge(d.clk25)
        d.h_we.value = 0
        await RisingEdge(d.clk25)
        self.m.write_reg(addr, val)

    async def rd_raw(self, addr):
        d = self.dut
        d.h_re.value = 1
        d.h_addr.value = addr
        await RisingEdge(d.clk25)
        d.h_re.value = 0
        await RisingEdge(d.clk25)
        await RisingEdge(d.clk25)
        await Timer(1, units="ns")
        v = int(d.h_rdata.value)
        return v

    async def rd(self, addr, mask=0xFFFFFFFF, check=True):
        v = await self.rd_raw(addr)
        e = self.m.read_reg(addr)
        if check:
            assert (v & mask) == (e & mask), f"reg {addr:#x}: rtl {v:#x} model {e:#x}"
        return v

    async def push(self, x):
        await self.wr(IN_PUSH, x & 0xFFFF)

    async def run_wait(self, limit=3000):
        await self.wr(CTRL, 2)
        for _ in range(limit):
            s = await self.rd_raw(STATUS)
            if not (s & 1):
                break
        else:
            raise AssertionError("BUSY stuck")
        for _ in range(3000):
            self.m.step()
            if not self.m.busy:
                break

    async def drain(self, n):
        for _ in range(n):
            await self.rd(OUT_POP)

    async def clear(self):
        await self.wr(CTRL, 1)
        await self.rd(STATUS)


def rnd_sample(r):
    c = r.random()
    if c < 0.1:
        return r.choice([0x7FFF, 0x8000, 0, 1, 0xFFFF])
    return r.getrandbits(16)


# req: REQ-01, REQ-03, REQ-32, REQ-25, REQ-26, REQ-35, REQ-27, REQ-36, REQ-19
@cocotb.test()
async def test_registers(dut):
    e = Env(dut)
    await e.start()
    assert await e.rd(ID) == 0x20940001
    assert await e.rd(SCRATCH) == 0
    for v in (0xFFFFFFFF, 0x12345678, 0, 0xA5A5A5A5):
        await e.wr(SCRATCH, v)
        assert await e.rd(SCRATCH) == v
    # hold: value stable until next h_re
    await e.wr(SCRATCH, 0xCAFEF00D)
    v = await e.rd_raw(SCRATCH)
    for _ in range(5):
        await RisingEdge(dut.clk25)
    await Timer(1, units="ns")
    assert int(dut.h_rdata.value) == v == 0xCAFEF00D
    # write effect one clock after h_we
    dut.h_we.value = 1
    dut.h_addr.value = SCRATCH
    dut.h_wdata.value = 0x55
    await RisingEdge(dut.clk25)
    dut.h_we.value = 0
    dut.h_re.value = 1
    await RisingEdge(dut.clk25)
    dut.h_re.value = 0
    await RisingEdge(dut.clk25)
    await RisingEdge(dut.clk25)
    await Timer(1, units="ns")
    assert int(dut.h_rdata.value) == 0x55
    e.m.write_reg(SCRATCH, 0x55)
    # unmapped
    for a in (0x028, 0x02C, 0x040, 0x100, 0x7FC, 0xFFC, 0x00C, 0x01 * 0x30):
        await e.wr(a, 0xDEADBEEF)
        assert await e.rd_raw(a) == 0, f"unmapped {a:#x}"
    assert await e.rd(SCRATCH) == 0x55
    assert await e.rd(STATUS) == 0
    assert await e.rd(SAT) == 0
    assert await e.rd(DONE) == 0
    # CTRL reads 0 after write
    await e.wr(CTRL, 3)
    assert await e.rd_raw(CTRL) == 0
    assert await e.rd_raw(CTRL) == 0
    e.m.reset()
    e.m.write_reg(SCRATCH, 0x55)


# req: REQ-28
@cocotb.test()
async def test_sfp_disable(dut):
    e = Env(dut)
    await e.start()
    for i in range(300):
        assert int(dut.sfp_tx_disable.value) == 1
        if i % 50 == 0:
            await e.wr(CTRL, 3)
            await e.push(i)
        await RisingEdge(dut.clk25)


async def stream_check(e, xs, chunk=None):
    chunk = chunk or len(xs)
    for i in range(0, len(xs), chunk):
        part = xs[i:i + chunk]
        for x in part:
            await e.push(x)
        await e.rd(STATUS)
        await e.run_wait()
        await e.rd(STATUS)
        await e.drain(len(part))
        await e.rd(OUT_POP)  # empty -> 0
        await e.rd(SAT)
        await e.rd(DONE)


# req: REQ-04, REQ-17, REQ-20, REQ-45, REQ-44, REQ-21, REQ-07, REQ-09
@cocotb.test()
async def test_impulse(dut):
    e = Env(dut)
    await e.start()
    xs = [0x4000] + [0] * 39
    await stream_check(e, xs)
    await e.clear()
    xs = [0x7FFF] + [0] * 39
    await stream_check(e, xs)
    await e.clear()
    xs = [0x8000] + [0] * 39
    await stream_check(e, xs)


# req: REQ-05, REQ-17, REQ-09
@cocotb.test()
async def test_step(dut):
    e = Env(dut)
    await e.start()
    await stream_check(e, [0x2000] * 64)
    await e.clear()
    await stream_check(e, [0xE000] * 64)


# req: REQ-10, REQ-23
@cocotb.test()
async def test_saturation(dut):
    e = Env(dut)
    await e.start()
    h = e.m.h
    for sgn in (1, -1):
        xs = [(sgn * (32767 if h[31 - j] >= 0 else -32767)) & 0xFFFF for j in range(32)]
        xs += [0x7FFF if sgn > 0 else 0x8000] * 8
        await stream_check(e, xs)
        sat = await e.rd(SAT)
        assert sat > 0, "no saturation exercised"
        await e.clear()
    # extremes
    await stream_check(e, [0x8000] * 40 + [0x7FFF] * 40)


# req: REQ-06, REQ-08, REQ-17, REQ-24, REQ-23, REQ-33, REQ-34, REQ-22
@cocotb.test()
async def test_random_chunks(dut):
    e = Env(dut)
    await e.start()
    r = random.Random(cocotb.RANDOM_SEED)
    nchunks = int(os.environ.get("FIR_CHUNKS", "10"))
    for c in range(nchunks):
        xs = [rnd_sample(r) if c % 2 else r.getrandbits(16) for _ in range(1000)]
        for x in xs:
            await e.push(x)
        await e.rd(STATUS)
        await e.run_wait()
        await e.rd(STATUS)
        for _ in range(1000):
            await e.rd(OUT_POP)
        await e.rd(SAT)
        await e.rd(DONE)


# req: REQ-06, REQ-17, REQ-08
@cocotb.test()
async def test_random_chunk_sizes(dut):
    e = Env(dut)
    await e.start()
    r = random.Random(cocotb.RANDOM_SEED + 7)
    for _ in range(12):
        n = r.choice([1, 2, 3, 7, 31, 32, 33, 50])
        xs = [rnd_sample(r) for _ in range(n)]
        await stream_check(e, xs)
        if r.random() < 0.25:
            await e.clear()


# req: REQ-15, REQ-42, REQ-16, REQ-33, REQ-34, REQ-22, REQ-11, REQ-17
@cocotb.test()
async def test_fifo_full(dut):
    e = Env(dut)
    await e.start()
    r = random.Random(5)
    xs = [r.getrandbits(16) for _ in range(1024)]
    for x in xs:
        await e.push(x)
    assert (await e.rd(STATUS)) >> 4 & 0xFFF == 1024
    for _ in range(5):
        await e.push(0x1234)  # ignored
    assert (await e.rd(STATUS)) >> 4 & 0xFFF == 1024
    await e.wr(CTRL, 2)
    s = await e.rd_raw(STATUS)
    assert s & 1, "BUSY not set after RUN"
    e.m.step()
    cycles = 0
    while True:
        s = await e.rd_raw(STATUS)
        cycles += 1
        if not s & 1:
            break
        assert cycles < 2000
    # throughput bound: 1024 samples at >=1 per clk_dsp (=10 per clk25) plus overheads
    assert cycles * 3 < 600, f"run took {cycles * 3} clk25 cycles"
    for _ in range(3000):
        e.m.step()
        if not e.m.busy:
            break
    assert (await e.rd(STATUS)) >> 20 == 1024
    assert (await e.rd(DONE)) == 1024
    await e.drain(1024)
    assert (await e.rd(STATUS)) == 0
    assert (await e.rd(OUT_POP)) == 0
    # fill output fifo again while pushing during nothing; refill input
    for x in xs[:10]:
        await e.push(x)
    assert (await e.rd(STATUS)) >> 4 & 0xFFF == 10


# req: REQ-18, REQ-39, REQ-40, REQ-41, REQ-07, REQ-08, REQ-19
@cocotb.test()
async def test_clear_and_history(dut):
    e = Env(dut)
    await e.start()
    r = random.Random(11)
    xs = [r.getrandbits(16) for _ in range(40)]
    await stream_check(e, xs)
    # history persists: second run without clear
    ys = [r.getrandbits(16) for _ in range(40)]
    await stream_check(e, ys)
    # leave outputs and inputs in both fifos, plus saturation
    for x in xs[:10]:
        await e.push(x)
    await e.run_wait()
    for x in ys[:5]:
        await e.push(x)
    h = e.m.h
    for j in range(32):
        await e.push(32767 if h[31 - j] >= 0 else -32767)
    await e.rd(STATUS)
    await e.wr(CTRL, 1)
    st = await e.rd(STATUS)
    assert st == 0
    assert await e.rd(SAT) == 0
    assert await e.rd(DONE) == 0
    assert await e.rd(OUT_POP) == 0
    # after clear, behaves as fresh (history zero)
    await stream_check(e, xs)
    # clear and run together: clear wins
    await e.push(5)
    await e.wr(CTRL, 3)
    await e.rd(STATUS)
    # RUN with empty input FIFO
    await e.wr(CTRL, 2)
    await e.rd(STATUS)
    await e.rd(OUT_POP)


# req: REQ-17, REQ-22
@cocotb.test()
async def test_push_while_busy_and_run_ignored(dut):
    e = Env(dut)
    await e.start()
    r = random.Random(3)
    xs = [r.getrandbits(16) for _ in range(300)]
    for x in xs:
        await e.push(x)
    await e.wr(CTRL, 2)
    # RUN while busy / pushes during run go to next run (model decides ordering by time; keep to settled state)
    await e.run_wait()
    await e.rd(STATUS)
    await e.drain(300)
    # back-to-back runs
    for _ in range(3):
        for x in [r.getrandbits(16) for _ in range(20)]:
            await e.push(x)
        await e.run_wait()
    await e.rd(STATUS)
    await e.drain(60)
