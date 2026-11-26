import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

CTRL, SNAP = 0x10, 0x30
CNT = {"ww": 0x14, "wr": 0x18, "err": 0x1C, "ovf": 0x20, "unf": 0x24, "stall": 0x28, "occ": 0x2C}


def _has(dut, n):
    return hasattr(dut, n)


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 40, units="ns").start())
    if _has(dut, "gt_refclk"):
        cocotb.start_soon(Clock(dut.gt_refclk, 6.4, units="ns").start())
    else:
        cocotb.start_soon(Clock(dut.gt_refclk_p, 6.4, units="ns").start())
        if _has(dut, "gt_refclk_n"):
            async def inv():
                while True:
                    dut.gt_refclk_n.value = 1 - int(dut.gt_refclk_p.value)
                    await Timer(100, units="ps")
            cocotb.start_soon(inv())
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    dut.rst.value = 1
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)


async def wr(dut, addr, val):
    dut.h_we.value = 1
    dut.h_addr.value = addr
    dut.h_wdata.value = val
    await RisingEdge(dut.clk)
    dut.h_we.value = 0
    await RisingEdge(dut.clk)


async def rd(dut, addr):
    dut.h_re.value = 1
    dut.h_addr.value = addr
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    return int(dut.h_rdata.value)


async def snap(dut):
    await wr(dut, SNAP, 1)
    for _ in range(40):
        await RisingEdge(dut.clk)
    return {k: await rd(dut, a) for k, a in CNT.items()}


async def clocks(dut, n):
    for _ in range(n):
        await RisingEdge(dut.clk)


# req: REQ-01, REQ-27, REQ-22
@cocotb.test()
async def test_reset_and_id(dut):
    await setup(dut)
    m = model.Model()
    assert await rd(dut, 0) == m.read_reg(0) == 0x20950001
    assert await rd(dut, 8) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    assert await rd(dut, CTRL) == 0
    for a in CNT.values():
        assert await rd(dut, a) == 0


# req: REQ-03
@cocotb.test()
async def test_scratch(dut):
    await setup(dut)
    for v in (0xDEADBEEF, 0, 0xFFFFFFFF, 0x12345678):
        await wr(dut, 8, v)
        assert await rd(dut, 8) == v


# req: REQ-04, REQ-28
@cocotb.test()
async def test_unmapped(dut):
    await setup(dut)
    await wr(dut, 8, 0xA5A5A5A5)
    for a in (0x34, 0x38, 0x40, 0x100, 0x7FC, 0xFFC, 0x00C, 0x01):
        assert await rd(dut, a) == 0
        await wr(dut, a, 0xFFFFFFFF)
    assert await rd(dut, 8) == 0xA5A5A5A5
    assert await rd(dut, 0) == 0x20950001
    assert await rd(dut, CTRL) == 0
    assert await rd(dut, SNAP) == 0


# req: REQ-05, REQ-29
@cocotb.test()
async def test_read_latency_hold(dut):
    await setup(dut)
    await wr(dut, 8, 0xCAFEF00D)
    dut.h_re.value = 1
    dut.h_addr.value = 8
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert int(dut.h_rdata.value) == 0xCAFEF00D
    for _ in range(10):
        dut.h_addr.value = random.choice([0, 8, 0x10])
        await RisingEdge(dut.clk)
        assert int(dut.h_rdata.value) == 0xCAFEF00D


# req: REQ-07, REQ-08, REQ-10, REQ-11, REQ-20, REQ-31, REQ-18
@cocotb.test()
async def test_run_basic(dut):
    await setup(dut)
    await wr(dut, CTRL, 1)
    await clocks(dut, 2000)
    s = await snap(dut)
    assert s["ww"] >= 1900
    assert s["wr"] > 0 and s["wr"] <= s["ww"]
    assert s["err"] == 0 and s["ovf"] == 0 and s["unf"] == 0
    assert 1 <= s["occ"] <= 512
    assert int(dut.led.value) & 1 == 1
    # snapshot holds while running
    await clocks(dut, 100)
    assert await rd(dut, CNT["ww"]) == s["ww"]
    # stop: counters hold, FIFO drains
    await wr(dut, CTRL, 0)
    await clocks(dut, 100)
    s2 = await snap(dut)
    assert s2["wr"] == s2["ww"]
    assert s2["err"] == 0 and s2["ovf"] == 0 and s2["unf"] == 0
    await clocks(dut, 50)
    s3 = await snap(dut)
    assert s3 == s2
    # writer writes nothing when RUN 0
    assert s3["ww"] == s2["ww"]


# req: REQ-12, REQ-13, REQ-35, REQ-10, REQ-11, REQ-20, REQ-31, REQ-06
@cocotb.test()
async def test_slow_read_fill(dut):
    await setup(dut)
    await wr(dut, CTRL, 3)
    await clocks(dut, 1500)
    s = await snap(dut)
    assert s["occ"] == 512
    assert s["stall"] > 0
    assert s["ovf"] == 0 and s["unf"] == 0 and s["err"] == 0
    # reader rate: at most 1 word per 8 gt cycles (51.2 ns); clk is 40 ns
    t0 = s
    await clocks(dut, 2000)
    t1 = await snap(dut)
    elapsed_ns = (2000 + 40 + 6) * 40
    max_words = elapsed_ns / 51.2 + 2
    assert 0 < t1["wr"] - t0["wr"] <= max_words
    # stall counts one per held cycle: writer fully backed up, writes track reads
    assert t1["stall"] > t0["stall"]
    assert t1["ww"] - t0["ww"] <= t1["wr"] - t0["wr"] + 2
    assert t1["occ"] == 512


# req: REQ-14, REQ-15, REQ-30
@cocotb.test()
async def test_inject(dut):
    await setup(dut)
    await wr(dut, CTRL, 1 | 8)
    await clocks(dut, 500)
    s = await snap(dut)
    assert s["err"] == 1
    assert int(dut.led.value) & 2 == 2
    assert (await rd(dut, CTRL)) & 8 == 0
    await clocks(dut, 1000)
    s = await snap(dut)
    assert s["err"] == 1
    # a second injection adds exactly one more
    await wr(dut, CTRL, 1 | 8)
    await clocks(dut, 500)
    s = await snap(dut)
    assert s["err"] == 2


# req: REQ-16, REQ-34, REQ-17, REQ-08
@cocotb.test()
async def test_clear(dut):
    await setup(dut)
    await wr(dut, CTRL, 1 | 8)
    await clocks(dut, 800)
    # CLEAR while RUN=1 has no effect
    s_before = await snap(dut)
    await wr(dut, CTRL, 1 | 4)
    await clocks(dut, 100)
    s = await snap(dut)
    assert s["ww"] >= s_before["ww"] and s["err"] == s_before["err"] == 1
    await wr(dut, CTRL, 0)
    await clocks(dut, 200)
    await wr(dut, CTRL, 4)
    await clocks(dut, 20)
    s = await snap(dut)
    assert all(v == 0 for v in s.values())
    assert (await rd(dut, CTRL)) & 4 == 0
    # sequences restarted: a fresh run checks clean
    await wr(dut, CTRL, 1)
    await clocks(dut, 1000)
    s = await snap(dut)
    assert s["wr"] > 0 and s["err"] == 0 and s["ww"] >= 900


# req: REQ-18, REQ-19, REQ-10, REQ-11
@cocotb.test()
async def test_snapshot_coherent(dut):
    await setup(dut)
    await wr(dut, CTRL, 1)
    await clocks(dut, 300)
    await wr(dut, SNAP, 0)
    await clocks(dut, 40)
    a = [await rd(dut, x) for x in CNT.values()]
    await clocks(dut, 300)
    b = [await rd(dut, x) for x in CNT.values()]
    assert a == b  # latched values do not move
    assert a[0] > 0 and a[0] < 2**32 and a[0] >= a[1]


# req: REQ-07, REQ-08, REQ-14, REQ-16, REQ-17, REQ-10, REQ-11, REQ-03
@cocotb.test()
async def test_random_traffic(dut):
    await setup(dut)
    rng = random.Random(cocotb.RANDOM_SEED)
    inj = 0
    for _ in range(12):
        slow = rng.choice([0, 1])
        inject = rng.choice([0, 0, 1])
        inj += inject
        await wr(dut, CTRL, 1 | (slow << 1) | (inject << 3))
        await clocks(dut, rng.randint(200, 900))
        v = rng.getrandbits(32)
        await wr(dut, 8, v)
        assert await rd(dut, 8) == v
        await wr(dut, rng.choice([0x34, 0x40, 0x200]), rng.getrandbits(32))
    await wr(dut, CTRL, 1)
    await clocks(dut, 1500)
    s = await snap(dut)
    assert s["ovf"] == 0 and s["unf"] == 0
    assert s["err"] <= inj
    assert 0 <= s["occ"] <= 512
