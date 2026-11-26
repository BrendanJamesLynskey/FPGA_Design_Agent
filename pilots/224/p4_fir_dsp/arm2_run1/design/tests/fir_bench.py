import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

ID = 0x20940001
DEPTH = 1024


def _clock(sig, ns):
    try:
        c = Clock(sig, ns, unit="ns")
    except TypeError:
        c = Clock(sig, ns, units="ns")
    cocotb.start_soon(c.start())


def _has(dut, n):
    return hasattr(dut, n)


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.bus = next(n for n in ("clk_bus", "clk", "clk_25") if _has(dut, n))
        self.m = Model()
        self.rng = random.Random(getattr(cocotb, "RANDOM_SEED", 1))

    async def start(self):
        d = self.dut
        _clock(getattr(d, self.bus), 40)
        if _has(d, "clk_dp"):
            _clock(d.clk_dp, 4)
        for n in ("rst", "rst_bus", "rst_dp"):
            if _has(d, n):
                getattr(d, n).value = 1
        if _has(d, "rst_n"):
            d.rst_n.value = 0
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        for _ in range(10):
            await RisingEdge(getattr(d, self.bus))
        for n in ("rst", "rst_bus", "rst_dp"):
            if _has(d, n):
                getattr(d, n).value = 0
        if _has(d, "rst_n"):
            d.rst_n.value = 1
        await self.idle(60)
        self.m.reset()

    async def idle(self, n):
        for _ in range(n):
            await RisingEdge(getattr(self.dut, self.bus))

    async def write(self, addr, val):
        d = self.dut
        d.h_we.value = 1
        d.h_addr.value = addr
        d.h_wdata.value = val
        await RisingEdge(getattr(d, self.bus))
        d.h_we.value = 0
        await RisingEdge(getattr(d, self.bus))

    async def read(self, addr):
        d = self.dut
        clk = getattr(d, self.bus)
        d.h_re.value = 1
        d.h_addr.value = addr
        await RisingEdge(clk)
        d.h_re.value = 0
        await RisingEdge(clk)
        await RisingEdge(clk)
        await Timer(1, "ns")
        return int(d.h_rdata.value)

    # model side
    def mwrite(self, addr, val):
        self.m.write_reg(addr, val)

    def mrun_done(self):
        n = 0
        while self.m.busy and n < 100000:
            self.m.step()
            n += 1

    async def push(self, samples):
        for s in samples:
            await self.write(20, s & 0xFFFF)
            self.mwrite(20, s & 0xFFFF)

    async def run_and_wait(self):
        self.mwrite(16, 2)
        self.mrun_done()
        exp = len(self.m.out)
        await self.write(16, 2)
        for _ in range(3000):
            st = await self.read(28)
            if (st & 1) == 0 and (st >> 20) == exp:
                return
        raise AssertionError("run did not finish, expected %d outputs" % exp)

    async def pop_all(self, check=True):
        got = []
        while self.m.out:
            exp = self.m.read_reg(24)
            v = await self.read(24)
            assert v == exp, "OUT_POP %#x != model %#x" % (v, exp)
            got.append(v)
        return got

    async def check_status(self):
        await self.idle(20)
        exp = self.m.read_reg(28)
        st = await self.read(28)
        assert st == exp, "STATUS %#x != model %#x" % (st, exp)

    async def process(self, samples):
        await self.push(samples)
        await self.run_and_wait()
        return await self.pop_all()

    async def clear(self):
        self.mwrite(16, 1)
        await self.write(16, 1)
        await self.idle(20)


async def setup(dut):
    b = Bench(dut)
    await b.start()
    return b


# req: REQ-01, REQ-30, REQ-25, REQ-04
@cocotb.test()
async def test_reset_values(dut):
    b = await setup(dut)
    assert await b.read(0) == ID
    assert await b.read(8) == 0
    for r in (24, 28, 32, 36):
        assert await b.read(r) == b.m.read_reg(r) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    assert int(dut.led.value) == 0


# req: REQ-03
@cocotb.test()
async def test_scratch(dut):
    b = await setup(dut)
    for v in (0xFFFFFFFF, 0x12345678, 0x80000001, 0, 0xA5A5A5A5):
        await b.write(8, v)
        assert await b.read(8) == v
    for i in range(32):
        await b.write(8, 1 << i)
        assert await b.read(8) == 1 << i


# req: REQ-04, REQ-05
@cocotb.test()
async def test_unmapped(dut):
    b = await setup(dut)
    await b.write(8, 0xCAFEF00D)
    await b.push([5, 6, 7])
    bad = [0x00C, 0x02C, 0x030, 0x040, 0x100, 0x800, 0xFFC, 0x03C, 0x400, 0x014 + 0x1000 - 0x1000 + 0x400]
    for a in bad:
        assert await b.read(a) == 0, hex(a)
    for a in bad:
        await b.write(a, 0xFFFFFFFF)
    await b.write(0, 0xFFFFFFFF)
    await b.write(4, 0xFFFFFFFF)
    assert await b.read(0) == ID
    assert await b.read(8) == 0xCAFEF00D
    await b.check_status()
    assert await b.read(32) == 0 and await b.read(36) == 0
    await b.clear()


# req: REQ-06, REQ-31
@cocotb.test()
async def test_read_timing_hold(dut):
    b = await setup(dut)
    d = dut
    clk = getattr(d, b.bus)
    await b.write(8, 0x55AA1234)
    d.h_re.value = 1
    d.h_addr.value = 8
    await RisingEdge(clk)
    d.h_re.value = 0
    d.h_addr.value = 0x28  # address changes after the pulse
    await RisingEdge(clk)
    await RisingEdge(clk)
    await Timer(1, "ns")
    assert int(d.h_rdata.value) == 0x55AA1234
    for _ in range(8):
        await RisingEdge(clk)
        await Timer(1, "ns")
        assert int(d.h_rdata.value) == 0x55AA1234
    d.h_addr.value = 0
    assert await b.read(0) == ID
    await b.idle(5)
    assert int(d.h_rdata.value) == ID


# req: REQ-07, REQ-18
@cocotb.test()
async def test_impulse(dut):
    b = await setup(dut)
    await b.process([32767] + [0] * 40)
    await b.clear()
    await b.process([1] + [0] * 40)
    await b.clear()
    await b.process([-32768] + [0] * 40)
    assert await b.read(36) == b.m.read_reg(36)
    await b.clear()


# req: REQ-08, REQ-18
@cocotb.test()
async def test_step(dut):
    b = await setup(dut)
    await b.process([1000] * 80)
    await b.clear()
    await b.process([-20000] * 70)
    await b.clear()


# req: REQ-09, REQ-10, REQ-18, REQ-24, REQ-23
@cocotb.test()
async def test_random_chunks(dut):
    b = await setup(dut)
    for c in range(10):
        if c == 4:
            xs = [b.rng.choice((32767, -32768)) for _ in range(1000)]
        else:
            amp = b.rng.choice((300, 8000, 32767))
            xs = [b.rng.randint(-amp, amp) for _ in range(1000)]
        await b.process(xs)
    await b.check_status()
    assert await b.read(32) == b.m.read_reg(32)
    assert await b.read(36) == b.m.read_reg(36) == 10000
    await b.clear()


# req: REQ-10
@cocotb.test()
async def test_history_persists_and_clear_history(dut):
    b = await setup(dut)
    await b.process([30000] * 16)
    await b.process([0] * 40)  # tail depends on history
    await b.process([12345] * 5)
    await b.clear()
    # after clear: history is zero
    await b.process([0] * 3 + [777] + [0] * 40)
    assert await b.read(36) == b.m.read_reg(36)
    await b.clear()


# req: REQ-12
@cocotb.test()
async def test_throughput_one_per_cycle(dut):
    b = await setup(dut)
    await b.push([b.rng.randint(-30000, 30000) for _ in range(DEPTH)])
    await b.idle(10)
    clk = getattr(dut, "clk_dp") if _has(dut, "clk_dp") else getattr(dut, b.bus)
    b.mwrite(16, 2)
    b.mrun_done()
    await b.write(16, 2)
    cyc = 0
    done = False
    while cyc < 2400:
        await RisingEdge(clk)
        cyc += 1
        if cyc % 50 == 0:
            # sample output count straight from the register (read is slow in bus clocks; use few)
            pass
        if cyc == 1200:
            break
    # after ~1200 dp cycles (1024 + latency + bus sync) the run must be done
    for _ in range(5):
        st = await b.read(28)
        if (st & 1) == 0 and (st >> 20) == DEPTH:
            done = True
            break
    assert done, "1024 samples not processed within 1200 clk_dp cycles + margin"
    await b.pop_all()
    await b.clear()


# req: REQ-14, REQ-32, REQ-22, REQ-15, REQ-33
@cocotb.test()
async def test_fifo_depth_and_full(dut):
    b = await setup(dut)
    xs = [b.rng.randint(-32768, 32767) for _ in range(DEPTH)]
    await b.push(xs)
    await b.check_status()
    # push to full: ignored
    await b.push([1, 2, 3])
    await b.check_status()
    st = await b.read(28)
    assert (st >> 4) & 0xFFF == DEPTH
    await b.run_and_wait()
    await b.check_status()
    st = await b.read(28)
    assert (st >> 20) == DEPTH and (st >> 4) & 0xFFF == 0
    # output FIFO full: push more, RUN processes nothing
    await b.push([9, 8, 7])
    b.mwrite(16, 2)
    await b.write(16, 2)
    await b.idle(60)
    await b.check_status()
    # drain and check order, count
    await b.pop_all()
    await b.check_status()
    # now the three remain; run them
    await b.run_and_wait()
    await b.pop_all()
    await b.check_status()
    await b.clear()


# req: REQ-16, REQ-34, REQ-17
@cocotb.test()
async def test_pop_semantics(dut):
    b = await setup(dut)
    assert await b.read(24) == 0
    assert await b.read(24) == 0
    await b.process([100, 200, 300, 400])
    assert await b.read(24) == 0
    await b.push([5, -5, 7])
    await b.run_and_wait()
    n = len(b.m.out)
    await b.check_status()
    v = await b.read(24)
    exp = b.m.read_reg(24)
    assert v == exp and (v >> 31) == 1
    await b.check_status()
    assert (await b.read(28) >> 20) == n - 1
    await b.pop_all()
    assert await b.read(24) == 0


# req: REQ-19, REQ-20, REQ-21, REQ-24, REQ-23
@cocotb.test()
async def test_ctrl_clear_status(dut):
    b = await setup(dut)
    await b.push([32767] * 40)
    await b.run_and_wait()
    await b.push([1, 2, 3])
    assert await b.read(16) == 0
    await b.check_status()
    assert await b.read(32) == b.m.read_reg(32) > 0
    assert await b.read(36) == b.m.read_reg(36) == 40
    assert int(dut.led.value) & 2 == 2
    # busy: observe BUSY during a long run
    await b.clear()
    assert await b.read(28) == 0
    assert await b.read(32) == 0 and await b.read(36) == 0
    assert await b.read(24) == 0
    assert int(dut.led.value) == 0
    # history zero after clear
    await b.process([1000] * 3)
    await b.clear()
    await b.push([3000] * 600)
    await b.idle(10)
    b.mwrite(16, 2)
    b.mrun_done()
    await b.write(16, 2)
    seen_busy = False
    for _ in range(200):
        st = await b.read(28)
        if st & 1:
            seen_busy = True
            assert int(dut.led.value) & 1 == 1
        if not (st & 1) and (st >> 20) == 600:
            break
    assert (await b.read(28)) & 1 == 0
    await b.pop_all()
    # CLEAR while busy aborts
    await b.push([2000] * 900)
    await b.idle(10)
    await b.write(16, 2)
    await b.write(16, 1)
    b.mwrite(16, 1)
    await b.idle(40)
    st = await b.read(28)
    assert st == 0, hex(st)
    assert await b.read(36) == 0
    assert await b.read(24) == 0
    assert int(dut.sfp_tx_disable.value) == 1
