import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import FallingEdge, Timer  # noqa: E402
from cocotb.utils import get_sim_time  # noqa: E402

CTRL, PUSH, POP, STATUS, SAT, DONE = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
ID = 0x20940001


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.m = model.Model()
        self.rng = random.Random(int(os.environ.get("RANDOM_SEED", "1")) ^ 0x5EED)

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 40, units="ns").start())
        if hasattr(d, "clk_dsp"):
            cocotb.start_soon(Clock(d.clk_dsp, 4, units="ns").start())
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        d.rst.value = 1
        for _ in range(8):
            await FallingEdge(d.clk)
        d.rst.value = 0
        for _ in range(40):
            await FallingEdge(d.clk)
        self.m.reset()

    async def wr(self, addr, val):
        d = self.dut
        await FallingEdge(d.clk)
        d.h_we.value = 1
        d.h_addr.value = addr
        d.h_wdata.value = val & 0xFFFFFFFF
        await FallingEdge(d.clk)
        d.h_we.value = 0
        await FallingEdge(d.clk)
        self.m.write_reg(addr, val)

    async def rd(self, addr):
        d = self.dut
        await FallingEdge(d.clk)
        d.h_re.value = 1
        d.h_addr.value = addr
        await FallingEdge(d.clk)
        d.h_re.value = 0
        await FallingEdge(d.clk)
        await FallingEdge(d.clk)
        return int(d.h_rdata.value)

    async def rd_chk(self, addr, what=""):
        got = await self.rd(addr)
        exp = self.m.read_reg(addr)
        assert got == exp, f"{what} reg 0x{addr:x}: got 0x{got:08x} exp 0x{exp:08x}"
        return got

    def settle_model(self):
        for _ in range(5000):
            if not self.m.busy:
                return
            self.m.step()

    async def run_wait(self):
        await self.wr(CTRL, 2)
        self.settle_model()
        for _ in range(20000):
            s = await self.rd(STATUS)
            if not (s & 1):
                return
        raise AssertionError("run never finished")

    async def push(self, vals):
        for v in vals:
            await self.wr(PUSH, v)

    async def drain_chk(self):
        n = len(self.m.outf)
        for i in range(n):
            await self.rd_chk(POP, f"pop {i}")
        await self.rd_chk(STATUS, "status after drain")

    async def full_check(self, vals):
        await self.push(vals)
        await self.run_wait()
        await self.rd_chk(STATUS, "status")
        await self.rd_chk(SAT, "sat")
        await self.rd_chk(DONE, "done")
        await self.drain_chk()


def s16(v):
    return v & 0xFFFF


# req: REQ-01, REQ-03, REQ-30, REQ-04, REQ-31, REQ-05, REQ-32, REQ-26
@cocotb.test()
async def test_regs_smoke(dut):
    b = Bench(dut)
    await b.start()
    assert await b.rd(0) == ID
    assert await b.rd(8) == 0
    for v in (0xDEADBEEF, 0, 0xFFFFFFFF, 0x12345678):
        await b.wr(8, v)
        assert await b.rd(8) == v
    for a in (0x00C, 0x028, 0x02C, 0x040, 0x100, 0x7FC, 0xFFC, 0x3C):
        assert await b.rd(a) == 0, f"unmapped 0x{a:x}"
    before = [await b.rd(a) for a in (0, 8, 0x1C, 0x20, 0x24)]
    for a in (0x00C, 0x028, 0x100, 0xFFC):
        await b.wr(a, 0xA5A5A5A5)
    after = [await b.rd(a) for a in (0, 8, 0x1C, 0x20, 0x24)]
    assert before == after
    await b.wr(0x04, 0x55)  # RO writes ignored
    assert await b.rd(0) == ID
    # hold
    v = await b.rd(8)
    for _ in range(10):
        await FallingEdge(dut.clk)
        assert int(dut.h_rdata.value) == v
    for _ in range(50):
        await FallingEdge(dut.clk)
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-06, REQ-15, REQ-17, REQ-34, REQ-25, REQ-33, REQ-19, REQ-20, REQ-21, REQ-23
@cocotb.test()
async def test_impulse(dut):
    b = Bench(dut)
    await b.start()
    await b.wr(CTRL, 1)
    b.settle_model()
    await b.push([0x7FFF] + [0] * 39)
    assert (await b.rd(STATUS)) >> 4 & 0xFFF == 40
    await b.run_wait()
    assert await b.rd(CTRL) == 0
    await b.rd_chk(STATUS)
    await b.rd_chk(DONE)
    await b.drain_chk()
    # low 16 bits stored
    await b.push([0xABCD1234, 0x00010005])
    await b.run_wait()
    await b.drain_chk()


# req: REQ-07
@cocotb.test()
async def test_step(dut):
    b = Bench(dut)
    await b.start()
    await b.wr(CTRL, 1)
    await b.full_check([s16(10000)] * 80)


# req: REQ-08, REQ-12
@cocotb.test()
async def test_random_chunks(dut):
    b = Bench(dut)
    await b.start()
    await b.wr(CTRL, 1)
    for c in range(10):
        vals = [b.rng.randrange(0, 65536) for _ in range(1000)]
        await b.full_check(vals)


# req: REQ-09, REQ-10, REQ-24, REQ-35, REQ-36, REQ-37, REQ-38
@cocotb.test()
async def test_history_clear(dut):
    b = Bench(dut)
    await b.start()
    vals = [b.rng.randrange(0, 65536) for _ in range(20)]
    await b.push(vals[:10])
    await b.run_wait()
    await b.push(vals[10:])
    await b.run_wait()  # history persists
    await b.rd_chk(STATUS)
    await b.drain_chk()
    # leave outputs in FIFOs and entries in input FIFO, then clear
    await b.push(vals[:15])
    await b.run_wait()
    await b.push([1, 2, 3])
    await b.wr(CTRL, 1)
    b.settle_model()
    assert await b.rd(CTRL) == 0
    st = await b.rd_chk(STATUS)
    assert st == 0
    assert await b.rd(SAT) == 0 and await b.rd(DONE) == 0
    assert await b.rd(POP) == 0
    await b.full_check([32767] * 5)  # history zero again


# req: REQ-22, REQ-23, REQ-15
@cocotb.test()
async def test_saturation(dut):
    b = Bench(dut)
    await b.start()
    h = b.m.h
    pos = [(32767 if c >= 0 else -32768) & 0xFFFF for c in reversed(h)]
    neg = [(-32768 if c >= 0 else 32767) & 0xFFFF for c in reversed(h)]
    await b.full_check(pos + neg + pos)
    await b.full_check([0x8000, 0x8000, 0x7FFF, 0x7FFF] * 20)


# req: REQ-16, REQ-20, REQ-21, REQ-18
@cocotb.test()
async def test_fifo_full_empty(dut):
    b = Bench(dut)
    await b.start()
    assert await b.rd(POP) == 0
    vals = [b.rng.randrange(0, 65536) for _ in range(1024)]
    await b.push(vals)
    await b.rd_chk(STATUS, "full")
    await b.push([0x1111, 0x2222])  # ignored
    await b.rd_chk(STATUS, "full after extra")
    assert (await b.rd(STATUS)) >> 4 & 0xFFF == 1024
    await b.run_wait()
    st = await b.rd_chk(STATUS)
    assert st >> 20 == 1024 and (st >> 4) & 0xFFF == 0
    await b.rd_chk(DONE)
    await b.drain_chk()
    assert await b.rd(POP) == 0


# req: REQ-19, REQ-25, REQ-12
@cocotb.test()
async def test_busy_rate(dut):
    b = Bench(dut)
    await b.start()
    n = 400
    await b.push([b.rng.randrange(0, 65536) for _ in range(n)])
    await b.wr(CTRL, 2)
    t0 = get_sim_time("ns")
    s = await b.rd(STATUS)
    assert s & 1, "BUSY not set after RUN"
    seen_done = False
    for _ in range(2000):
        s = await b.rd(STATUS)
        if not s & 1:
            seen_done = True
            break
    t1 = get_sim_time("ns")
    assert seen_done
    assert (t1 - t0) <= (n + 80) * 4 + 6 * 40, f"run took {t1 - t0} ns"
    b.settle_model()
    await b.rd_chk(STATUS)
    await b.drain_chk()
    # empty-FIFO RUN completes with no output
    await b.wr(CTRL, 2)
    b.settle_model()
    await Timer(400, units="ns")
    await b.rd_chk(STATUS)


# robustness: random mix of register operations against the model
@cocotb.test()
async def test_random_ops(dut):
    b = Bench(dut)
    await b.start()
    for _ in range(300):
        r = b.rng.random()
        if r < 0.5:
            await b.push([b.rng.randrange(0, 65536) for _ in range(b.rng.randrange(1, 30))])
        elif r < 0.7:
            await b.run_wait()
            await b.rd_chk(STATUS)
            await b.rd_chk(SAT)
            await b.rd_chk(DONE)
        elif r < 0.9:
            for _ in range(b.rng.randrange(1, 10)):
                await b.rd_chk(POP)
        elif r < 0.95:
            await b.wr(8, b.rng.getrandbits(32))
            await b.rd_chk(8)
        else:
            await b.wr(CTRL, 1)
            b.settle_model()
            await b.rd_chk(STATUS)
