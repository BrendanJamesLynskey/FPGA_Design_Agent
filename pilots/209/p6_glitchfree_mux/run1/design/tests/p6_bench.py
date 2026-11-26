"""cocotb bench for the P6 glitch-free clock mux register core, checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

GATE = 200  # GATE_LEN_DEFAULT override (same value given to the model)
PARAMS = {"GATE_LEN_DEFAULT": GATE}

ID, BUILD, SCRATCH = 0x00, 0x04, 0x08
SEL, STATUS, B_DIV, GATE_LEN, FREQ_CTRL, FREQ_STATUS = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
FREQ_COUNT, MUX_ERRS, MUX_COUNT, SWITCH_COUNT, SNAPSHOT = 0x28, 0x2C, 0x30, 0x34, 0x38


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.m = model.Model(**PARAMS)
        self.cycles = 0

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 40, units="ns").start())
        # optional extra clock inputs of the core (names unknown to the bench)
        if hasattr(d, "gt_refclk_p"):
            cocotb.start_soon(Clock(d.gt_refclk_p, 6.4, units="ns").start())
            if hasattr(d, "gt_refclk_n"):
                d.gt_refclk_n.value = 0
        if hasattr(d, "clk_b"):
            cocotb.start_soon(Clock(d.clk_b, 12.8, units="ns").start())
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        d.rst.value = 1
        for _ in range(6):
            await RisingEdge(d.clk)
        d.rst.value = 0
        self.m.reset()
        for _ in range(10):
            await self.tick()

    async def tick(self, n=1):
        for _ in range(n):
            await RisingEdge(self.dut.clk)
            self.m.step()
            self.cycles += 1

    async def write(self, addr, val, model_too=True):
        d = self.dut
        d.h_addr.value = addr
        d.h_wdata.value = val
        d.h_we.value = 1
        await self.tick()
        d.h_we.value = 0
        if model_too:
            self.m.write_reg(addr, val)
        await self.tick()

    async def read(self, addr):
        d = self.dut
        d.h_addr.value = addr
        d.h_re.value = 1
        await self.tick()
        d.h_re.value = 0
        await self.tick(2)
        return int(d.h_rdata.value)

    async def check(self, addr, what=""):
        got = await self.read(addr)
        exp = self.m.read_reg(addr)
        assert got == exp, f"{what} reg 0x{addr:x}: rtl {got:#x} model {exp:#x}"
        return got

    async def wait_switched(self, timeout=300):
        for _ in range(timeout):
            s = await self.read(STATUS)
            if not (s & 1):
                return s
        raise AssertionError("SWITCHING never cleared")

    async def snap(self):
        await self.write(SNAPSHOT, 1)
        await self.tick(6)
        return await self.read(MUX_COUNT)

    async def go(self, sel):
        """write SEL and wait until the switch is complete; return when settled."""
        await self.write(SEL, sel)
        s = await self.wait_switched()
        assert (s >> 1) & 1 == sel, "ACTIVE_SEL != SEL after switch"
        # model settles on its own timer
        await self.tick(8)
        return s

    async def gate(self, timeout=None):
        """START a gate and return (busy_cycles, freq_count)."""
        await self.write(FREQ_CTRL, 1)
        n = 0
        timeout = timeout or (GATE * 4 + 200)
        while n < timeout:
            st = await self.read(FREQ_STATUS)
            n += 4
            if not (st & 1):
                assert st & 2, "DONE not set at gate end"
                break
        else:
            raise AssertionError("gate never finished")
        return n, await self.read(FREQ_COUNT)


async def setup(dut):
    b = Bench(dut)
    await b.start()
    return b


# req: REQ-01, REQ-25, REQ-06, REQ-17, REQ-10, REQ-21, REQ-05
@cocotb.test()
async def test_reset_values(dut):
    b = await setup(dut)
    assert await b.read(ID) == 0x20960001
    await b.check(ID, "ID")
    for a in (SCRATCH, SEL, STATUS, B_DIV, GATE_LEN, FREQ_CTRL, FREQ_STATUS,
              FREQ_COUNT, MUX_ERRS, SWITCH_COUNT):
        await b.check(a, "reset")
    assert await b.read(SCRATCH) == 0
    assert await b.read(SEL) == 0
    assert await b.read(GATE_LEN) == GATE
    bd = await b.read(B_DIV)
    assert bd == 2 and 1 <= bd <= 8
    assert int(dut.sfp_tx_disable.value) == 1
    assert int(dut.led.value) == 0


# req: REQ-03, REQ-25, REQ-26, REQ-04
@cocotb.test()
async def test_scratch_and_unmapped(dut):
    b = await setup(dut)
    for v in (0, 1, 0xFFFFFFFF, 0x12345678, 0x80000000, 0xA5A5A5A5):
        await b.write(SCRATCH, v)
        assert await b.read(SCRATCH) == v
        await b.check(SCRATCH)
    await b.write(SCRATCH, 0xCAFEBABE)
    snapshot_before = {a: await b.read(a) for a in (ID, SCRATCH, SEL, STATUS, B_DIV, GATE_LEN,
                                                    FREQ_CTRL, FREQ_STATUS, SWITCH_COUNT, MUX_ERRS)}
    for a in (0x0C, 0x3C, 0x40, 0x44, 0x80, 0x100, 0x404, 0x800, 0xFFC):
        assert await b.read(a) == 0, f"unmapped 0x{a:x} not 0"
        await b.write(a, 0xFFFFFFFF, model_too=False)
        assert await b.read(a) == 0, f"unmapped 0x{a:x} not 0 after write"
    for a, v in snapshot_before.items():
        assert await b.read(a) == v, f"reg 0x{a:x} changed by unmapped write"
    # ID is read-only
    await b.write(ID, 0, model_too=False)
    assert await b.read(ID) == 0x20960001


# req: REQ-05, REQ-27
@cocotb.test()
async def test_read_latency_and_hold(dut):
    b = await setup(dut)
    d = dut
    await b.write(SCRATCH, 0x11223344)
    d.h_addr.value = SCRATCH
    d.h_re.value = 1
    await b.tick()
    d.h_re.value = 0
    await b.tick(2)
    assert int(d.h_rdata.value) == 0x11223344, "not valid within 2 clocks"
    # held while the register changes and the address bus moves
    d.h_addr.value = ID
    d.h_wdata.value = 0x55555555
    d.h_we.value = 1
    await b.tick()
    d.h_we.value = 0
    d.h_addr.value = SEL
    for _ in range(12):
        await b.tick()
        assert int(d.h_rdata.value) == 0x11223344, "h_rdata did not hold"
    # write takes effect the clock after h_we
    d.h_addr.value = SCRATCH
    d.h_wdata.value = 0x99
    d.h_we.value = 1
    await b.tick()
    d.h_we.value = 0
    d.h_re.value = 1
    await b.tick()
    d.h_re.value = 0
    await b.tick(2)
    assert int(d.h_rdata.value) == 0x99


# req: REQ-07, REQ-08, REQ-14, REQ-15, REQ-21, REQ-22, REQ-23, REQ-24
@cocotb.test()
async def test_switching(dut):
    b = await setup(dut)
    # write of current value: nothing happens
    await b.write(SEL, 0)
    await b.tick(10)
    assert await b.read(STATUS) == 0
    assert await b.read(SWITCH_COUNT) == 0
    # A -> B: SWITCHING seen high right after the write
    d = dut
    d.h_addr.value = SEL
    d.h_wdata.value = 1
    d.h_we.value = 1
    await b.tick()
    d.h_we.value = 0
    b.m.write_reg(SEL, 1)
    seen = False
    for _ in range(3):
        await b.tick()
        if int(d.led.value) & 2:
            seen = True
    s = await b.read(STATUS)
    assert seen or s & 1 or (s >> 1) & 1, "SWITCHING never observed"
    s = await b.wait_switched()
    assert s == 2
    await b.tick(8)
    assert int(d.led.value) == 1, "led[0]=ACTIVE_SEL, led[1]=0"
    assert await b.read(SEL) == 1
    assert await b.read(SWITCH_COUNT) == 1
    await b.write(SEL, 1)
    await b.tick(20)
    assert await b.read(SWITCH_COUNT) == 1
    assert await b.read(STATUS) == 2
    await b.go(0)
    assert await b.read(SWITCH_COUNT) == 2
    assert await b.read(STATUS) == 0
    assert int(d.led.value) == 0
    assert int(d.sfp_tx_disable.value) == 1
    assert await b.read(MUX_ERRS) == 0


# req: REQ-07, REQ-08, REQ-14
@cocotb.test()
async def test_sel_write_while_switching(dut):
    b = await setup(dut)
    # 1 then 0 straight away: final state follows the last write (A)
    await b.write(SEL, 1)
    await b.write(SEL, 0)
    s = await b.wait_switched()
    await b.tick(10)
    assert await b.read(SEL) == 0
    assert (await b.read(STATUS)) == 0
    assert (await b.read(SWITCH_COUNT)) in (0, 1, 2)
    base = await b.read(SWITCH_COUNT)
    # 1, then 0, then 1: final B
    await b.write(SEL, 1)
    await b.write(SEL, 0)
    await b.write(SEL, 1)
    await b.wait_switched()
    await b.tick(10)
    assert await b.read(STATUS) == 2
    assert await b.read(SEL) == 1
    cnt = await b.read(SWITCH_COUNT)
    assert base + 1 <= cnt <= base + 3
    assert await b.read(MUX_ERRS) == 0


# req: REQ-12, REQ-13, REQ-16
@cocotb.test()
async def test_snapshot_and_errors(dut):
    b = await setup(dut)
    assert await b.read(MUX_COUNT) == 0
    c1 = await b.snap()
    assert c1 > 0
    await b.tick(100)
    c2 = await b.snap()
    # the register holds between snapshots
    await b.tick(50)
    assert await b.read(MUX_COUNT) == c2
    diff = (c2 - c1) & 0xFFFFFFFF
    # clock A: one count per clk; elapsed cycles ~ 100 + snapshot overhead
    assert 100 <= diff <= 160, f"A diff {diff}"
    await b.go(1)
    c3 = await b.snap()
    await b.tick(100)
    c4 = await b.snap()
    diff = (c4 - c3) & 0xFFFFFFFF
    # clock B: 3.125 counts per clk
    assert 3.125 * 100 * 0.85 <= diff <= 3.125 * 170, f"B diff {diff}"
    assert await b.read(MUX_ERRS) == 0
    await b.go(0)
    assert await b.read(MUX_ERRS) == 0


# req: REQ-18, REQ-28, REQ-19, REQ-29, REQ-20, REQ-17
@cocotb.test()
async def test_frequency_gate(dut):
    b = await setup(dut)
    assert await b.read(FREQ_STATUS) == 0
    await b.write(FREQ_CTRL, 1)
    assert await b.read(FREQ_CTRL) == 0, "START must self-clear"
    st = await b.read(FREQ_STATUS)
    assert st & 1 and not st & 2, "BUSY not set during gate"
    n = 0
    while True:
        st = await b.read(FREQ_STATUS)
        n += 4
        if not st & 1:
            break
        assert not st & 2, "DONE set while BUSY"
        assert n < GATE * 3
    assert st & 2
    assert n >= GATE - 40, "gate too short"
    fc = await b.read(FREQ_COUNT)
    assert abs(fc - GATE) <= 3, f"A freq count {fc}"
    # a new START clears DONE
    await b.write(FREQ_CTRL, 1)
    st = await b.read(FREQ_STATUS)
    assert st & 1 and not st & 2
    # START while BUSY ignored: gate is not extended
    await b.write(FREQ_CTRL, 1)
    while (await b.read(FREQ_STATUS)) & 1:
        pass
    # mux on B
    await b.go(1)
    _, fc = await b.gate()
    exp = GATE * 3.125
    assert abs(fc - exp) <= 8, f"B freq count {fc} vs {exp}"
    # different gate length
    await b.write(GATE_LEN, 100)
    assert await b.read(GATE_LEN) == 100
    _, fc = await b.gate()
    assert abs(fc - 312.5) <= 8, f"B freq count {fc}"
    await b.go(0)
    _, fc = await b.gate()
    assert abs(fc - 100) <= 3
    # GATE_LEN 0 acts as one cycle, never stuck
    await b.write(GATE_LEN, 0)
    await b.write(FREQ_CTRL, 1)
    await b.tick(20)
    st = await b.read(FREQ_STATUS)
    assert st == 2, f"gate 0 status {st}"
    assert await b.read(MUX_ERRS) == 0


# req: REQ-01, REQ-03, REQ-07, REQ-08, REQ-14, REQ-15, REQ-16, REQ-20, REQ-26, REQ-04, REQ-12
@cocotb.test()
async def test_random_traffic(dut):
    b = await setup(dut)
    rng = random.Random(int(getattr(cocotb, "RANDOM_SEED", 1)))
    await b.write(GATE_LEN, 60)
    sel = 0
    switches = 0
    last = 0
    for _ in range(40):
        op = rng.choice(["sel", "sel", "scratch", "unmapped", "snap", "gate", "same", "idle"])
        if op == "sel":
            sel = rng.randint(0, 1)
            if sel != (await b.read(SEL)):
                switches += 1
            await b.go(sel)
        elif op == "same":
            await b.write(SEL, sel)
            await b.tick(rng.randint(5, 30))
        elif op == "scratch":
            v = rng.choice([0, 1, 0xFFFFFFFF, rng.getrandbits(32)])
            await b.write(SCRATCH, v)
            await b.check(SCRATCH)
        elif op == "unmapped":
            a = rng.choice([0x3C, 0x40, 0x7C, 0x200, 0xFFC])
            await b.write(a, rng.getrandbits(32), model_too=False)
            assert await b.read(a) == 0
        elif op == "snap":
            c = await b.snap()
            assert c >= last or last > 0xF0000000
            last = c
        elif op == "gate":
            _, fc = await b.gate()
            exp = 60 * (3.125 if sel else 1)
            assert abs(fc - exp) <= 6, f"freq {fc} vs {exp}"
        else:
            await b.tick(rng.randint(1, 40))
        assert int(dut.sfp_tx_disable.value) == 1
        await b.check(SEL)
        await b.check(SCRATCH)
        assert await b.read(STATUS) == (sel << 1)
    assert await b.read(SWITCH_COUNT) == switches
    assert await b.read(MUX_ERRS) == 0
    await b.check(ID)
    await b.check(B_DIV)
    await b.check(GATE_LEN)
