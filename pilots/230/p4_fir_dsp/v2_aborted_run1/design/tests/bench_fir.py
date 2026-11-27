"""cocotb bench for the FIR register core, checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

CTRL, IN_PUSH, OUT_POP, STATUS, SAT, DONE = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
DEPTH = 1024


def pick(dut, names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.clk = pick(dut, ["clk", "clk25"])
        self.clk_dp = pick(dut, ["clk_dp"])
        self.locked = pick(dut, ["mmcm_locked", "locked", "dp_locked", "clk_dp_locked"])
        self.rst = pick(dut, ["rst"])
        self.dp_edges = 0

    async def dp_counter(self):
        sig = self.clk_dp if self.clk_dp is not None else self.clk
        mult = 1 if self.clk_dp is not None else 10
        while True:
            await RisingEdge(sig)
            self.dp_edges += mult

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(self.clk, 40, "ns").start())
        if self.clk_dp is not None:
            cocotb.start_soon(Clock(self.clk_dp, 4, "ns").start())
        cocotb.start_soon(self.dp_counter())
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if self.locked is not None:
            self.locked.value = 0
        if self.rst is not None:
            self.rst.value = 1
        for _ in range(6):
            await RisingEdge(self.clk)
        if self.locked is not None:
            self.locked.value = 1
        if self.rst is not None:
            self.rst.value = 0
        for _ in range(30):
            await RisingEdge(self.clk)
        cocotb.start_soon(self.sfp_monitor())

    async def sfp_monitor(self):
        sfp = pick(self.dut, ["sfp_tx_disable"])
        if sfp is None:
            return
        while True:
            await RisingEdge(self.clk)
            assert int(sfp.value) == 1, "sfp_tx_disable dropped"

    async def idle(self, n=1):
        for _ in range(n):
            await RisingEdge(self.clk)

    async def write(self, addr, val):
        self.dut.h_addr.value = addr
        self.dut.h_wdata.value = val & 0xFFFFFFFF
        self.dut.h_we.value = 1
        await RisingEdge(self.clk)
        self.dut.h_we.value = 0
        self.dut.h_re.value = 0

    async def read(self, addr, gap=True):
        self.dut.h_addr.value = addr
        self.dut.h_re.value = 1
        await RisingEdge(self.clk)
        self.dut.h_re.value = 0
        # sampled by the DUT at this edge; value must show within 2 further clocks
        await RisingEdge(self.clk)
        await RisingEdge(self.clk)
        await RisingEdge(self.clk)
        return int(self.dut.h_rdata.value)

    async def push(self, vals):
        for v in vals:
            await self.write(IN_PUSH, v)

    async def wait_idle(self, limit=200000):
        for _ in range(limit):
            s = await self.read(STATUS)
            if not (s & 1):
                await self.idle(25)  # CDC lag of counts
                return
        raise AssertionError("BUSY never cleared")

    async def run_and_wait(self, m):
        await self.write(CTRL, 2)
        m.write_reg(CTRL, 2)
        model_run(m)
        await self.wait_idle()

    async def check_status(self, m, msg=""):
        s = await self.read(STATUS)
        e = m.read_reg(STATUS)
        assert s == e, f"STATUS {s:#x} != model {e:#x} {msg}"

    async def pop_compare(self, m, n):
        for i in range(n):
            g = await self.read(OUT_POP)
            e = m.read_reg(OUT_POP)
            assert g == e, f"OUT_POP[{i}] {g:#x} != model {e:#x}"

    async def check_counts(self, m):
        for a in (SAT, DONE):
            g = await self.read(a)
            e = m.read_reg(a)
            assert g == e, f"reg {a:#x}: {g} != model {e}"


def model_run(m):
    while m.busy and m.infifo and len(m.outfifo) < DEPTH:
        m.step()
    if m.busy and not m.infifo:
        m.step()


async def setup(dut):
    b = Bench(dut)
    await b.start()
    m = Model()
    m.reset()
    # start from a clean datapath state
    await b.write(CTRL, 1)
    await b.idle(30)
    return b, m


# req: REQ-01, REQ-28, REQ-25, REQ-03
@cocotb.test()
async def test_reset_values(dut):
    b = Bench(dut)
    await b.start()
    m = Model()
    assert await b.read(0x000) == m.read_reg(0) == 0x20940001
    assert await b.read(0x008) == 0
    assert await b.read(STATUS) == 0
    assert await b.read(SAT) == 0
    assert await b.read(DONE) == 0
    assert await b.read(OUT_POP) == 0
    led = pick(dut, ["led"])
    if led is not None:
        assert (int(led.value) & 1) == 0


# req: REQ-03, REQ-01
@cocotb.test()
async def test_scratch(dut):
    b, m = await setup(dut)
    for v in (0xDEADBEEF, 0, 0xFFFFFFFF, 0x12345678, 1):
        await b.write(0x008, v)
        m.write_reg(8, v)
        assert await b.read(0x008) == m.read_reg(8) == v
        assert await b.read(0x000) == 0x20940001
    # back-to-back: read in the clock right after the write
    await b.write(0x008, 0xA5A5A5A5)
    dut.h_addr.value = 0x008
    dut.h_re.value = 1
    await RisingEdge(b.clk)
    dut.h_re.value = 0
    for _ in range(3):
        await RisingEdge(b.clk)
    assert int(dut.h_rdata.value) == 0xA5A5A5A5


# req: REQ-04, REQ-29
@cocotb.test()
async def test_unmapped(dut):
    b, m = await setup(dut)
    await b.write(0x008, 0x55AA55AA)
    for a in (0x00C, 0x02C, 0x030, 0x040, 0x100, 0x400, 0x7FC, 0xFFC, 0x018 + 0x200):
        assert await b.read(a) == 0, hex(a)
        await b.write(a, 0xFFFFFFFF)
    assert await b.read(0x008) == 0x55AA55AA
    assert await b.read(0x000) == 0x20940001
    await b.check_status(m)
    assert await b.read(OUT_POP) == 0
    await b.check_counts(m)


# req: REQ-05, REQ-30
@cocotb.test()
async def test_read_timing_hold(dut):
    b, m = await setup(dut)
    await b.write(0x008, 0xCAFEF00D)
    dut.h_addr.value = 0x008
    dut.h_re.value = 1
    await RisingEdge(b.clk)
    dut.h_re.value = 0
    await RisingEdge(b.clk)
    await RisingEdge(b.clk)
    await RisingEdge(b.clk)
    assert int(dut.h_rdata.value) == 0xCAFEF00D
    for _ in range(25):
        await RisingEdge(b.clk)
        assert int(dut.h_rdata.value) == 0xCAFEF00D
    # changing address without h_re must not change the held value
    dut.h_addr.value = 0x000
    for _ in range(5):
        await RisingEdge(b.clk)
        assert int(dut.h_rdata.value) == 0xCAFEF00D
    # new read replaces it
    assert await b.read(0x000) == 0x20940001
    await b.idle(10)
    assert int(dut.h_rdata.value) == 0x20940001


# req: REQ-06, REQ-10, REQ-24, REQ-20
@cocotb.test()
async def test_impulse(dut):
    b, m = await setup(dut)
    xs = [0x7FFF] + [0] * 39
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.check_status(m)
    await b.run_and_wait(m)
    await b.check_status(m)
    await b.pop_compare(m, 40)
    await b.check_counts(m)
    # impulse not at first position, preceded by zeros (history is all 0)
    await b.write(CTRL, 1)
    m.write_reg(CTRL, 1)
    xs = [0, 0, 0, 0x4000, -1 & 0xFFFF] + [0] * 40
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.run_and_wait(m)
    await b.pop_compare(m, len(xs))


# req: REQ-07, REQ-21
@cocotb.test()
async def test_step(dut):
    b, m = await setup(dut)
    for amp in (0x4000, 0x7FFF, 0x8000):
        await b.write(CTRL, 1)
        m.write_reg(CTRL, 1)
        await b.idle(10)
        xs = [amp] * 70
        await b.push(xs)
        for x in xs:
            m.write_reg(IN_PUSH, x)
        await b.idle(25)
        await b.run_and_wait(m)
        await b.pop_compare(m, 70)
        await b.check_counts(m)


# req: REQ-08, REQ-09, REQ-21, REQ-22, REQ-24
@cocotb.test()
async def test_random_chunks(dut):
    rnd = random.Random(cocotb.RANDOM_SEED)
    b, m = await setup(dut)
    for chunk in range(10):
        mode = chunk % 3
        xs = []
        for _ in range(1000):
            if mode == 0:
                xs.append(rnd.randrange(65536))
            elif mode == 1:
                xs.append(rnd.choice([0x7FFF, 0x8000, 0x7000, 0x9000, 0, rnd.randrange(65536)]))
            else:
                xs.append(((rnd.randrange(-32768, 32768)) >> rnd.randrange(0, 12)) & 0xFFFF)
        await b.push(xs)
        for x in xs:
            m.write_reg(IN_PUSH, x)
        await b.idle(25)
        await b.run_and_wait(m)
        await b.check_status(m, f"chunk {chunk}")
        await b.pop_compare(m, 1000)
        await b.check_counts(m)


# req: REQ-09, REQ-23
@cocotb.test()
async def test_history_persists_then_clear(dut):
    b, m = await setup(dut)
    for rnd_i in range(3):
        xs = [0x6000 + 37 * i for i in range(20)]
        await b.push(xs)
        for x in xs:
            m.write_reg(IN_PUSH, x)
        await b.idle(25)
        await b.run_and_wait(m)
        await b.pop_compare(m, 20)
    await b.check_counts(m)
    # leave outputs and inputs pending, then CLEAR
    xs = [0x7000] * 10
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.run_and_wait(m)
    await b.push([1, 2, 3])
    for x in (1, 2, 3):
        m.write_reg(IN_PUSH, x)
    await b.write(CTRL, 1)
    m.write_reg(CTRL, 1)
    await b.idle(40)
    assert await b.read(CTRL) == 0
    await b.check_status(m)
    assert await b.read(STATUS) == 0
    assert await b.read(OUT_POP) == 0
    assert await b.read(SAT) == 0
    assert await b.read(DONE) == 0
    # history zeroed: same as fresh
    xs = [0x7FFF] + [0] * 33
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.run_and_wait(m)
    await b.pop_compare(m, len(xs))
    # CLEAR and RUN in the same write: CLEAR wins
    await b.push([5, 6])
    for x in (5, 6):
        m.write_reg(IN_PUSH, x)
    await b.write(CTRL, 3)
    m.write_reg(CTRL, 3)
    await b.idle(60)
    await b.check_status(m)
    assert await b.read(STATUS) == 0


# req: REQ-32, REQ-24
@cocotb.test()
async def test_ctrl_self_clear_and_empty_run(dut):
    b, m = await setup(dut)
    # RUN with an empty FIFO finishes with no output
    await b.write(CTRL, 2)
    m.write_reg(CTRL, 2)
    assert await b.read(CTRL) == 0
    await b.idle(40)
    await b.check_status(m)
    assert await b.read(STATUS) & 1 == 0
    assert await b.read(OUT_POP) == 0
    xs = [1000, 2000, 3000]
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.write(CTRL, 2)
    m.write_reg(CTRL, 2)
    assert await b.read(CTRL) == 0
    model_run(m)
    await b.wait_idle()
    assert await b.read(CTRL) == 0
    await b.pop_compare(m, 3)


# req: REQ-19, REQ-20, REQ-12
@cocotb.test()
async def test_status_busy_and_throughput(dut):
    b, m = await setup(dut)
    n = 1000
    xs = [(i * 211) & 0xFFFF for i in range(n)]
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    st = await b.read(STATUS)
    assert (st >> 4) & 0xFFF == n and (st >> 20) == 0 and st & 1 == 0
    await b.write(CTRL, 2)
    m.write_reg(CTRL, 2)
    start = b.dp_edges
    await b.idle(8)
    st = await b.read(STATUS)
    assert st & 1 == 1, "BUSY must be 1 after RUN"
    led = pick(dut, ["led"])
    if led is not None:
        assert int(led.value) & 1 == 1
    # follow BUSY through led[0] when available, else poll status
    if led is not None:
        for _ in range(100000):
            await RisingEdge(b.clk)
            if int(led.value) & 1 == 0:
                break
        else:
            raise AssertionError("BUSY stuck")
        elapsed = b.dp_edges - start
        # one sample per clk_dp cycle: n cycles plus pipeline and CDC slack
        assert elapsed <= n + 300, f"{elapsed} dp cycles for {n} samples"
    model_run(m)
    await b.wait_idle()
    await b.check_status(m)
    await b.pop_compare(m, n)


# req: REQ-15, REQ-31, REQ-20
@cocotb.test()
async def test_input_fifo_full(dut):
    b, m = await setup(dut)
    xs = [(i * 7 + 3) & 0xFFFF for i in range(DEPTH)]
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.check_status(m)
    st = await b.read(STATUS)
    assert (st >> 4) & 0xFFF == DEPTH
    # pushes on a full FIFO are ignored
    extra = [0x1234, 0x5678, 0xFFFF]
    await b.push(extra)
    for x in extra:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    st = await b.read(STATUS)
    assert (st >> 4) & 0xFFF == DEPTH
    await b.run_and_wait(m)
    await b.check_status(m)
    assert (await b.read(STATUS) >> 20) == DEPTH
    await b.pop_compare(m, DEPTH)
    await b.check_counts(m)


# req: REQ-16, REQ-17, REQ-20, REQ-18
@cocotb.test()
async def test_output_fifo_full_stall(dut):
    b, m = await setup(dut)
    xs = [(i * 13 + 5) & 0xFFFF for i in range(DEPTH)]
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.run_and_wait(m)
    st = await b.read(STATUS)
    assert (st >> 20) == DEPTH and (st >> 4) & 0xFFF == 0
    # more input: processing stalls until there is room, nothing lost
    ys = [0x7FFF, 0x8000, 0x1111, 0x2222, 0x3333]
    await b.push(ys)
    for x in ys:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.write(CTRL, 2)
    m.write_reg(CTRL, 2)
    await b.idle(300)
    st = await b.read(STATUS)
    assert st & 1 == 1, "must stay BUSY while output FIFO is full"
    assert (st >> 20) == DEPTH and (st >> 4) & 0xFFF == len(ys)
    await b.pop_compare(m, 3)
    model_run(m)
    await b.idle(200)
    await b.pop_compare(m, 2)
    model_run(m)
    await b.wait_idle()
    await b.check_status(m)
    # drain everything
    n = len(m.outfifo)
    assert n == DEPTH
    await b.pop_compare(m, n)
    # empty now: pops return 0
    for _ in range(3):
        assert await b.read(OUT_POP) == 0
    await b.check_status(m)
    await b.check_counts(m)


# req: REQ-18, REQ-17
@cocotb.test()
async def test_pop_empty(dut):
    b, m = await setup(dut)
    for _ in range(4):
        assert await b.read(OUT_POP) == 0
    await b.push([0x0100])
    m.write_reg(IN_PUSH, 0x0100)
    await b.run_and_wait(m)
    g = await b.read(OUT_POP)
    e = m.read_reg(OUT_POP)
    assert g == e and (g >> 31) == 1
    assert await b.read(OUT_POP) == 0
    await b.check_status(m)


# req: REQ-21, REQ-22
@cocotb.test()
async def test_saturation_count(dut):
    b, m = await setup(dut)
    xs = [0x7FFF] * 40 + [0x8000] * 40 + [0x7FFF, 0x8000] * 20
    await b.push(xs)
    for x in xs:
        m.write_reg(IN_PUSH, x)
    await b.idle(25)
    await b.run_and_wait(m)
    await b.check_counts(m)
    await b.pop_compare(m, len(xs))
    await b.check_counts(m)
    assert m.read_reg(DONE) == len(xs)
