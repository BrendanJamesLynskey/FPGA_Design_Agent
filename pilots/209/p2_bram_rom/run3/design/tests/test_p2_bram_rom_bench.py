"""cocotb bench for the p2_mem_test register core, checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID = 0x20920001
OFF = dict(ID=0, BUILD=4, SCRATCH=8, MEM_ADDR=16, ROM=20, RAM=24, MEM_CTRL=28,
           CTRL=32, PASSES=36, STATUS=40, ERRS=44, FIRST=48)
M32 = 0xFFFFFFFF


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 40, units="ns").start())
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    await do_reset(dut)
    return model.Model()


async def do_reset(dut):
    if hasattr(dut, "rst"):
        dut.rst.value = 1
        for _ in range(10):
            await RisingEdge(dut.clk)
        dut.rst.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)


async def wr(dut, addr, val):
    dut.h_addr.value = addr
    dut.h_wdata.value = val
    dut.h_we.value = 1
    await RisingEdge(dut.clk)
    dut.h_we.value = 0


async def rd(dut, addr):
    dut.h_addr.value = addr
    dut.h_re.value = 1
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    v = int(dut.h_rdata.value)
    return v


async def idle(dut, n):
    for _ in range(n):
        await RisingEdge(dut.clk)


async def expect(dut, m, off, what=""):
    got = await rd(dut, off)
    exp = m.read_reg(off)
    assert got == exp, f"{what} reg 0x{off:x}: rtl 0x{got:08x} model 0x{exp:08x}"
    return got


async def wr_both(dut, m, off, val):
    await wr(dut, off, val)
    m.write_reg(off, val)


async def check_all(dut, m, what=""):
    for name in ("ID", "SCRATCH", "MEM_ADDR", "MEM_CTRL", "CTRL", "PASSES",
                 "STATUS", "ERRS", "FIRST"):
        await expect(dut, m, OFF[name], what)


async def run_march(dut, m, passes, ctrl_extra=0, limit=40000):
    await wr_both(dut, m, OFF["PASSES"], passes)
    await wr(dut, OFF["CTRL"], 1 | ctrl_extra)
    m.write_reg(OFF["CTRL"], 1 | ctrl_extra)
    while m.busy:
        m.step()
    waited = 0
    while True:
        await idle(dut, 200)
        st = await rd(dut, OFF["STATUS"])
        if not (st & 1):
            break
        waited += 1
        assert waited < limit // 200 * passes + 100, "march did not finish"
    return st


# req: REQ-01, REQ-24, REQ-19, REQ-20, REQ-10
@cocotb.test()
async def test_reset_values(dut):
    m = await setup(dut)
    assert await rd(dut, 0) == ID
    await check_all(dut, m, "reset")
    assert await rd(dut, OFF["FIRST"]) == M32
    assert await rd(dut, OFF["PASSES"]) == 1
    assert int(dut.sfp_tx_disable.value) == 1
    assert int(dut.led.value) == 0
    # hold: rdata stable without a new read
    v = int(dut.h_rdata.value)
    await idle(dut, 3)
    assert int(dut.h_rdata.value) == v
    # scratch reset after a write then reset
    await wr(dut, OFF["SCRATCH"], 0xDEADBEEF)
    assert await rd(dut, OFF["SCRATCH"]) == 0xDEADBEEF
    if hasattr(dut, "rst"):
        await do_reset(dut)
        assert await rd(dut, OFF["SCRATCH"]) == 0
        assert await rd(dut, OFF["MEM_ADDR"]) == 0
        assert await rd(dut, OFF["PASSES"]) == 1
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-03, REQ-24, REQ-01, REQ-11, REQ-26
@cocotb.test()
async def test_scratch_and_ro(dut):
    m = await setup(dut)
    for v in (0, M32, 0x12345678, 0xA5A5A5A5, 0x5A5A5A5A, 1, 0x80000000):
        await wr_both(dut, m, OFF["SCRATCH"], v)
        assert await rd(dut, OFF["SCRATCH"]) == v
    # byte address low bits ignored
    await wr(dut, 0x0B, 0x77)
    m.write_reg(8, 0x77)
    assert await rd(dut, 0x09) == 0x77
    # writes to RO registers ignored
    for off in (0, 20, 40, 44, 48):
        await wr(dut, off, 0x1234)
    assert await rd(dut, 0) == ID
    await check_all(dut, m, "ro")
    # unmapped
    for off in (0x0C, 0x34, 0x38, 0x3C, 0x40, 0x100, 0x7FC, 0x800, 0xFFC):
        assert await rd(dut, off) == 0, f"unmapped 0x{off:x}"
        await wr(dut, off, 0xFFFFFFFF)
    await check_all(dut, m, "after unmapped writes")


# req: REQ-04, REQ-06, REQ-08, REQ-10
@cocotb.test()
async def test_rom(dut):
    m = await setup(dut)
    # no autoinc: address unchanged
    await wr_both(dut, m, OFF["MEM_ADDR"], 5)
    for _ in range(3):
        await expect(dut, m, OFF["ROM"], "rom")
        assert await rd(dut, OFF["MEM_ADDR"]) == 5
    # MEM_ADDR upper bits read 0
    await wr_both(dut, m, OFF["MEM_ADDR"], 0xFFFFFC01)
    assert await rd(dut, OFF["MEM_ADDR"]) == m.read_reg(OFF["MEM_ADDR"])
    # full sweep with autoinc
    await wr_both(dut, m, OFF["MEM_CTRL"], 1)
    await wr_both(dut, m, OFF["MEM_ADDR"], 0)
    for i in range(1024):
        got = await rd(dut, OFF["ROM"])
        assert got == m.rom[i], f"rom[{i}] rtl {got:08x} model {m.rom[i]:08x}"
        m.read_reg(OFF["ROM"])
        if i in (0, 1, 1022, 1023):
            assert await rd(dut, OFF["MEM_ADDR"]) == (i + 1) % 1024
    assert await rd(dut, OFF["MEM_ADDR"]) == 0  # wrapped
    assert m.addr == 0


# req: REQ-05, REQ-07, REQ-08, REQ-09, REQ-10
@cocotb.test()
async def test_ram_host(dut):
    m = await setup(dut)
    await wr_both(dut, m, OFF["MEM_CTRL"], 1)
    await wr_both(dut, m, OFF["MEM_ADDR"], 0)
    for i in range(1024):
        got = await rd(dut, OFF["RAM"])
        assert got == (0xC0DE0000 + i) & M32, f"ram init {i}: {got:08x}"
        m.read_reg(OFF["RAM"])
    assert await rd(dut, OFF["MEM_ADDR"]) == 0
    # autoinc writes, wrap
    await wr_both(dut, m, OFF["MEM_ADDR"], 1020)
    for k in range(8):
        await wr_both(dut, m, OFF["RAM"], 0x1000 + k)
    assert await rd(dut, OFF["MEM_ADDR"]) == 4
    # read back
    await wr_both(dut, m, OFF["MEM_ADDR"], 1020)
    for k in range(8):
        got = await expect(dut, m, OFF["RAM"], "ram")
    # no autoinc: write then read same address
    await wr_both(dut, m, OFF["MEM_CTRL"], 0)
    await wr_both(dut, m, OFF["MEM_ADDR"], 77)
    await wr_both(dut, m, OFF["RAM"], 0xCAFEF00D)
    assert await rd(dut, OFF["MEM_ADDR"]) == 77
    assert await rd(dut, OFF["RAM"]) == 0xCAFEF00D
    await wr_both(dut, m, OFF["RAM"], 0x0BADBEEF)
    assert await rd(dut, OFF["RAM"]) == 0x0BADBEEF
    assert await rd(dut, OFF["MEM_ADDR"]) == 77
    # neighbours untouched
    for a in (76, 78):
        await wr_both(dut, m, OFF["MEM_ADDR"], a)
        await expect(dut, m, OFF["RAM"], "neighbour")
    assert await rd(dut, OFF["MEM_CTRL"]) == 0


# req: REQ-12, REQ-13, REQ-17, REQ-18, REQ-19, REQ-16
@cocotb.test()
async def test_march_clean(dut):
    m = await setup(dut)
    # leave RAM in a non-initial state first
    await wr_both(dut, m, OFF["MEM_ADDR"], 3)
    await wr_both(dut, m, OFF["RAM"], 0x13572468)
    passes = 3
    await wr_both(dut, m, OFF["PASSES"], passes)
    await wr(dut, OFF["CTRL"], 1)
    m.write_reg(OFF["CTRL"], 1)
    await idle(dut, 4)
    st = await rd(dut, OFF["STATUS"])
    assert st & 1 == 1 and st & 2 == 0, "busy after start"
    assert int(dut.led.value) & 1 == 1
    assert await rd(dut, OFF["CTRL"]) & 1 == 0  # START reads back 0
    # host RAM access ignored during BUSY
    await wr(dut, OFF["RAM"], 0xFFFFFFFF)
    assert await rd(dut, OFF["RAM"]) == 0
    # START while busy ignored: passes completed keeps growing monotonic
    await wr(dut, OFF["CTRL"], 1)
    last = 0
    while True:
        await idle(dut, 3000)
        st = await rd(dut, OFF["STATUS"])
        pc = st >> 16
        assert pc >= last and pc <= passes
        last = pc
        if not st & 1:
            break
    while m.busy:
        m.step()
    await check_all(dut, m, "clean")
    st = await rd(dut, OFF["STATUS"])
    assert st == (2 | (passes << 16)), f"status {st:08x}"
    assert await rd(dut, OFF["ERRS"]) == 0
    assert await rd(dut, OFF["FIRST"]) == M32
    assert int(dut.led.value) == 2
    # RAM all zero
    await wr_both(dut, m, OFF["MEM_CTRL"], 1)
    await wr_both(dut, m, OFF["MEM_ADDR"], 0)
    for i in range(1024):
        got = await rd(dut, OFF["RAM"])
        assert got == 0, f"ram[{i}] = {got:08x} after march"
    # restart clears DONE and passes completed
    await wr(dut, OFF["PASSES"], 1)
    await wr(dut, OFF["CTRL"], 1)
    await idle(dut, 4)
    st = await rd(dut, OFF["STATUS"])
    assert st & 3 == 1 and (st >> 16) == 0, f"restart status {st:08x}"
    assert await rd(dut, OFF["ERRS"]) == 0
    assert await rd(dut, OFF["FIRST"]) == M32
    while (await rd(dut, OFF["STATUS"])) & 1:
        await idle(dut, 500)
    assert (await rd(dut, OFF["STATUS"])) == (2 | (1 << 16))


# req: REQ-14, REQ-15, REQ-16, REQ-18, REQ-12
@cocotb.test()
async def test_march_fault(dut):
    m = await setup(dut)
    m1 = model.Model()
    st = await run_march(dut, m1, 1, ctrl_extra=2)
    per_pass = m1.errs
    assert per_pass >= 1
    assert await rd(dut, OFF["ERRS"]) == per_pass
    assert await rd(dut, OFF["FIRST"]) == 0 == m1.first
    assert await rd(dut, OFF["CTRL"]) == 2
    # 3 passes: errors scale with passes, first error address stays
    st = await run_march(dut, m, 3, ctrl_extra=2)
    assert m.errs == 3 * per_pass
    assert await rd(dut, OFF["ERRS"]) == m.errs > 0
    assert await rd(dut, OFF["FIRST"]) == m.first
    assert (await rd(dut, OFF["STATUS"])) == (2 | (3 << 16))
    # RAM zero after faulty run too (fault is in the checker only)
    await wr_both(dut, m, OFF["MEM_ADDR"], 0)
    for a in (0, 1, 511, 1023):
        await wr(dut, OFF["MEM_ADDR"], a)
        assert await rd(dut, OFF["RAM"]) == 0
    # clean run afterwards clears the error state
    await wr(dut, OFF["CTRL"], 0)
    m.write_reg(OFF["CTRL"], 0)
    st = await run_march(dut, m, 1)
    assert await rd(dut, OFF["ERRS"]) == 0
    assert await rd(dut, OFF["FIRST"]) == M32


# req: REQ-13, REQ-18
@cocotb.test()
async def test_march_passes_count(dut):
    m = await setup(dut)
    # many-pass behaviour (spec: 200; bench uses 6 to stay short); 0 treated as 1
    st = await run_march(dut, m, 6)
    assert (await rd(dut, OFF["STATUS"])) == (2 | (6 << 16)) == m.read_reg(OFF["STATUS"])
    st = await run_march(dut, m, 0)
    assert (await rd(dut, OFF["STATUS"])) == m.read_reg(OFF["STATUS"])
    assert int(dut.led.value) == 2


# req: REQ-03, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-26, REQ-12, REQ-20
@cocotb.test()
async def test_random_traffic(dut):
    m = await setup(dut)
    rng = random.Random(cocotb.RANDOM_SEED)
    offs = [0, 4, 8, 16, 20, 24, 28, 32, 36, 40, 44, 48,
            0x0C, 0x14 + 0x40, 0x34, 0x100, 0xFFC]
    cls = (0, 1, M32, None)
    for n in range(600):
        off = rng.choice(offs)
        if off in (32,):
            val = rng.choice((0, 2))  # no START in the random phase
        elif off == 36:
            val = rng.choice((1, 2, 3))
        else:
            c = rng.choice(cls)
            val = rng.getrandbits(32) if c is None else c
        low = rng.randrange(4)
        if rng.random() < 0.45:
            await wr(dut, off | low, val)
            m.write_reg(off, val)
            # let the write settle (address/BRAM pipeline) before the next op
            await idle(dut, rng.randrange(2, 5))
        else:
            if off == 4:
                await rd(dut, off | low)  # BUILD not modelled
                continue
            got = await rd(dut, off | low)
            exp = m.read_reg(off)
            assert got == exp, f"op{n} off 0x{off:x}: rtl {got:08x} model {exp:08x}"
        assert int(dut.sfp_tx_disable.value) == 1
    # a short run to end, then random fault run
    await wr(dut, OFF["CTRL"], 0)
    m.write_reg(OFF["CTRL"], 0)
    inj = rng.choice((0, 2))
    await run_march(dut, m, rng.choice((1, 2)), ctrl_extra=inj)
    await check_all(dut, m, "random end")
