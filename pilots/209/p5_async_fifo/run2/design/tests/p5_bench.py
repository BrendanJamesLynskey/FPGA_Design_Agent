import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

M32 = 0xFFFFFFFF


def prbs_words(n, seed=0x7FFFFFFF):
    m = model.Model()
    s = seed
    out = []
    for _ in range(n):
        s, w = m._next(s)
        out.append(w)
    return out


def pick(dut, names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


async def start(dut):
    c25 = pick(dut, ["clk_25", "clk_c3", "clk"])
    c156 = pick(dut, ["clk_gt156", "clk_156", "clk_rd"])
    cocotb.start_soon(Clock(c25, 40, units="ns").start())
    if c156 is not None:
        cocotb.start_soon(Clock(c156, 6.4, units="ns").start())
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    rst = pick(dut, ["rst", "reset"])
    if rst is not None:
        rst.value = 1
        for _ in range(20):
            await RisingEdge(c25)
        rst.value = 0
    for _ in range(5):
        await RisingEdge(c25)
    return c25


class Bus:
    def __init__(self, dut, clk):
        self.d = dut
        self.clk = clk

    async def write(self, addr, val):
        self.d.h_we.value = 1
        self.d.h_addr.value = addr
        self.d.h_wdata.value = val
        await RisingEdge(self.clk)
        self.d.h_we.value = 0
        await RisingEdge(self.clk)

    async def read(self, addr):
        self.d.h_re.value = 1
        self.d.h_addr.value = addr
        await RisingEdge(self.clk)
        self.d.h_re.value = 0
        await RisingEdge(self.clk)
        await RisingEdge(self.clk)
        await Timer(1, units="ns")
        return int(self.d.h_rdata.value)

    async def snap(self):
        await self.write(0x30, 1)
        for _ in range(40):
            await RisingEdge(self.clk)

    async def counters(self):
        await self.snap()
        return [await self.read(0x14 + 4 * i) for i in range(7)]

    async def idle(self, n):
        for _ in range(n):
            await RisingEdge(self.clk)


# req: REQ-10, REQ-23
@cocotb.test()
async def test_soak_no_errors(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    await b.write(0x10, 1)
    await b.idle(5000)
    await b.write(0x10, 0)
    await b.idle(200)
    c = await b.counters()
    assert c[2] == 0, c
    assert c[0] >= 4500, c  # about one word per clk_25 clock


# req: REQ-25, REQ-32, REQ-26, REQ-33, REQ-27, REQ-28
@cocotb.test()
async def test_static_structure(dut):
    root = Path(__file__).resolve().parents[1]
    rtl = ""
    for f in (root / "rtl").glob("*.sv"):
        if "stub" not in f.name:
            rtl += f.read_text()
    assert "GTHE4_CHANNEL" not in rtl and "GTYE4_CHANNEL" not in rtl
    for f in (root / "rtl").glob("*.sv"):
        if "stub" not in f.name:
            assert "GTHE4_COMMON" not in f.read_text()
    xdc = "".join(f.read_text() for f in root.rglob("*.xdc"))
    if xdc:
        assert "clk_25" in xdc or "clk_c3" in xdc
        assert "asynchronous" in xdc or "set_max_delay" in xdc
    jb = root / "data" / "jtag_bus.sv"
    if jb.exists():
        assert b"BSCANE2" in jb.read_bytes()


# req: REQ-01, REQ-02, REQ-03, REQ-04, REQ-29, REQ-30, REQ-05, REQ-31, REQ-24
@cocotb.test()
async def test_register_basics(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    m = model.Model()
    assert await b.read(0) == 0x20950001 == m.read_reg(0)
    assert await b.read(8) == 0
    assert await b.read(4) == 0 == m.read_reg(4)
    await b.write(4, 0x1234)
    assert await b.read(4) == 0
    await b.write(8, 0xA5A5F00D)
    assert await b.read(8) == 0xA5A5F00D
    for a in (0x3C, 0x100, 0x7FC, 0x34, 0x0C):
        await b.write(a, 0xFFFFFFFF)
        assert await b.read(a) == 0
    assert await b.read(8) == 0xA5A5F00D
    assert await b.read(0) == 0x20950001
    # hold until next h_re
    await b.idle(10)
    assert int(dut.h_rdata.value) == 0x20950001
    sfp = pick(dut, ["sfp_tx_disable"])
    if sfp is not None:
        assert int(sfp.value) == 1


# req: REQ-06, REQ-07, REQ-09, REQ-08, REQ-20, REQ-19
@cocotb.test()
async def test_prbs_run(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    await b.write(0x10, 1)
    await b.idle(2000)
    await b.write(0x10, 0)
    await b.idle(200)
    c = await b.counters()
    ww, wr, errs, ovf, unf, stall, occ = c
    assert ww > 1500, c
    assert wr == ww or abs(wr - ww) <= 512
    assert errs == 0 and ovf == 0 and unf == 0
    assert 1 <= occ <= 512
    # snapshot not live
    await b.write(0x10, 1)
    await b.idle(200)
    assert await b.read(0x14) == ww
    await b.write(0x10, 0)


# req: REQ-13, REQ-14, REQ-22, REQ-08
@cocotb.test()
async def test_slow_read_stall(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    await b.write(0x10, 3)
    await b.idle(3000)
    await b.write(0x10, 2)
    await b.idle(100)
    s1 = await b.counters()
    await b.write(0x10, 3)
    await b.idle(1000)
    await b.write(0x10, 2)
    await b.idle(100)
    s2 = await b.counters()
    assert s2[6] == 512, s2
    assert s2[5] > s1[5]
    assert s2[2] == 0 and s2[3] == 0 and s2[4] == 0
    # reader rate: at most 1 per 8 reader clocks (6.4ns) = 51.2 ns/word
    # 3000+ cycles of 40 ns -> reads <= 120000/51.2 + margin
    assert s2[1] <= (4100 * 40) / 51.2 + 5


# req: REQ-15, REQ-16
@cocotb.test()
async def test_inject(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    await b.write(0x10, 1 | 8)
    await b.idle(500)
    await b.write(0x10, 0)
    await b.idle(100)
    c = await b.counters()
    assert c[2] == 1, c
    assert (await b.read(0x10)) & 8 == 0
    await b.write(0x10, 1)
    await b.idle(500)
    await b.write(0x10, 0)
    await b.idle(100)
    c = await b.counters()
    assert c[2] == 1, c


# req: REQ-17, REQ-34, REQ-35, REQ-18, REQ-19, REQ-20
@cocotb.test()
async def test_clear(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    await b.write(0x10, 1)
    await b.idle(300)
    await b.write(0x10, 1 | 4)  # ignored while RUN
    await b.idle(300)
    assert (await b.read(0x10)) & 4 == 0
    await b.write(0x10, 0)
    await b.idle(100)
    c = await b.counters()
    assert c[0] > 500, c
    await b.write(0x10, 4)
    assert (await b.read(0x10)) & 4 == 0
    # snapshot still old until new snapshot
    assert await b.read(0x14) == c[0]
    c = await b.counters()
    assert c == [0] * 7, c
    await b.write(0x10, 1)
    await b.idle(300)
    await b.write(0x10, 0)
    await b.idle(100)
    c = await b.counters()
    assert c[0] > 200 and c[2] == 0, c


# req: REQ-21
@cocotb.test()
async def test_counter_width(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    await b.write(0x10, 1)
    await b.idle(500)
    await b.write(0x10, 0)
    await b.idle(100)
    c = await b.counters()
    assert all(0 <= v <= M32 for v in c)


# req: REQ-06, REQ-07, REQ-09, REQ-13, REQ-14, REQ-15, REQ-17, REQ-19
@cocotb.test()
async def test_random_traffic(dut):
    clk = await start(dut)
    b = Bus(dut, clk)
    rnd = random.Random(1234)
    for _ in range(12):
        await b.write(0x10, 0)
        await b.idle(80)
        await b.write(0x10, 4)
        run = 1
        slow = rnd.randint(0, 1)
        await b.write(0x10, run | (slow << 1))
        await b.idle(rnd.randint(100, 1200))
        if rnd.random() < 0.3:
            await b.write(0x10, run | (slow << 1) | 8)
            await b.idle(300)
            await b.write(0x10, 0)
            await b.idle(100)
            c = await b.counters()
            assert c[2] == 1, c
        else:
            await b.write(0x10, 0)
            await b.idle(100)
            c = await b.counters()
            assert c[2] == 0 and c[3] == 0 and c[4] == 0, c
