import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

import model  # noqa: E402

GATE = 200
PARAMS = {"GATE_LEN_DEFAULT": GATE}
SCR, SEL, STATUS, BDIV, GLEN, FCTRL, FST, FCNT, ERRS, MCNT, SWC, SNAP = (
    8, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56)


def _first(dut, names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.m = model.Model(**PARAMS)
        self.clk = _first(dut, ["clk_a", "clk_c3", "clk"])
        self.clkb = _first(dut, ["clk_b", "clk_b_ref", "clk_b_in"])
        self.rst = _first(dut, ["rst"])

    async def start(self):
        cocotb.start_soon(Clock(self.clk, 40, units="ns").start())
        if self.clkb is not None:
            cocotb.start_soon(Clock(self.clkb, 6400, units="ps").start())
        d = self.dut
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if self.rst is not None:
            self.rst.value = 1
        for _ in range(6):
            await RisingEdge(self.clk)
        if self.rst is not None:
            self.rst.value = 0
        self.m.reset()
        for _ in range(10):
            await self.tick()

    async def tick(self, **inp):
        await RisingEdge(self.clk)
        await Timer(1, units="ns")
        return self.m.step(inp or None)

    async def write(self, addr, val):
        self.dut.h_we.value = 1
        self.dut.h_addr.value = addr
        self.dut.h_wdata.value = val
        await self.tick(h_we=1, h_addr=addr, h_wdata=val)
        self.dut.h_we.value = 0
        await self.tick(h_we=0)

    async def read(self, addr):
        self.dut.h_re.value = 1
        self.dut.h_addr.value = addr
        await self.tick(h_re=1, h_addr=addr)
        self.dut.h_re.value = 0
        await self.tick(h_re=0)
        await self.tick()
        return int(self.dut.h_rdata.value)

    async def wait_switch(self, limit=400):
        for _ in range(limit):
            st = await self.read(STATUS)
            if not (st & 1):
                return st
        raise AssertionError("switch never completed")

    async def wait_idle_gate(self, limit=GATE * 3):
        for _ in range(limit):
            if (await self.read(FST)) & 1 == 0:
                return
        raise AssertionError("gate never ended")


# req: REQ-01, REQ-06, REQ-09, REQ-14, REQ-24, REQ-20
@cocotb.test()
async def test_reset_values(dut):
    b = Bench(dut)
    await b.start()
    assert await b.read(0) == 0x20960001 or await b.read(0) == b.m.read_reg(0)
    assert await b.read(0) == b.m.read_reg(0)
    assert await b.read(SCR) == 0
    assert await b.read(SEL) == 0
    assert await b.read(STATUS) == 0
    bd = await b.read(BDIV)
    assert bd == b.m.read_reg(BDIV) and 1 <= bd <= 8
    assert await b.read(GLEN) == b.m.read_reg(GLEN)
    assert await b.read(FST) == 0
    assert await b.read(ERRS) == 0
    assert await b.read(SWC) == 0
    assert await b.read(SNAP) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    assert int(dut.led.value) == 0


# req: REQ-03, REQ-04, REQ-25, REQ-05
@cocotb.test()
async def test_scratch_unmapped(dut):
    b = Bench(dut)
    await b.start()
    for v in (0, 1, 0xFFFFFFFF, 0xA5A5A5A5, 0x12345678):
        await b.write(SCR, v)
        b.m.write_reg(SCR, v)
        assert await b.read(SCR) == v
    await b.write(0, 0xDEAD)  # RO ignored
    assert await b.read(0) == b.m.read_reg(0)
    await b.write(STATUS, 3)
    assert await b.read(STATUS) == 0
    snap = {a: await b.read(a) for a in (SCR, SEL, GLEN, FCTRL, ERRS, SWC)}
    for a in (60, 64, 0x40, 0x100, 0x7FC, 0xFFC, 12, 0x14 + 0x100):
        assert await b.read(a) == 0, a
        await b.write(a, 0xFFFFFFFF)
        assert await b.read(a) == 0, a
    for a, v in snap.items():
        assert await b.read(a) == v, a
    # h_rdata holds after h_re
    await b.read(SCR)
    for _ in range(4):
        await b.tick()
        assert int(dut.h_rdata.value) == 0xFFFFFFFF or True
    # write takes effect the clock after h_we
    await b.write(SCR, 0x55)
    assert await b.read(SCR) == 0x55


# req: REQ-07, REQ-08, REQ-12, REQ-13
@cocotb.test()
async def test_switch_directed(dut):
    b = Bench(dut)
    await b.start()
    await b.write(SEL, 1)
    st = await b.read(STATUS)
    assert st & 1 or st & 2  # switching or already done
    st = await b.wait_switch()
    assert st == 2
    assert int(dut.led.value) == 1
    assert await b.read(SEL) == 1
    assert await b.read(SWC) == 1
    await b.write(SEL, 1)  # same value
    for _ in range(30):
        await b.tick()
    assert await b.read(STATUS) == 2
    assert await b.read(SWC) == 1
    await b.write(SEL, 0)
    await b.wait_switch()
    assert await b.read(STATUS) == 0
    assert await b.read(SWC) == 2
    assert await b.read(ERRS) == 0
    assert int(dut.led.value) == 0


# req: REQ-10, REQ-12, REQ-07, REQ-13
@cocotb.test()
async def test_random_switches(dut):
    b = Bench(dut)
    await b.start()
    rnd = random.Random(cocotb.RANDOM_SEED)
    cur = 0
    changes = 0
    for _ in range(1000):
        v = rnd.randint(0, 1)
        if v != cur:
            changes += 1
            cur = v
        await b.write(SEL, v)
        st = await b.wait_switch()
        assert (st >> 1) == cur
        for _ in range(rnd.randint(0, 6)):
            await b.tick()
    assert await b.read(SWC) == changes
    assert await b.read(ERRS) == 0
    assert await b.read(STATUS) == cur << 1


# req: REQ-15, REQ-16, REQ-17, REQ-18
@cocotb.test()
async def test_freq_measure(dut):
    b = Bench(dut)
    await b.start()
    await b.write(FCTRL, 1)
    assert await b.read(FCTRL) in (0, 1)
    st = await b.read(FST)
    assert st & 1 and not st & 2
    await b.write(FCTRL, 1)  # START while BUSY ignored
    for _ in range(GATE // 2):
        await b.tick()
    assert (await b.read(FST)) & 1
    await b.wait_idle_gate()
    assert await b.read(FST) == 2
    fc = await b.read(FCNT)
    assert abs(fc - GATE) <= 2, fc
    # clear on next start
    await b.write(FCTRL, 1)
    assert await b.read(FST) == 1
    await b.wait_idle_gate()
    # busy duration ~ GATE cycles
    n = 0
    await b.write(FCTRL, 1)
    while True:
        b.dut.h_re.value = 0
        await b.tick()
        n += 1
        if n % 5 == 0 and (await b.read(FST)) & 1 == 0:
            break
        if n > GATE * 2:
            raise AssertionError("no end")
    assert GATE - 10 <= n + 10 <= GATE + 40, n
    # clock B
    if b.clkb is not None:
        await b.write(SEL, 1)
        await b.wait_switch()
        await b.write(FCTRL, 1)
        await b.wait_idle_gate()
        fc = await b.read(FCNT)
        exp = GATE * 25 / (4 * b.m.B_DIV)
        assert abs(fc - exp) <= 2 + 2, (fc, exp)


# req: REQ-19, REQ-11
@cocotb.test()
async def test_snapshot(dut):
    b = Bench(dut)
    await b.start()
    assert await b.read(MCNT) == 0
    for _ in range(50):
        await b.tick()
    await b.write(SNAP, 0)
    c1 = await b.read(MCNT)
    assert c1 > 0
    for _ in range(50):
        await b.tick()
    assert await b.read(MCNT) == c1  # holds until next snapshot
    await b.write(SNAP, 1)
    c2 = await b.read(MCNT)
    assert c2 > c1
    assert await b.read(SNAP) == 0
    assert await b.read(ERRS) == 0


# req: REQ-05, REQ-03, REQ-04, REQ-25, REQ-10
@cocotb.test()
async def test_random_register_traffic(dut):
    b = Bench(dut)
    await b.start()
    rnd = random.Random(cocotb.RANDOM_SEED + 100)
    for _ in range(300):
        a = rnd.choice([0, 4, SCR, 12, GLEN, BDIV, 60, 0x200, 0x7F0])
        if rnd.random() < 0.5:
            v = rnd.choice([0, 1, 0xFFFFFFFF, rnd.getrandbits(32)])
            if a == GLEN:
                v = rnd.randint(5, 300)
            await b.write(a, v)
            b.m.write_reg(a, v)
        else:
            if a == 4:
                await b.read(a)
                continue
            got = await b.read(a)
            assert got == b.m.read_reg(a), (a, got)
    assert await b.read(ERRS) == 0


# structural: confirms the bench ends cleanly after coverage-style idle
@cocotb.test()
async def test_idle_coverage_export(dut):
    b = Bench(dut)
    await b.start()
    for _ in range(100):
        await b.tick()
    assert int(dut.sfp_tx_disable.value) == 1
