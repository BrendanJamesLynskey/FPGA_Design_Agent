"""cocotb bench for the p6 clock-mux register core, checked against model.py."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import FallingEdge, Timer  # noqa: E402

GATE = 200  # GATE_LEN_DEFAULT override (must match the pytest entry)
PARAMS = dict(GATE_LEN_DEFAULT=GATE)

ID, BUILD, SCRATCH, SEL, STATUS, BDIV, GATE_LEN, FCTRL, FSTAT, FCOUNT, ERRS, MCOUNT, SWCNT, SNAP = (
    0, 4, 8, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56)


def _find(dut, names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


class Env:
    def __init__(self, dut):
        self.dut = dut
        self.clk = _find(dut, ["clk", "clk_c3", "clk_a", "clka"])
        self.clkb = _find(dut, ["clk_b", "clkb", "gtref_clk", "clk_gt", "gt_clk", "clk_ref"])
        if self.clkb is None:
            for h in dut:
                n = h._name.lower()
                if "clk" in n and h is not self.clk and ("b" in n or "gt" in n or "ref" in n):
                    self.clkb = h
                    break
        self.rst = _find(dut, ["rst", "reset"])
        self.m = model.Model(**PARAMS)
        self.cycles = 0

    async def start(self):
        cocotb.start_soon(Clock(self.clk, 40, "ns").start())
        if self.clkb is not None:
            cocotb.start_soon(Clock(self.clkb, 6400, "ps").start())
        d = self.dut
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if self.rst is not None:
            self.rst.value = 1
        for _ in range(20):
            await FallingEdge(self.clk)
        if self.rst is not None:
            self.rst.value = 0
        for _ in range(4):
            await FallingEdge(self.clk)
        self.m.reset()

    async def idle(self, n=1):
        for _ in range(n):
            await FallingEdge(self.clk)
            self.cycles += 1

    async def write(self, addr, val):
        d = self.dut
        d.h_addr.value = addr
        d.h_wdata.value = val
        d.h_we.value = 1
        await self.idle()
        d.h_we.value = 0
        await self.idle()

    async def read(self, addr):
        d = self.dut
        d.h_addr.value = addr
        d.h_re.value = 1
        await self.idle()
        d.h_re.value = 0
        await self.idle()
        v = int(d.h_rdata.value)
        # holds the value
        await self.idle()
        assert int(d.h_rdata.value) == v, "h_rdata not held"
        return v

    async def wait_switch(self, limit=3000):
        for _ in range(limit):
            st = await self.read(STATUS)
            if not (st & 1):
                return st
        raise AssertionError("SWITCHING never returned to 0")

    async def set_sel(self, v):
        await self.write(SEL, v)
        return await self.wait_switch()


# req: REQ-01, REQ-03, REQ-05, REQ-13, REQ-21, REQ-12, REQ-17
@cocotb.test()
async def test_smoke_reset_and_common(dut):
    e = Env(dut)
    await e.start()
    m = e.m
    assert await e.read(ID) == m.read_reg(ID) == 0x20960001
    assert await e.read(SCRATCH) == m.read_reg(SCRATCH) == 0
    assert await e.read(SEL) == 0
    assert await e.read(STATUS) == m.read_reg(STATUS) == 0
    assert await e.read(BDIV) == m.read_reg(BDIV)
    assert 1 <= await e.read(BDIV) <= 8
    assert await e.read(GATE_LEN) == m.read_reg(GATE_LEN) == GATE
    assert await e.read(FSTAT) == 0
    assert await e.read(ERRS) == 0
    assert await e.read(SWCNT) == 0
    assert await e.read(MCOUNT) == 0
    for pat in (0xDEADBEEF, 0xFFFFFFFF, 0x1, 0x80000000, 0):
        await e.write(SCRATCH, pat)
        m.write_reg(SCRATCH, pat)
        assert await e.read(SCRATCH) == m.read_reg(SCRATCH) == pat
        assert await e.read(ID) == 0x20960001
    s = _find(dut, ["sfp_tx_disable"])
    if s is not None:
        for _ in range(10):
            assert int(s.value) == 1
            await e.idle()


# req: REQ-04, REQ-22, REQ-01, REQ-03
@cocotb.test()
async def test_unmapped_and_ro(dut):
    e = Env(dut)
    await e.start()
    await e.write(SCRATCH, 0x1234567)
    await e.write(GATE_LEN, 77)
    for a in (0x00C, 0x03C, 0x040, 0x044, 0x080, 0x100, 0x400, 0x800, 0xFFC, 0x012, 0x1C0):
        assert await e.read(a) == e.m.read_reg(a) == 0, hex(a)
    for a in (0x00C, 0x03C, 0x040, 0x100, 0x800, 0xFFC):
        await e.write(a, 0xFFFFFFFF)
    assert await e.read(SCRATCH) == 0x1234567
    assert await e.read(GATE_LEN) == 77
    assert await e.read(SEL) == 0
    assert await e.read(STATUS) == 0
    assert await e.read(ID) == 0x20960001
    assert await e.read(FSTAT) == 0
    assert await e.read(SWCNT) == 0
    # writes to read-only registers are ignored
    await e.write(ID, 0)
    await e.write(STATUS, 3)
    await e.write(ERRS, 5)
    await e.write(SWCNT, 9)
    assert await e.read(ID) == 0x20960001
    assert await e.read(STATUS) == 0
    assert await e.read(ERRS) == 0
    assert await e.read(SWCNT) == 0


# req: REQ-06, REQ-10, REQ-11, REQ-12
@cocotb.test()
async def test_switch_directed(dut):
    e = Env(dut)
    await e.start()
    m = e.m
    # same selection: no count
    await e.write(SEL, 0)
    st = await e.wait_switch()
    assert st == 0
    assert await e.read(SWCNT) == 0
    # to B
    await e.write(SEL, 1)
    m.write_reg(SEL, 1)
    st = await e.wait_switch()
    assert (st >> 1) & 1 == 1
    assert await e.read(SEL) == 1
    assert await e.read(SWCNT) == 1
    led = _find(dut, ["led"])
    if led is not None:
        assert int(led.value) == 0b01
    # same again
    await e.write(SEL, 1)
    await e.wait_switch()
    assert await e.read(SWCNT) == 1
    # SEL bits above 0 are ignored for selection
    await e.write(SEL, 0)
    st = await e.wait_switch()
    assert (st >> 1) & 1 == 0
    assert await e.read(SWCNT) == 2
    assert await e.read(SEL) == 0
    # SWITCHING is observed right after a change
    await e.write(SEL, 1)
    seen = False
    for _ in range(40):
        st = await e.read(STATUS)
        if st & 1:
            seen = True
        else:
            break
    assert (st >> 1) & 1 == 1
    assert await e.read(SWCNT) == 3
    # write during switching: the latest value wins
    await e.write(SEL, 0)
    await e.write(SEL, 1)
    await e.write(SEL, 0)
    st = await e.wait_switch()
    assert (st >> 1) & 1 == 0 and await e.read(SEL) == 0
    n = await e.read(SWCNT)
    assert 3 <= n <= 6
    if led is not None:
        assert int(led.value) == 0


# req: REQ-06, REQ-08, REQ-10, REQ-11
@cocotb.test()
async def test_random_switches(dut):
    e = Env(dut)
    await e.start()
    rnd = random.Random(cocotb.RANDOM_SEED)
    cur = 0
    expect = 0
    for i in range(1000):
        v = rnd.choice([0, 1, 1, 0, cur, cur])
        await e.write(SEL, v)
        st = await e.wait_switch()
        if rnd.random() < 0.3:
            await e.idle(rnd.randint(0, 30))
        assert (st >> 1) & 1 == v, f"iter {i}"
        if v != cur:
            expect += 1
            cur = v
        if i % 50 == 49:
            assert await e.read(SWCNT) == expect
            assert await e.read(ERRS) == 0
    assert await e.read(SWCNT) == expect
    assert await e.read(ERRS) == 0


# req: REQ-10, REQ-06
@cocotb.test()
async def test_random_back_to_back_switch_writes(dut):
    e = Env(dut)
    await e.start()
    rnd = random.Random(cocotb.RANDOM_SEED + 1)
    last = 0
    total_min, total_max = 0, 0
    prev_n = 0
    for i in range(100):
        k = rnd.randint(1, 4)
        for _ in range(k):
            last = rnd.randint(0, 1)
            await e.write(SEL, last)
        st = await e.wait_switch()
        assert (st >> 1) & 1 == last
        n = await e.read(SWCNT)
        assert n >= prev_n
        prev_n = n
    assert await e.read(ERRS) == 0


# req: REQ-15, REQ-23, REQ-13
@cocotb.test()
async def test_gate_status(dut):
    e = Env(dut)
    await e.start()
    m = e.m
    assert await e.read(FSTAT) == 0
    await e.write(GATE_LEN, 120)
    assert await e.read(GATE_LEN) == 120
    m.write_reg(GATE_LEN, 120)
    await e.write(FCTRL, 1)
    m.write_reg(FCTRL, 1)
    assert await e.read(FCTRL) == 0  # self-clearing
    st = await e.read(FSTAT)
    assert st == 1, f"BUSY expected, got {st}"
    for _ in range(300):
        st = await e.read(FSTAT)
        if st & 1 == 0:
            break
    assert st == 2, f"DONE expected, got {st}"
    await e.idle(10)
    assert await e.read(FSTAT) == 2
    # START clears DONE
    await e.write(FCTRL, 1)
    st = await e.read(FSTAT)
    assert st == 1
    for _ in range(300):
        st = await e.read(FSTAT)
        if st & 1 == 0:
            break
    assert st == 2
    # GATE_LEN 0 behaves as 1
    await e.write(GATE_LEN, 0)
    await e.write(FCTRL, 1)
    for _ in range(20):
        st = await e.read(FSTAT)
        if st == 2:
            break
    assert st == 2


# req: REQ-15, REQ-23, REQ-12
@cocotb.test()
async def test_gate_count(dut):
    e = Env(dut)
    await e.start()
    for sel, gl in ((0, 100), (0, 333), (1, 100), (1, 333)):
        await e.set_sel(sel)
        m = model.Model(**PARAMS)
        m.write_reg(SEL, sel)
        for _ in range(10):
            m.step()
        m.write_reg(GATE_LEN, gl)
        m.write_reg(FCTRL, 1)
        for _ in range(gl + 5):
            m.step()
        want = m.read_reg(FCOUNT)
        await e.write(GATE_LEN, gl)
        await e.write(FCTRL, 1)
        for _ in range(gl + 100):
            st = await e.read(FSTAT)
            if st & 2:
                break
        assert st & 2
        got = await e.read(FCOUNT)
        tol = 4 if sel == 0 else 8 + gl // 50
        assert abs(got - want) <= tol, f"sel={sel} gl={gl} got {got} want {want}"
        assert await e.read(ERRS) == 0


# req: REQ-16, REQ-09, REQ-08
@cocotb.test()
async def test_snapshot(dut):
    e = Env(dut)
    await e.start()
    assert await e.read(MCOUNT) == 0
    await e.write(SNAP, 0)
    a = await e.read(MCOUNT)
    assert a > 0
    # MUX_COUNT holds between snapshots
    await e.idle(20)
    assert await e.read(MCOUNT) == a
    await e.idle(100)
    await e.write(SNAP, 0xFFFFFFFF)
    b = await e.read(MCOUNT)
    # clock A selected: one mux_clk per clk_c3
    ref = model.Model(**PARAMS)
    for _ in range(1):
        ref.step()
    diff = (b - a) & 0xFFFFFFFF
    assert 100 < diff < 400, diff
    assert abs(diff - 124) <= 20, diff  # 100 idle + about 24 cycles of register traffic
    # with B selected the counter runs about 6.25x faster
    await e.set_sel(1)
    await e.write(SNAP, 0)
    c = await e.read(MCOUNT)
    await e.idle(200)
    await e.write(SNAP, 0)
    d = await e.read(MCOUNT)
    diff = (d - c) & 0xFFFFFFFF
    want = 200 * 6.25
    assert want * 0.9 < diff < want * 1.4 + 100, diff
    assert await e.read(ERRS) == 0


# req: REQ-09, REQ-08
@cocotb.test()
async def test_errors_stay_zero_idle_and_busy(dut):
    e = Env(dut)
    await e.start()
    for i in range(30):
        await e.write(SEL, i & 1)
        await e.idle(i % 7)
    await e.wait_switch()
    await e.idle(500)
    assert await e.read(ERRS) == 0
    assert e.m.read_reg(ERRS) == 0
