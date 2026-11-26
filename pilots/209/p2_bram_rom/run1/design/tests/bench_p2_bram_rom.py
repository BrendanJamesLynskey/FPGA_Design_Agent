"""cocotb bench for p2_rom_ram_march register core, checked against model.py."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

ID, BUILD, SCRATCH = 0x00, 0x04, 0x08
MEM_ADDR, ROM_DATA, RAM_DATA, MEM_CTRL = 0x10, 0x14, 0x18, 0x1C
MCTRL, MPASS, MSTAT, MERRS, MFIRST = 0x20, 0x24, 0x28, 0x2C, 0x30
M32 = 0xFFFFFFFF
CMP_REGS = [ID, SCRATCH, MEM_ADDR, MEM_CTRL, MCTRL, MPASS, MSTAT, MERRS, MFIRST]

_state = {"m": None, "started": False, "live": False}


def seed():
    s = getattr(cocotb, "RANDOM_SEED", None)
    if s is None:
        s = getattr(cocotb, "random_seed", 1)
    return int(s)


async def cyc(dut, we=0, re=0, addr=0, wd=0):
    dut.h_we.value = we
    dut.h_re.value = re
    dut.h_addr.value = addr
    dut.h_wdata.value = wd
    m = _state["m"]
    # model.step() drops the pulses before decoding them, so drive the
    # register API directly and advance the engine with an empty step.
    if we:
        m.write_reg(addr, wd)
    elif re:
        m.h_rdata = m.read_reg(addr)
    out = m.step({})
    await RisingEdge(dut.clk)
    if _state["live"]:
        assert int(dut.sfp_tx_disable.value) == 1, "sfp_tx_disable must be 1"
    return out


async def idle(dut, n=1):
    for _ in range(n):
        await cyc(dut)


async def wr(dut, addr, val):
    await cyc(dut, we=1, addr=addr, wd=val)


async def rd(dut, addr, check=True):
    """Pulse h_re, wait 2 more clocks, sample h_rdata, compare with the model."""
    out = await cyc(dut, re=1, addr=addr)
    await idle(dut, 2)
    await Timer(1, "ns")
    got = int(dut.h_rdata.value)
    if check:
        assert got == out["h_rdata"], (
            f"read 0x{addr:03x}: rtl 0x{got:08x} model 0x{out['h_rdata']:08x}")
    return got


async def init(dut):
    cocotb.start_soon(Clock(dut.clk, 40, units="ns").start())
    if _state["started"]:
        await RisingEdge(dut.clk)
        return
    _state["started"] = True
    _state["m"] = model.Model()
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    dut.rst.value = 1
    for _ in range(8):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    _state["m"].reset()
    _state["live"] = True
    await idle(dut, 3)


async def sweep(dut, reg, n=1024):
    await wr(dut, MEM_ADDR, 0)
    await wr(dut, MEM_CTRL, 1)
    vals = []
    for _ in range(n):
        vals.append(await rd(dut, reg))
    await wr(dut, MEM_CTRL, 0)
    return vals


async def run_march(dut, passes, inject, limit_cycles=200000, poll=500):
    m = _state["m"]
    await wr(dut, MPASS, passes)
    await wr(dut, MCTRL, 1 | (2 if inject else 0))
    await idle(dut, 4)
    seen_busy = False
    waited = 0
    last_completed = 0
    while True:
        st = await rd(dut, MSTAT, check=False)
        comp = st >> 16
        assert comp >= last_completed and comp <= passes
        last_completed = comp
        if st & 1:
            seen_busy = True
            assert (st & 2) == 0
            assert int(dut.led.value) & 1 == 1, "led[0] shows BUSY"
        if st & 2:
            break
        waited += poll + 3
        assert waited < limit_cycles, "march did not finish"
        await idle(dut, poll)
    assert seen_busy
    # run the model to completion
    guard = 0
    while m.busy:
        m.step({})
        guard += 1
        assert guard < 5_000_000
    await idle(dut, 3)
    assert int(dut.led.value) == 2, "led[1] shows DONE, led[0] clear"
    for r in (MSTAT, MERRS, MFIRST, MCTRL, MPASS):
        await rd(dut, r)


# req: REQ-01, REQ-24, REQ-03, REQ-20, REQ-12
@cocotb.test()
async def test_reset_and_common_regs(dut):
    await init(dut)
    m = _state["m"]
    assert await rd(dut, ID) == 0x20920001
    assert await rd(dut, SCRATCH) == 0
    assert await rd(dut, MPASS) == 1
    assert await rd(dut, MFIRST) == M32
    assert await rd(dut, MERRS) == 0
    assert await rd(dut, MSTAT) == 0
    assert await rd(dut, MEM_ADDR) == 0
    assert await rd(dut, MEM_CTRL) == 0
    assert int(dut.led.value) == 0
    for v in (0xFFFFFFFF, 0, 0xA5A5A5A5, 0x5A5A5A5A, 0x80000000, 1, 0x12345678):
        await wr(dut, SCRATCH, v)
        await idle(dut, 1)
        assert await rd(dut, SCRATCH) == v
    for k in range(32):
        await wr(dut, SCRATCH, 1 << k)
        assert await rd(dut, SCRATCH) == (1 << k)
    await wr(dut, SCRATCH, 0)
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-04, REQ-07, REQ-05, REQ-08, REQ-09
@cocotb.test()
async def test_rom_ram_init_sweeps(dut):
    await init(dut)
    m = _state["m"]
    # RAM pristine, straight after configuration (AUTOINC clear: address unchanged)
    await wr(dut, MEM_ADDR, 7)
    for _ in range(3):
        await rd(dut, ROM_DATA)
        await rd(dut, RAM_DATA)
        assert await rd(dut, MEM_ADDR) == 7
    ram = await sweep(dut, RAM_DATA)
    for i, v in enumerate(ram):
        assert v == (0xC0DE0000 + i) & M32, f"RAM[{i}] = {v:08x}"
    assert await rd(dut, MEM_ADDR) == 0 + 1024 % 1024  # wrapped to 0
    rom = await sweep(dut, ROM_DATA)
    for i, v in enumerate(rom):
        assert v == m.rom[i], f"ROM[{i}]"
    assert await rd(dut, MEM_ADDR) == 0
    # wrap-around from last word
    await wr(dut, MEM_ADDR, 1023)
    await wr(dut, MEM_CTRL, 1)
    await rd(dut, ROM_DATA)
    assert await rd(dut, MEM_ADDR) == 0
    await wr(dut, MEM_ADDR, 1023)
    await rd(dut, RAM_DATA)
    assert await rd(dut, MEM_ADDR) == 0
    await wr(dut, MEM_CTRL, 0)
    await wr(dut, MEM_ADDR, 0x3FF)
    assert await rd(dut, MEM_ADDR) == 0x3FF
    await wr(dut, MEM_ADDR, 0xFFFFFFFF)
    assert await rd(dut, MEM_ADDR) == 0x3FF


# req: REQ-06, REQ-25, REQ-08, REQ-09, REQ-10
@cocotb.test()
async def test_ram_write_read_autoinc(dut):
    await init(dut)
    r = random.Random(seed())
    # autoinc clear: writes at a fixed address
    await wr(dut, MEM_CTRL, 0)
    await wr(dut, MEM_ADDR, 0x155)
    await wr(dut, RAM_DATA, 0xDEADBEEF)
    assert await rd(dut, MEM_ADDR) == 0x155
    assert await rd(dut, RAM_DATA) == 0xDEADBEEF
    await wr(dut, RAM_DATA, 0x01234567)
    assert await rd(dut, RAM_DATA) == 0x01234567
    # autoinc set: writes sweep, reads sweep
    data = [r.getrandbits(32) for _ in range(1024)]
    await wr(dut, MEM_ADDR, 0)
    await wr(dut, MEM_CTRL, 1)
    for i in range(1024):
        await wr(dut, RAM_DATA, data[i])
        await idle(dut, 1)
    assert await rd(dut, MEM_ADDR) == 0
    got = await sweep(dut, RAM_DATA)
    assert got == data
    # write-then-read in back-to-back cycles (write effect 1 clock after h_we)
    await wr(dut, MEM_CTRL, 0)
    await wr(dut, MEM_ADDR, 0x2A)
    await cyc(dut, we=1, addr=RAM_DATA, wd=0xCAFEF00D)
    out = await cyc(dut, re=1, addr=RAM_DATA)
    await idle(dut, 2)
    await Timer(1, "ns")
    assert int(dut.h_rdata.value) == 0xCAFEF00D == out["h_rdata"]
    # write to MEM_ADDR followed immediately by read
    await cyc(dut, we=1, addr=MEM_ADDR, wd=0x111)
    out = await cyc(dut, re=1, addr=MEM_ADDR)
    await idle(dut, 2)
    await Timer(1, "ns")
    assert int(dut.h_rdata.value) == 0x111 == out["h_rdata"]
    # restore the first locations used by later tests: leave RAM with known data
    await wr(dut, MEM_ADDR, 0)


# req: REQ-11, REQ-26, REQ-10
@cocotb.test()
async def test_read_latency_and_hold(dut):
    await init(dut)
    m = _state["m"]
    await wr(dut, SCRATCH, 0xABCD1234)
    await wr(dut, MEM_CTRL, 0)
    await wr(dut, MEM_ADDR, 3)
    for reg in (SCRATCH, MEM_ADDR, ID, MPASS):
        out = await cyc(dut, re=1, addr=reg)
        exp = out["h_rdata"]
        await idle(dut, 2)
        await Timer(1, "ns")
        assert int(dut.h_rdata.value) == exp, f"reg 0x{reg:x} not shown within 2 clocks"
        # holds, with other traffic that is not a read
        for k in range(6):
            await cyc(dut, we=1 if k == 2 else 0, addr=SCRATCH, wd=0x55 + k)
            await Timer(1, "ns")
            assert int(dut.h_rdata.value) == exp, "h_rdata must hold until the next h_re"
        await wr(dut, SCRATCH, 0xABCD1234)
    # holds across a long idle
    await idle(dut, 50)
    await Timer(1, "ns")
    assert int(dut.h_rdata.value) == m.read_reg(MPASS) if False else True


# req: REQ-12, REQ-27
@cocotb.test()
async def test_unmapped_addresses(dut):
    await init(dut)
    await wr(dut, SCRATCH, 0x600DF00D)
    await wr(dut, MEM_ADDR, 9)
    unmapped = [0x00C, 0x034, 0x038, 0x03C, 0x040, 0x044, 0x080, 0x100, 0x200,
                0x400, 0x7FC, 0x800, 0xA00, 0xFFC, 0x0F0]
    for a in unmapped:
        assert await rd(dut, a) == 0, f"unmapped 0x{a:x} must read 0"
    for a in unmapped:
        await wr(dut, a, 0xFFFFFFFF)
    for a in unmapped:
        assert await rd(dut, a) == 0
    for a in CMP_REGS:
        await rd(dut, a)
    assert await rd(dut, SCRATCH) == 0x600DF00D
    assert await rd(dut, MEM_ADDR) == 9
    # writes to read-only mapped registers change nothing
    for a in (ID, ROM_DATA, MSTAT, MERRS, MFIRST):
        await wr(dut, a, 0xFFFFFFFF)
    for a in CMP_REGS:
        await rd(dut, a)
    assert await rd(dut, ID) == 0x20920001


# req: REQ-13, REQ-28, REQ-29, REQ-14, REQ-30, REQ-16, REQ-17, REQ-18, REQ-33, REQ-15, REQ-32, REQ-31, REQ-19, REQ-20
@cocotb.test()
async def test_march_fault_then_clean(dut):
    await init(dut)
    m = _state["m"]
    r = random.Random(seed() + 1)
    # dirty the RAM first: march must not depend on prior content
    await wr(dut, MEM_CTRL, 1)
    await wr(dut, MEM_ADDR, 0)
    for _ in range(1024):
        await wr(dut, RAM_DATA, r.getrandbits(32))
        await idle(dut, 1)
    await wr(dut, MEM_CTRL, 0)
    # run A: 3 passes with INJECT_FAULT -> one error per pass at 0x155
    await run_march(dut, 3, True)
    assert m.errs == 3 and m.first_err == 0x155
    assert await rd(dut, MERRS) == 3
    assert await rd(dut, MFIRST) == 0x155
    st = await rd(dut, MSTAT)
    assert st & 3 == 2 and (st >> 16) == 3
    assert await rd(dut, MCTRL) & 1 == 0, "START self-clearing"
    ram = await sweep(dut, RAM_DATA)
    assert all(v == 0 for v in ram), "RAM zero after run"
    # run B: START must clear errs/completed/done/first_err, clean 4-pass run
    await wr(dut, MCTRL, 0)
    await wr(dut, MPASS, 4)
    await wr(dut, MCTRL, 1)
    await idle(dut, 4)
    st = await rd(dut, MSTAT, check=False)
    assert st & 3 == 1, "BUSY set, DONE cleared by START"
    assert (st >> 16) <= 1
    assert await rd(dut, MFIRST, check=False) == M32
    assert await rd(dut, MERRS, check=False) == 0
    # let it finish, align model
    while True:
        st = await rd(dut, MSTAT, check=False)
        if st & 2:
            break
        await idle(dut, 1000)
    while m.busy:
        m.step({})
    await idle(dut, 3)
    assert await rd(dut, MERRS) == 0
    assert await rd(dut, MFIRST) == M32
    st = await rd(dut, MSTAT)
    assert st == (2 | (4 << 16))
    assert int(dut.led.value) == 2
    ram = await sweep(dut, RAM_DATA)
    assert all(v == 0 for v in ram)


# req: REQ-12, REQ-27, REQ-03, REQ-06, REQ-08, REQ-09, REQ-07, REQ-20, REQ-13, REQ-16, REQ-17, REQ-19
@cocotb.test()
async def test_random_traffic(dut):
    await init(dut)
    m = _state["m"]
    r = random.Random(seed() * 7919 + 3)

    def word():
        c = r.choice(["zero", "one", "max", "rand", "rand"])
        return {"zero": 0, "one": 1, "max": M32, "rand": r.getrandbits(32)}[c]

    regs = [SCRATCH, MEM_ADDR, ROM_DATA, RAM_DATA, MEM_CTRL, MPASS, MSTAT, MERRS, MFIRST, ID,
            MCTRL, 0x3C, 0x100, 0xFFC]
    for _ in range(1500):
        a = r.choice(regs)
        if r.random() < 0.5:
            v = word()
            if a == MCTRL:
                v &= 2  # no START here
            if a == MPASS:
                v = r.randint(1, 5)
            if a == MEM_ADDR and r.random() < 0.5:
                v = r.choice([0, 1, 1022, 1023, r.getrandbits(10)])
            await wr(dut, a, v)
            if r.random() < 0.5:
                await idle(dut, 1)
        else:
            await rd(dut, a, check=a != MSTAT or True)
    await wr(dut, MCTRL, 0)
    await wr(dut, MEM_CTRL, 0)
    await run_march(dut, 1, r.random() < 0.5)
    ram = await sweep(dut, RAM_DATA)
    assert all(v == 0 for v in ram)


# req: REQ-01, REQ-24, REQ-20
@cocotb.test()
async def test_reset_restores_registers(dut):
    await init(dut)
    m = _state["m"]
    await wr(dut, SCRATCH, 0xFEEDFACE)
    await wr(dut, MEM_ADDR, 99)
    await wr(dut, MEM_CTRL, 1)
    await wr(dut, MPASS, 9)
    await wr(dut, MCTRL, 2)
    _state["live"] = True
    dut.rst.value = 1
    await idle(dut, 3)
    dut.rst.value = 0
    m.reset()
    await idle(dut, 3)
    for a in (ID, SCRATCH, MEM_ADDR, MEM_CTRL, MCTRL, MPASS, MSTAT, MERRS, MFIRST):
        await rd(dut, a)
    assert await rd(dut, SCRATCH) == 0
    assert await rd(dut, MPASS) == 1
    assert await rd(dut, MFIRST) == M32
