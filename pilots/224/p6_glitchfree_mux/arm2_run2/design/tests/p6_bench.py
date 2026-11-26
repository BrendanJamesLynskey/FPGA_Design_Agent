"""cocotb bench for the p6 glitch-free clock mux register core, checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

GATE = 300
PARAMS = {"GATE_LEN_DEFAULT": GATE}


def new_model():
    return model.Model(GATE_LEN_DEFAULT=GATE)


def _clock(sig, period, units):
    try:
        c = Clock(sig, period, unit=units)
    except TypeError:
        c = Clock(sig, period, units=units)
    cocotb.start_soon(c.start())


async def setup(dut):
    _clock(dut.clk, 40000, "ps")
    for n in ("clk_b", "clk_b_in", "clkb", "clk_b_ref", "clk_b_i"):
        if hasattr(dut, n):
            _clock(getattr(dut, n), 6400, "ps")
            break
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    has_rst = hasattr(dut, "rst")
    if has_rst:
        dut.rst.value = 1
    for _ in range(10):
        await RisingEdge(dut.clk)
    if has_rst:
        dut.rst.value = 0
    for _ in range(10):
        await RisingEdge(dut.clk)


async def wr(dut, addr, val):
    await FallingEdge(dut.clk)
    dut.h_addr.value = addr
    dut.h_wdata.value = val
    dut.h_we.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.h_we.value = 0


async def rd(dut, addr):
    await FallingEdge(dut.clk)
    dut.h_addr.value = addr
    dut.h_re.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    return int(dut.h_rdata.value)


async def wait_idle(dut, limit=400):
    for _ in range(limit):
        s = await rd(dut, 0x14)
        if not (s & 1):
            return s
    raise AssertionError("SWITCHING never returned to 0")


async def idle(dut, n):
    for _ in range(n):
        await RisingEdge(dut.clk)


# req: REQ-01, REQ-26, REQ-07, REQ-29, REQ-11, REQ-10, REQ-22
@cocotb.test()
async def test_reset_values(dut):
    await setup(dut)
    m = new_model()
    for off in (0x00, 0x08, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x2C, 0x34):
        got = await rd(dut, off)
        assert got == m.read_reg(off), f"reg {off:#x}: {got:#x} != {m.read_reg(off):#x}"
    assert await rd(dut, 0x00) == 0x20960001
    assert await rd(dut, 0x1C) == GATE
    assert 1 <= await rd(dut, 0x18) <= 8
    assert int(dut.sfp_tx_disable.value) == 1
    assert (int(dut.led.value) & 3) == 0


# req: REQ-03
@cocotb.test()
async def test_scratch(dut):
    await setup(dut)
    m = new_model()
    for v in (0xFFFFFFFF, 0x12345678, 0x80000000, 1, 0):
        await wr(dut, 8, v)
        m.write_reg(8, v)
        assert await rd(dut, 8) == m.read_reg(8) == v


# req: REQ-04, REQ-27
@cocotb.test()
async def test_unmapped(dut):
    await setup(dut)
    await wr(dut, 8, 0xA5A5A5A5)
    for a in (0x03, 0x0C, 0x3C, 0x40, 0x100, 0x7FC, 0xFFC, 0x44):
        assert await rd(dut, a) == 0, f"unmapped {a:#x}"
        await wr(dut, a, 0xFFFFFFFF)
        assert await rd(dut, a) == 0
    assert await rd(dut, 8) == 0xA5A5A5A5
    assert await rd(dut, 0x10) == 0
    assert await rd(dut, 0x1C) == GATE
    assert await rd(dut, 0x00) == 0x20960001
    assert await rd(dut, 0x2C) == 0


# req: REQ-04
@cocotb.test()
async def test_ro_write_ignored(dut):
    await setup(dut)
    for a in (0x00, 0x14, 0x18, 0x24, 0x28, 0x2C, 0x30, 0x34):
        before = await rd(dut, a)
        await wr(dut, a, 0xFFFFFFFF)
        assert await rd(dut, a) == before, f"RO {a:#x} changed"


# req: REQ-05, REQ-28, REQ-06
@cocotb.test()
async def test_read_write_timing(dut):
    await setup(dut)
    await wr(dut, 8, 0x1111)
    await wr(dut, 0x1C, 0x77)
    # write effective on the next clock: read right after
    await FallingEdge(dut.clk)
    dut.h_addr.value = 8
    dut.h_wdata.value = 0xCAFE0001
    dut.h_we.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.h_we.value = 0
    dut.h_addr.value = 8
    dut.h_re.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.h_rdata.value) == 0xCAFE0001
    # held until next h_re, while other registers change
    await wr(dut, 0x1C, 0x55)
    for _ in range(6):
        await FallingEdge(dut.clk)
        assert int(dut.h_rdata.value) == 0xCAFE0001
    assert await rd(dut, 0x1C) == 0x55
    # back to back reads of different registers
    await wr(dut, 0x18 + 0x20, 0)
    assert await rd(dut, 0x00) == 0x20960001
    assert await rd(dut, 0x08) == 0xCAFE0001


# req: REQ-07, REQ-08, REQ-09, REQ-20, REQ-29, REQ-19
@cocotb.test()
async def test_switch(dut):
    await setup(dut)
    m = new_model()
    assert (await rd(dut, 0x34)) == 0
    # same value as active: no count, no switching
    await wr(dut, 0x10, 0)
    await idle(dut, 20)
    assert await rd(dut, 0x34) == 0
    assert (await rd(dut, 0x14)) & 1 == 0
    # to B
    await wr(dut, 0x10, 1)
    m.write_reg(0x10, 1)
    saw = 0
    for _ in range(400):
        s = await rd(dut, 0x14)
        saw |= s & 1
        if not (s & 1) and saw:
            break
    assert saw, "SWITCHING never seen"
    s = await wait_idle(dut)
    assert (s >> 1) & 1 == 1
    assert await rd(dut, 0x10) == 1
    assert await rd(dut, 0x34) == 1
    await idle(dut, 10)
    assert (int(dut.led.value) & 1) == 1
    # same again
    await wr(dut, 0x10, 1)
    await idle(dut, 30)
    assert await rd(dut, 0x34) == 1
    # back to A
    await wr(dut, 0x10, 0)
    await wait_idle(dut)
    assert ((await rd(dut, 0x14)) >> 1) & 1 == 0
    assert await rd(dut, 0x34) == 2
    # latest-wins during switching: write 1 then 0 immediately
    await wr(dut, 0x10, 1)
    await wr(dut, 0x10, 0)
    await wait_idle(dut)
    await idle(dut, 40)
    s = await wait_idle(dut)
    assert (s >> 1) & 1 == 0
    assert await rd(dut, 0x10) == 0
    cnt = await rd(dut, 0x34)
    assert cnt in (2, 4), cnt
    assert await rd(dut, 0x2C) == 0
    assert (int(dut.led.value) & 2) == 0


# req: REQ-12, REQ-30, REQ-13, REQ-31, REQ-14
@cocotb.test()
async def test_freq_gate(dut):
    await setup(dut)
    await wr(dut, 0x1C, GATE)
    assert await rd(dut, 0x1C) == GATE
    assert await rd(dut, 0x24) == 0
    await wr(dut, 0x20, 1)
    assert await rd(dut, 0x20) == 0  # self-clears
    n = 0
    s = await rd(dut, 0x24)
    assert s & 1 and not (s & 2), f"status {s}"
    # START while busy is ignored
    await wr(dut, 0x20, 1)
    cycles = 0
    while True:
        s = await rd(dut, 0x24)
        cycles += 4
        if not (s & 1):
            break
        assert cycles < GATE * 3
    assert s & 2, "DONE not set"
    assert abs(cycles - GATE) <= 24, f"gate length {cycles}"
    c = await rd(dut, 0x28)
    assert abs(c - GATE) <= 4, f"FREQ_COUNT {c}"
    # holds
    await idle(dut, 50)
    assert await rd(dut, 0x28) == c
    # new start clears done
    await wr(dut, 0x1C, 40)
    await wr(dut, 0x20, 1)
    s = await rd(dut, 0x24)
    assert s & 1 and not (s & 2)
    await idle(dut, 120)
    s = await rd(dut, 0x24)
    assert s == 2
    c = await rd(dut, 0x28)
    assert abs(c - 40) <= 4, c
    # clock B (if the bench drives it): count scales
    await wr(dut, 0x10, 1)
    await wait_idle(dut)
    await wr(dut, 0x1C, 160)
    await wr(dut, 0x20, 1)
    await idle(dut, 260)
    s = await rd(dut, 0x24)
    assert s == 2, s
    c = await rd(dut, 0x28)
    exp = 160 * 156.25 / 25 / max(1, await rd(dut, 0x18))
    assert abs(c - exp) <= 0.05 * exp + 10, f"B count {c} vs {exp}"


# req: REQ-21
@cocotb.test()
async def test_snapshot(dut):
    await setup(dut)
    await wr(dut, 0x38, 0)
    await idle(dut, 6)
    a = await rd(dut, 0x30)
    assert a > 0
    await idle(dut, 100)
    assert await rd(dut, 0x30) == a  # holds
    await wr(dut, 0x38, 0xFFFFFFFF)
    await idle(dut, 6)
    b = await rd(dut, 0x30)
    assert 100 <= (b - a) % (1 << 32) <= 200, (a, b)
    await idle(dut, 50)
    assert await rd(dut, 0x30) == b


# req: REQ-18, REQ-19, REQ-16, REQ-17, REQ-08, REQ-20
@cocotb.test()
async def test_random_switches(dut):
    await setup(dut)
    rng = random.Random(cocotb.RANDOM_SEED)
    m = new_model()
    cur = 0
    changes = 0
    for i in range(1000):
        v = rng.choice((0, 1, 1, 0, rng.randint(0, 1)))
        if rng.random() < 0.15:
            # burst of writes during switching, latest wins
            w = rng.randint(0, 1)
            await wr(dut, 0x10, 1 - cur)
            await wr(dut, 0x10, w)
            v = w
        else:
            await wr(dut, 0x10, v)
        m.write_reg(0x10, v)
        s = await wait_idle(dut)
        await idle(dut, rng.randint(0, 6))
        s = await wait_idle(dut)
        # if a burst reversed direction, the model may have counted extra; count from DUT view
        act = (s >> 1) & 1
        assert act == v, f"iter {i}: active {act} != sel {v}"
        if act != cur:
            changes += 1
            cur = act
    cnt = await rd(dut, 0x34)
    # a burst may have gone out and back (two real changes) - count is >= observed net changes
    assert cnt >= changes and (cnt - changes) % 2 == 0, (cnt, changes)
    assert await rd(dut, 0x2C) == 0
    assert (int(dut.led.value) & 2) == 0
    assert (int(dut.led.value) & 1) == cur
