import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

GATE = 200
SCRATCH, SEL, STATUS, BDIV, GLEN, FCTRL, FSTAT, FCNT, ERRS, MCNT, SWC, SNAP = (
    8, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56)


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 40, units="ns").start())
    if hasattr(dut, "gt_clk"):
        cocotb.start_soon(Clock(dut.gt_clk, 6400, units="ps").start())
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    dut.rst.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)


async def wr(dut, a, v):
    dut.h_we.value = 1
    dut.h_addr.value = a
    dut.h_wdata.value = v
    await RisingEdge(dut.clk)
    dut.h_we.value = 0
    await RisingEdge(dut.clk)


async def rd(dut, a):
    dut.h_re.value = 1
    dut.h_addr.value = a
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    return int(dut.h_rdata.value)


async def wait_switch(dut, tmo=4096):
    for _ in range(tmo):
        if (await rd(dut, STATUS)) & 1 == 0:
            return
    assert False, "switch timeout"


# req: REQ-01, REQ-03, REQ-25, REQ-16, REQ-06, REQ-09, REQ-29
@cocotb.test()
async def test_reset_and_regs(dut):
    await setup(dut)
    m = model.Model(GATE_LEN_DEFAULT=GATE)
    assert await rd(dut, 0) == 0x20960001
    assert await rd(dut, SCRATCH) == 0
    assert await rd(dut, SEL) == m.read_reg(SEL) == 0
    assert await rd(dut, GLEN) == GATE
    assert await rd(dut, BDIV) == m.read_reg(BDIV)
    assert await rd(dut, SNAP) == 0
    for v in (0xA5A5A5A5, 0xFFFFFFFF, 0x12345678, 0):
        await wr(dut, SCRATCH, v)
        assert await rd(dut, SCRATCH) == v
    await wr(dut, GLEN, 0x01234567)
    assert await rd(dut, GLEN) == 0x01234567
    await wr(dut, GLEN, GATE)


# req: REQ-04, REQ-26, REQ-05, REQ-27
@cocotb.test()
async def test_unmapped_and_read_hold(dut):
    await setup(dut)
    await wr(dut, SCRATCH, 0xCAFEF00D)
    for a in (0x0C, 0x3C, 0x40, 0x100, 0x7FC, 0xFFC):
        await wr(dut, a, 0xFFFFFFFF)
        assert await rd(dut, a) == 0
    assert await rd(dut, SCRATCH) == 0xCAFEF00D
    assert await rd(dut, SEL) == 0
    # hold until next h_re
    dut.h_re.value = 1
    dut.h_addr.value = SCRATCH
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    dut.h_addr.value = 0x0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    for _ in range(6):
        assert int(dut.h_rdata.value) == 0xCAFEF00D
        await RisingEdge(dut.clk)
        await Timer(1, units="ns")


# req: REQ-28, REQ-07, REQ-08, REQ-14, REQ-15, REQ-10, REQ-11, REQ-12, REQ-13
@cocotb.test()
async def test_switching(dut):
    await setup(dut)
    assert (await rd(dut, STATUS)) == 0
    await wr(dut, SEL, 0)
    assert await rd(dut, SWC) == 0
    await wr(dut, SEL, 1)
    await wait_switch(dut)
    assert (await rd(dut, STATUS)) == 2
    assert int(dut.led.value) & 1 == 1
    assert await rd(dut, SWC) == 1
    await wr(dut, SEL, 1)
    for _ in range(50):
        await RisingEdge(dut.clk)
    assert await rd(dut, SWC) == 1
    await wr(dut, SEL, 0)
    await wait_switch(dut)
    assert (await rd(dut, STATUS)) == 0
    assert await rd(dut, SWC) == 2
    assert await rd(dut, ERRS) == 0


# req: REQ-11, REQ-14, REQ-10
@cocotb.test()
async def test_random_switches(dut):
    await setup(dut)
    rnd = random.Random(int(cocotb.RANDOM_SEED) if hasattr(cocotb, "RANDOM_SEED") else 1)
    cur = 0
    n = 0
    for _ in range(100):
        new = rnd.getrandbits(1)
        await wr(dut, SEL, new)
        if new != cur:
            n += 1
            cur = new
        await wait_switch(dut)
        assert ((await rd(dut, STATUS)) >> 1) == cur
    assert await rd(dut, SWC) == n
    assert await rd(dut, ERRS) == 0


# req: REQ-17, REQ-18, REQ-19, REQ-20
@cocotb.test()
async def test_frequency_and_snapshot(dut):
    await setup(dut)
    m = model.Model(GATE_LEN_DEFAULT=GATE)
    await wr(dut, GLEN, GATE)
    await wr(dut, FCTRL, 1)
    assert await rd(dut, FCTRL) == 0
    st = await rd(dut, FSTAT)
    assert st & 1 == 1 and st & 2 == 0
    await wr(dut, FCTRL, 1)  # ignored while busy
    n = 0
    while (await rd(dut, FSTAT)) & 1:
        n += 1
        assert n < 1000
    assert (await rd(dut, FSTAT)) & 2
    exp = GATE  # clock A: one edge per C3 cycle
    got = await rd(dut, FCNT)
    assert abs(got - exp) <= 2, (got, exp)
    # clock B
    await wr(dut, SEL, 1)
    await wait_switch(dut)
    await wr(dut, FCTRL, 1)
    assert (await rd(dut, FSTAT)) & 2 == 0
    while (await rd(dut, FSTAT)) & 1:
        pass
    got = await rd(dut, FCNT)
    exp = GATE * 6.25 / m.p["B_DIV_VALUE"]
    assert abs(got - exp) <= 0.05 * exp + 2, (got, exp)
    # snapshot
    a = await rd(dut, MCNT)
    await wr(dut, SNAP, 1)
    b = await rd(dut, MCNT)
    assert b != a or b != 0
    await wr(dut, SNAP, 0)
    c = await rd(dut, MCNT)
    assert c != b


# req: REQ-21
@cocotb.test()
async def test_outputs(dut):
    await setup(dut)
    for _ in range(200):
        assert int(dut.sfp_tx_disable.value) == 1
        await RisingEdge(dut.clk)
    await wr(dut, SEL, 1)
    for _ in range(100):
        assert int(dut.sfp_tx_disable.value) == 1
        await RisingEdge(dut.clk)
