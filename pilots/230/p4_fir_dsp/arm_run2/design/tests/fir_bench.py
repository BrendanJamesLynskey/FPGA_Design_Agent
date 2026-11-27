"""cocotb bench for the fir32 register core, checked against model.py (transaction level)."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

A_ID, A_BUILD, A_SCR, A_CTRL, A_PUSH, A_POP, A_STAT, A_SAT, A_DONE = 0, 4, 8, 16, 20, 24, 28, 32, 36
CLK_NS = 40
DP_NS = 4


class Env:
    pass


def _h(dut, *names):
    for n in names:
        try:
            return getattr(dut, n)
        except AttributeError:
            continue
    return None


async def setup(dut, do_reset=True):
    e = Env()
    e.dut = dut
    e.clk = _h(dut, "clk25", "clk")
    e.dp = _h(dut, "clk_dp")
    e.rst = _h(dut, "rst")
    e.sfp = _h(dut, "sfp_tx_disable")
    e.led = _h(dut, "led")
    cocotb.start_soon(Clock(e.clk, CLK_NS, units="ns").start())
    if e.dp is not None:
        cocotb.start_soon(Clock(e.dp, DP_NS, units="ns").start())
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    if e.rst is not None:
        e.rst.value = 1
        await ClockCycles(e.clk, 8)
        e.rst.value = 0
        await ClockCycles(e.clk, 20)
    else:
        await ClockCycles(e.clk, 5)
    e.m = Model()
    e.m.reset()
    e.has_rst = e.rst is not None
    e.cycles = 0
    return e


async def wr(e, addr, val):
    e.dut.h_addr.value = addr
    e.dut.h_wdata.value = val
    e.dut.h_we.value = 1
    await RisingEdge(e.clk)
    e.dut.h_we.value = 0
    await RisingEdge(e.clk)
    e.cycles += 2


async def rd(e, addr):
    e.dut.h_addr.value = addr
    e.dut.h_re.value = 1
    await RisingEdge(e.clk)
    e.dut.h_re.value = 0
    await RisingEdge(e.clk)
    await RisingEdge(e.clk)
    await Timer(1, units="ns")
    e.cycles += 3
    if e.sfp is not None:
        assert int(e.sfp.value) == 1, "sfp_tx_disable must be 1"
    return int(e.dut.h_rdata.value)


async def mwr(e, addr, val):
    """write to RTL and model."""
    await wr(e, addr, val)
    e.m.write_reg(addr, val)


async def cmp_rd(e, addr, what=""):
    got = await rd(e, addr)
    exp = e.m.read_reg(addr)
    assert got == exp, f"{what} reg 0x{addr:03x}: rtl 0x{got:08x} model 0x{exp:08x}"
    return got


async def wait_idle(e, first_wait=40):
    await ClockCycles(e.clk, first_wait)
    seen = 0
    for _ in range(3000):
        s = await rd(e, A_STAT)
        if not (s & 1):
            return seen
        seen += 1
    raise AssertionError("BUSY never cleared")


def model_run(e):
    e.m.write_reg(A_CTRL, 2)
    n = 0
    while e.m.read_reg(A_STAT) & 1:
        e.m.step()
        n += 1
        assert n < 200000


async def run(e):
    await wr(e, A_CTRL, 2)
    model_run(e)
    await wait_idle(e)


async def push(e, samples, rng=None):
    rng = rng or random.Random(1)
    for x in samples:
        v = (x & 0xFFFF) | (rng.getrandbits(16) << 16)
        await wr(e, A_PUSH, v)
        e.m.write_reg(A_PUSH, v)


async def pop_all(e, n=None):
    if n is None:
        n = len(e.m.outfifo)
    out = []
    for _ in range(n):
        out.append(await cmp_rd(e, A_POP, "pop"))
    return out


async def check_idle_regs(e):
    for a in (A_STAT, A_SAT, A_DONE, A_CTRL, A_SCR):
        await cmp_rd(e, a)


async def clear(e):
    await wr(e, A_CTRL, 1)
    e.m.write_reg(A_CTRL, 1)
    await ClockCycles(e.clk, 30)


def sat_stream(e):
    h = getattr(e.m, "h", None)
    if h is None:
        return [32767, -32768] * 16
    pos = [32767 if c >= 0 else -32768 for c in reversed(h)]
    neg = [-32768 if c >= 0 else 32767 for c in reversed(h)]
    return pos + neg + pos


# req: REQ-01, REQ-03, REQ-20, REQ-28, REQ-05, REQ-22, REQ-23, REQ-21
@cocotb.test()
async def test_reset_values(dut):
    e = await setup(dut)
    assert await rd(e, A_ID) == 0x20940001
    await rd(e, A_BUILD)
    assert await rd(e, A_SCR) == 0
    assert await rd(e, A_STAT) == 0
    assert await rd(e, A_SAT) == 0
    assert await rd(e, A_DONE) == 0
    assert await rd(e, A_POP) == 0
    assert await rd(e, A_CTRL) == 0
    if e.led is not None:
        assert (int(e.led.value) & 1) == 0
    if e.sfp is not None:
        assert int(e.sfp.value) == 1


# req: REQ-35, REQ-04, REQ-36, REQ-05, REQ-37, REQ-03
@cocotb.test()
async def test_scratch_unmapped_hold(dut):
    e = await setup(dut)
    for v in (0, 0xFFFFFFFF, 0x12345678, 0x80000001, 0xA5A5A5A5):
        await mwr(e, A_SCR, v)
        assert await rd(e, A_SCR) == v
    await mwr(e, A_SCR, 0xCAFEF00D)
    # hold: value stays until next h_re, even when the address changes
    got = await rd(e, A_ID)
    assert got == 0x20940001
    e.dut.h_addr.value = A_SCR
    await ClockCycles(e.clk, 6)
    assert int(e.dut.h_rdata.value) == 0x20940001
    for a in (0x00C, 0x028, 0x02C, 0x040, 0x0FC, 0x100, 0x400, 0x800, 0xFFC, 0x00D + 0x10 * 3):
        assert await rd(e, a) == 0, f"unmapped 0x{a:x}"
        await wr(e, a, 0xFFFFFFFF)
    for a in (0x00C, 0x028, 0x02C, 0x100, 0x800, 0xFFC):
        await wr(e, a, 0xDEADBEEF)
    assert await rd(e, A_SCR) == 0xCAFEF00D
    assert await rd(e, A_ID) == 0x20940001
    await check_idle_regs(e)
    for a in (0x00C, 0x028, 0x100, 0xFFC):
        assert await rd(e, a) == 0


# req: REQ-34, REQ-27, REQ-26, REQ-32, REQ-33, REQ-39, REQ-25, REQ-24, REQ-17
@cocotb.test()
async def test_ctrl_clear(dut):
    e = await setup(dut)
    for v in (1, 2, 3, 0):
        await wr(e, A_CTRL, v)
        e.m.write_reg(A_CTRL, v)
        await wait_idle(e, 10)
        assert await rd(e, A_CTRL) == 0
    await clear(e)
    # CLEAR+RUN: clear wins, nothing is run
    await push(e, [1000, 2000, 3000])
    await wr(e, A_CTRL, 3)
    e.m.write_reg(A_CTRL, 3)
    await wait_idle(e, 40)
    await check_idle_regs(e)
    st = await rd(e, A_STAT)
    assert st == 0, f"status after CLEAR+RUN {st:x}"
    # saturating run builds history, SAT_COUNT, SAMPLES_DONE and fills output
    await push(e, sat_stream(e) + [5, -7, 9])
    await run(e)
    assert e.m.read_reg(A_SAT) > 0, "stimulus must saturate"
    await check_idle_regs(e)
    # leave unprocessed inputs and unread outputs, then clear
    await push(e, [11, 12, 13])
    await clear(e)
    assert await rd(e, A_STAT) == 0
    assert await rd(e, A_SAT) == 0
    assert await rd(e, A_DONE) == 0
    assert await rd(e, A_POP) == 0
    # history zeroed: impulse response is the plain coefficients again
    await push(e, [20000] + [0] * 40)
    await run(e)
    await cmp_rd(e, A_DONE)
    await pop_all(e)
    # history persists across runs (REQ-17)
    rng = random.Random(7)
    await clear(e)
    for _ in range(3):
        await push(e, [rng.randint(-32768, 32767) for _ in range(50)], rng)
        await run(e)
        await check_idle_regs(e)
    await pop_all(e)


# req: REQ-09, REQ-08, REQ-06, REQ-07
@cocotb.test()
async def test_impulse_and_startup(dut):
    e = await setup(dut)
    await clear(e)
    await push(e, [32767] + [0] * 40)
    await run(e)
    out = await pop_all(e)
    h = getattr(e.m, "h", None)
    if h is not None:
        for k in range(32):
            exp = ((h[k] * 32767 + 16384) >> 15) & 0xFFFF
            assert out[k] == (0x80000000 | exp), f"impulse tap {k}"
        assert all(v == 0x80000000 | (((0 + 16384) >> 15) & 0xFFFF) for v in out[32:])
    # step input: first outputs depend only on samples seen so far
    await clear(e)
    await push(e, [12000] * 45)
    await run(e)
    await pop_all(e)
    # small and odd values: rounding only at the end
    await clear(e)
    rng = random.Random(3)
    await push(e, [rng.randint(-3, 3) for _ in range(100)], rng)
    await run(e)
    await pop_all(e)
    await check_idle_regs(e)


# req: REQ-13, REQ-14, REQ-15, REQ-19, REQ-38, REQ-22, REQ-23, REQ-16
@cocotb.test()
async def test_fifo_full(dut):
    e = await setup(dut)
    await clear(e)
    rng = random.Random(11)
    data = [rng.randint(-32768, 32767) for _ in range(1030)]
    await push(e, data, rng)
    st = await rd(e, A_STAT)
    assert (st >> 4) & 0xFFF == 1024, f"input count {(st >> 4) & 0xFFF}"
    assert st == e.m.read_reg(A_STAT)
    await run(e)
    st = await rd(e, A_STAT)
    assert (st >> 20) & 0xFFF == 1024 and (st >> 4) & 0xFFF == 0 and not st & 1
    assert st == e.m.read_reg(A_STAT)
    await check_idle_regs(e)
    # pop decrements the count, oldest first
    first = await cmp_rd(e, A_POP, "pop0")
    assert first & 0x80000000
    st = await rd(e, A_STAT)
    assert (st >> 20) & 0xFFF == 1023
    await pop_all(e)
    assert await rd(e, A_POP) == 0
    assert (await rd(e, A_STAT)) == 0


# req: REQ-24, REQ-25, REQ-06, REQ-07
@cocotb.test()
async def test_saturation_counts(dut):
    e = await setup(dut)
    await clear(e)
    await push(e, sat_stream(e))
    await run(e)
    assert e.m.read_reg(A_SAT) > 0
    await check_idle_regs(e)
    await pop_all(e)
    rng = random.Random(5)
    await push(e, [rng.choice([32767, -32768, 0, 1, -1]) for _ in range(300)], rng)
    await run(e)
    await check_idle_regs(e)
    await pop_all(e)


# req: REQ-21, REQ-11, REQ-16
@cocotb.test()
async def test_busy_and_throughput(dut):
    e = await setup(dut)
    await clear(e)
    rng = random.Random(21)
    await push(e, [rng.randint(-32768, 32767) for _ in range(1024)], rng)
    t0 = e.cycles
    await wr(e, A_CTRL, 2)
    model_run(e)
    busy_seen = 0
    led_seen = 0
    done = False
    for _ in range(400):
        s = await rd(e, A_STAT)
        if e.led is not None and (int(e.led.value) & 1):
            led_seen += 1
        if s & 1:
            busy_seen += 1
        else:
            done = True
            break
    assert done and busy_seen > 0, "BUSY must be seen high, then low"
    if e.dp is not None:
        bound = 1024 * DP_NS / CLK_NS + 60
        assert e.cycles - t0 <= bound + 20, f"run took {e.cycles - t0} clk25 cycles, bound {bound}"
    if e.led is not None:
        assert led_seen > 0
        assert (int(e.led.value) & 1) == 0
    await cmp_rd(e, A_STAT)
    await pop_all(e)


# req: REQ-18, REQ-06, REQ-16, REQ-17
@cocotb.test()
async def test_random_chunks(dut):
    e = await setup(dut)
    await clear(e)
    rng = random.Random(cocotb.RANDOM_SEED)
    samples = [rng.randint(-32768, 32767) for _ in range(10000)]
    ref = Model()
    ref_out = []
    for i in range(0, 10000, 1000):
        chunk = samples[i:i + 1000]
        await push(e, chunk, rng)
        await run(e)
        await check_idle_regs(e)
        await pop_all(e)
    # reference: single sample-by-sample pass through a fresh model
    ref.reset()
    for x in samples:
        ref.write_reg(A_PUSH, x)
        ref.write_reg(A_CTRL, 2)
        while ref.read_reg(A_STAT) & 1:
            ref.step()
        ref_out.append(ref.read_reg(A_POP))
    chunked = Model()
    chunked_out = []
    for i in range(0, 10000, 1000):
        for x in samples[i:i + 1000]:
            chunked.write_reg(A_PUSH, x)
        chunked.write_reg(A_CTRL, 2)
        while chunked.read_reg(A_STAT) & 1:
            chunked.step()
        for _ in range(1000):
            chunked_out.append(chunked.read_reg(A_POP))
    assert ref_out == chunked_out
    assert e.m.read_reg(A_DONE) == 10000


# req: REQ-06, REQ-16, REQ-17, REQ-19, REQ-38, REQ-20, REQ-22, REQ-23, REQ-24, REQ-25, REQ-26, REQ-35, REQ-05, REQ-37
@cocotb.test()
async def test_random_ops(dut):
    e = await setup(dut)
    await clear(e)
    rng = random.Random(cocotb.RANDOM_SEED + 1000)
    for _ in range(150):
        op = rng.choice(["push", "push", "push", "run", "pop", "pop", "status", "scratch",
                         "unmapped", "clear", "extreme"])
        if op == "push":
            n = rng.randint(1, 40)
            await push(e, [rng.randint(-32768, 32767) for _ in range(n)], rng)
        elif op == "extreme":
            await push(e, [rng.choice([32767, -32768]) for _ in range(rng.randint(1, 40))], rng)
        elif op == "run":
            await run(e)
            await check_idle_regs(e)
        elif op == "pop":
            await cmp_rd(e, A_POP)
        elif op == "status":
            await cmp_rd(e, A_STAT)
        elif op == "scratch":
            await mwr(e, A_SCR, rng.getrandbits(32))
            await cmp_rd(e, A_SCR)
        elif op == "unmapped":
            a = rng.choice([0x00C, 0x028, 0x02C, 0x100, 0x7FC, 0xFFC])
            await wr(e, a, rng.getrandbits(32))
            assert await rd(e, a) == 0
        elif op == "clear" and rng.random() < 0.3:
            await clear(e)
    await run(e)
    await check_idle_regs(e)
    await pop_all(e)
    await check_idle_regs(e)
