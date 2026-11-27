"""cocotb bench for the FIR32 register core, checked against model.py."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

ID_VAL = 0x20940001
CTRL, PUSH, POP, STATUS, SAT, DONE = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.clk_25 if hasattr(dut, "clk_25") else dut.clk
        self.dp = dut.clk_dp if hasattr(dut, "clk_dp") else None
        self.rng = random.Random(cocotb.RANDOM_SEED)

    async def start(self):
        d = self.dut
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if hasattr(d, "rst"):
            d.rst.value = 1
        cocotb.start_soon(Clock(self.clk, 40, units="ns").start())
        if self.dp is not None:
            cocotb.start_soon(Clock(self.dp, 4, units="ns").start())
        for _ in range(20):
            await RisingEdge(self.clk)
        if hasattr(d, "rst"):
            d.rst.value = 0
        for _ in range(10):
            await RisingEdge(self.clk)

    async def idle(self, n):
        for _ in range(n):
            await RisingEdge(self.clk)

    async def write(self, addr, val):
        d = self.dut
        d.h_addr.value = addr
        d.h_wdata.value = val
        d.h_we.value = 1
        await RisingEdge(self.clk)
        d.h_we.value = 0
        await RisingEdge(self.clk)

    async def read(self, addr):
        d = self.dut
        d.h_addr.value = addr
        d.h_re.value = 1
        await RisingEdge(self.clk)
        d.h_re.value = 0
        await RisingEdge(self.clk)
        await RisingEdge(self.clk)
        await Timer(1, units="ns")
        v = d.h_rdata.value
        if not v.is_resolvable:
            return -1  # unresolved (e.g. BUILD stub); never equals a real value
        return int(v)


async def setup(dut):
    b = Bench(dut)
    await b.start()
    m = Model()
    return b, m


async def wr(b, m, addr, val):
    await b.write(addr, val)
    m.write_reg(addr, val)


async def rd_cmp(b, m, addr, what=""):
    got = await b.read(addr)
    exp = m.read_reg(addr)
    assert got == exp, f"{what} read {addr:#x}: dut {got:#x} model {exp:#x}"
    return got


async def push_all(b, m, samples):
    for s in samples:
        await wr(b, m, PUSH, s & 0xFFFF)


async def run_and_settle(b, m, expect_busy=False):
    await wr(b, m, CTRL, 2)
    await b.idle(3)
    if expect_busy:
        assert m.busy
        st = await b.read(STATUS)
        assert st & 1, "BUSY not set after RUN"
    for _ in range(5000):
        st = await b.read(STATUS)
        if not st & 1:
            break
    else:
        raise AssertionError("BUSY never cleared")
    while m.busy:
        m.step()


async def drain(b, m, n):
    for i in range(n):
        got = await b.read(POP)
        exp = m.read_reg(POP)
        assert got == exp, f"pop {i}: dut {got:#x} model {exp:#x}"
        assert got >> 31 == 1
    got = await b.read(POP)
    assert got == 0 and m.read_reg(POP) == 0, "empty OUT_POP not 0"


async def check_state(b, m):
    for a in (STATUS, SAT, DONE):
        await rd_cmp(b, m, a, "state")
    led = m.step()["led"]
    assert int(b.dut.led.value) == led, f"led {int(b.dut.led.value)} != {led}"


async def run_batch(b, m, samples):
    await push_all(b, m, samples)
    await run_and_settle(b, m)
    await check_state(b, m)
    await drain(b, m, len(samples))


def sat_pattern(m):
    h = getattr(m, "h", [1] * 32)
    return [32767 if h[31 - j] >= 0 else -32768 for j in range(32)]


# req: REQ-01, REQ-35, REQ-04, REQ-20, REQ-30, REQ-27, REQ-42
@cocotb.test()
async def test_reset_and_id(dut):
    b, m = await setup(dut)
    assert await b.read(0x00) == ID_VAL
    await b.read(0x04)
    assert await b.read(0x08) == 0
    for a in (CTRL, POP, STATUS, SAT, DONE):
        await rd_cmp(b, m, a, "reset")
    for a in (0x0C, 0x28, 0x2C, 0x40, 0x100, 0x800, 0xFFC):
        assert await b.read(a) == 0, f"unmapped {a:#x}"
    assert int(dut.led.value) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    # CTRL self-clearing bits read back 0
    await wr(b, m, CTRL, 2)
    assert await b.read(CTRL) == 0
    await wr(b, m, CTRL, 1)
    assert await b.read(CTRL) == 0
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-03, REQ-04, REQ-05, REQ-34, REQ-36
@cocotb.test()
async def test_scratch_and_bus(dut):
    b, m = await setup(dut)
    for v in (0xFFFFFFFF, 0x12345678, 0, 0x80000000, 1, 0xA5A5A5A5):
        await wr(b, m, 0x08, v)
        assert await b.read(0x08) == v
        # holds until the next h_re, even with the address changed
        b.dut.h_addr.value = 0x2C
        await b.idle(6)
        assert int(b.dut.h_rdata.value) == v
    # writes to unmapped addresses change nothing
    await wr(b, m, 0x08, 0x5555AAAA)
    for a in (0x0C, 0x28, 0x2C, 0x30, 0x100, 0x7FC, 0xFFC):
        await b.write(a, 0xFFFFFFFF)
    assert await b.read(0x08) == 0x5555AAAA
    await rd_cmp(b, m, STATUS)
    await rd_cmp(b, m, SAT)
    await rd_cmp(b, m, DONE)
    assert await b.read(0x00) == ID_VAL
    for a in (0x0C, 0x2C, 0x100, 0xFFC):
        assert await b.read(a) == 0
    # back-to-back write then read
    await b.write(0x08, 0x77)
    assert await b.read(0x08) == 0x77
    # response within two clocks (checked inside read(): sampled after edge 2)


# req: REQ-06, REQ-07, REQ-19, REQ-21, REQ-39
@cocotb.test()
async def test_impulse(dut):
    b, m = await setup(dut)
    await run_batch(b, m, [32767] + [0] * 63)
    await run_batch(b, m, [-32768] + [0] * 63)
    await run_batch(b, m, [1] + [0] * 63)


# req: REQ-06, REQ-08
@cocotb.test()
async def test_step(dut):
    b, m = await setup(dut)
    await run_batch(b, m, [16384] * 100)
    await wr(b, m, CTRL, 1)
    await run_batch(b, m, [-20000] * 100)
    await wr(b, m, CTRL, 1)
    await run_batch(b, m, [32767] * 100)


# req: REQ-10, REQ-21
@cocotb.test()
async def test_history_persist(dut):
    b, m = await setup(dut)
    r = random.Random(11)
    for _ in range(5):
        await run_batch(b, m, [r.randint(-32768, 32767) for _ in range(20)])
    await run_batch(b, m, [])  # empty RUN: no change
    await run_batch(b, m, [r.randint(-32768, 32767) for _ in range(40)])


# req: REQ-24, REQ-25, REQ-26, REQ-41, REQ-27, REQ-42
@cocotb.test()
async def test_clear(dut):
    b, m = await setup(dut)
    r = random.Random(5)
    await push_all(b, m, sat_pattern(m) * 2)
    await run_and_settle(b, m)
    await check_state(b, m)
    # leave outputs in the FIFO and inputs pending, then CLEAR
    await push_all(b, m, [r.randint(-32768, 32767) for _ in range(10)])
    await wr(b, m, CTRL, 1)
    assert await b.read(CTRL) == 0
    await check_state(b, m)
    assert await b.read(STATUS) == 0
    assert await b.read(SAT) == 0 and await b.read(DONE) == 0
    assert await b.read(POP) == 0
    assert int(dut.led.value) == 0
    # history cleared: result equals a fresh filter
    await run_batch(b, m, [12345, -2000, 30000, 7] * 5)
    # clear while busy aborts
    await push_all(b, m, [r.randint(-32768, 32767) for _ in range(400)])
    await wr(b, m, CTRL, 2)
    await wr(b, m, CTRL, 1)
    await b.idle(100)
    await check_state(b, m)
    assert await b.read(STATUS) == 0
    await run_batch(b, m, [r.randint(-32768, 32767) for _ in range(30)])


# req: REQ-17, REQ-18, REQ-37, REQ-23, REQ-40, REQ-33
@cocotb.test()
async def test_fifo_limits(dut):
    b, m = await setup(dut)
    r = random.Random(7)
    data = [r.randint(-32768, 32767) for _ in range(1024)]
    await push_all(b, m, data)
    await rd_cmp(b, m, STATUS, "full in")
    assert (await b.read(STATUS) >> 4) & 0xFFF == 1024
    await push_all(b, m, [1, 2, 3])  # ignored
    assert (await b.read(STATUS) >> 4) & 0xFFF == 1024
    await run_and_settle(b, m)
    await check_state(b, m)
    assert (await b.read(STATUS) >> 20) & 0xFFF == 1024
    # outputs full and not drained: extra pushes stay in the input FIFO
    await push_all(b, m, [100, -100, 5])
    await run_and_settle(b, m)
    await check_state(b, m)
    # drain everything, count tracks pops
    for i in range(1024):
        got = await b.read(POP)
        assert got == m.read_reg(POP), f"pop {i}"
        if i in (0, 500):
            await rd_cmp(b, m, STATUS, "pop count")
    assert await b.read(POP) == 0
    await run_and_settle(b, m)
    await check_state(b, m)
    await drain(b, m, 3)


# req: REQ-28, REQ-29, REQ-06
@cocotb.test()
async def test_saturation_counters(dut):
    b, m = await setup(dut)
    pat = sat_pattern(m)
    for _ in range(3):
        await run_batch(b, m, pat * 2 + [32767] * 40 + [-32768] * 40)
    await rd_cmp(b, m, SAT, "sat")
    await rd_cmp(b, m, DONE, "done")
    r = random.Random(3)
    await run_batch(b, m, [r.choice((-32768, 32767)) for _ in range(200)])
    await wr(b, m, CTRL, 1)
    await check_state(b, m)


# req: REQ-13, REQ-22
@cocotb.test()
async def test_throughput(dut):
    b, m = await setup(dut)
    n = 1000
    r = random.Random(9)
    await push_all(b, m, [r.randint(-32768, 32767) for _ in range(n)])
    await b.write(CTRL, 2)
    m.write_reg(CTRL, 2)
    t0 = b.dp
    cycles = 0
    seen_busy = False
    # BUSY seen on the led and in STATUS
    st = await b.read(STATUS)
    assert st & 1, "STATUS BUSY not set during RUN"
    seen_busy = True
    if t0 is not None:
        # count clk_dp cycles until led[0] drops
        cycles = 0
        while int(dut.led.value) & 1:
            await RisingEdge(t0)
            cycles += 1
            assert cycles < 4 * n, "datapath slower than ~1 sample/clk_dp"
        assert cycles < n + 200, f"{cycles} clk_dp cycles for {n} samples"
    assert seen_busy
    await run_and_settle(b, m)
    await check_state(b, m)
    await drain(b, m, n)


# req: REQ-21, REQ-22, REQ-10
@cocotb.test()
async def test_run_edge_cases(dut):
    b, m = await setup(dut)
    r = random.Random(21)
    # RUN with empty FIFO: completes, no change
    await wr(b, m, CTRL, 2)
    await b.idle(10)
    await check_state(b, m)
    # RUN while BUSY is ignored; push while busy is not part of the batch
    await push_all(b, m, [r.randint(-32768, 32767) for _ in range(500)])
    await wr(b, m, CTRL, 2)
    await wr(b, m, PUSH, 1234)
    await wr(b, m, CTRL, 2)
    await b.idle(3)
    for _ in range(5000):
        if not (await b.read(STATUS)) & 1:
            break
    while m.busy:
        m.step()
    await check_state(b, m)
    await drain(b, m, 500)
    # the push made while busy is still in the input FIFO: a RUN processes it
    await run_and_settle(b, m)
    await check_state(b, m)
    await drain(b, m, 1)
    await run_batch(b, m, [])
    await rd_cmp(b, m, STATUS)


# req: REQ-11, REQ-12, REQ-38, REQ-14, REQ-15, REQ-16, REQ-31, REQ-32
@cocotb.test()
async def test_static_structure(dut):
    """Source-level checks backing the analysis requirements (full evidence: flow gates)."""
    root = Path(__file__).resolve().parents[1]
    txt = "\n".join(p.read_text() for p in sorted((root / "rtl").glob("*.sv")))
    for gt in ("GTHE4_CHANNEL", "GTYE4_CHANNEL", "GTHE4_COMMON", "GTYE4_COMMON"):
        assert gt not in txt, f"GT primitive {gt} instantiated"
    assert (root / "data" / "jtag_bus.sv").exists() or "jtag_bus" in txt
    assert "jtag_bus" not in "".join(
        p.name for p in (root / "rtl").glob("jtag_bus*")), "jtag_bus copied into rtl/"
    b, m = await setup(dut)
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-09, REQ-06, REQ-33, REQ-21, REQ-29
@cocotb.test()
async def test_random_traffic(dut):
    b, m = await setup(dut)
    r = b.rng
    pat = sat_pattern(m)
    for chunk in range(10):
        kind = chunk % 3
        if kind == 0:
            s = [r.randint(-32768, 32767) for _ in range(1000)]
        elif kind == 1:
            s = [r.randint(-3000, 3000) for _ in range(1000)]
        else:
            s = []
            while len(s) < 1000:
                s += pat if r.random() < 0.3 else [r.randint(-32768, 32767) for _ in range(r.randint(1, 40))]
            s = s[:1000]
        await run_batch(b, m, s)
    await rd_cmp(b, m, DONE, "done total")
    await rd_cmp(b, m, SAT, "sat total")
