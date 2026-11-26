"""cocotb bench for the fir32_sym register core, checked against model.Model."""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

CTRL, IN_PUSH, OUT_POP, STATUS, SAT, DONE = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24
ID, BUILD, SCRATCH = 0x0, 0x4, 0x8
DEPTH = 1024


def _has(dut, n):
    return hasattr(dut, n)


async def setup(dut):
    """Start clocks, reset the core, return a fresh model."""
    ck = "clk" if _has(dut, "clk") else "clk_25"
    cocotb.start_soon(Clock(getattr(dut, ck), 40, units="ns").start())
    if _has(dut, "clk_dsp"):
        cocotb.start_soon(Clock(dut.clk_dsp, 4, units="ns").start())
    dut._ck = getattr(dut, ck)
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    if _has(dut, "rst"):
        dut.rst.value = 1
    elif _has(dut, "rst_n"):
        dut.rst_n.value = 0
    for _ in range(12):
        await RisingEdge(dut._ck)
    if _has(dut, "rst"):
        dut.rst.value = 0
    elif _has(dut, "rst_n"):
        dut.rst_n.value = 1
    for _ in range(4):
        await RisingEdge(dut._ck)
    m = Model()
    m.reset()
    return m


async def hw(dut, addr, val):
    dut.h_addr.value = addr
    dut.h_wdata.value = val & 0xFFFFFFFF
    dut.h_we.value = 1
    await RisingEdge(dut._ck)
    dut.h_we.value = 0
    await RisingEdge(dut._ck)


async def hr(dut, addr, wait=2):
    dut.h_addr.value = addr
    dut.h_re.value = 1
    await RisingEdge(dut._ck)
    dut.h_re.value = 0
    for _ in range(wait):
        await RisingEdge(dut._ck)
    await Timer(1, units="ns")
    return int(dut.h_rdata.value)


async def wr(dut, m, addr, val):
    await hw(dut, addr, val)
    m.write_reg(addr, val)


async def rd(dut, m, addr, what=""):
    got = await hr(dut, addr)
    exp = m.read_reg(addr)
    assert got == exp, f"read {addr:#x} {what}: rtl {got:#x} model {exp:#x}"
    return got


async def push(dut, m, xs):
    for x in xs:
        await wr(dut, m, IN_PUSH, x & 0xFFFF)


async def wait_idle(dut, limit=20000):
    n = 0
    while True:
        s = await hr(dut, STATUS)
        n += 3
        if not (s & 1):
            return n
        assert n < limit, "BUSY never dropped"


async def run(dut, m):
    """Write RUN, wait for idle, bring the model to idle too. Returns clk_25 cycles taken."""
    await hw(dut, CTRL, 2)
    m.write_reg(CTRL, 2)
    n = await wait_idle(dut)
    for _ in range(3000):
        m.step()
    assert m.read_reg(STATUS) & 1 == 0
    return n


async def pop(dut, m, n):
    out = []
    for _ in range(n):
        out.append(await rd(dut, m, OUT_POP, "pop"))
    return out


def sgn(v):
    return v - 65536 if v >= 32768 else v


async def clear(dut, m):
    await wr(dut, m, CTRL, 1)
    await hr(dut, STATUS)


# req: REQ-01, REQ-03, REQ-33, REQ-25, REQ-28
@cocotb.test()
async def test_reset_and_common_regs(dut):
    m = await setup(dut)
    assert await hr(dut, ID) == 0x20940001
    assert await hr(dut, SCRATCH) == 0
    assert await hr(dut, STATUS) == 0
    assert await hr(dut, SAT) == 0
    assert await hr(dut, DONE) == 0
    assert await hr(dut, OUT_POP) == 0
    for v in (0xDEADBEEF, 0, 0xFFFFFFFF, 0x12345678, 1):
        await wr(dut, m, SCRATCH, v)
        assert await hr(dut, SCRATCH) == v
        await rd(dut, m, SCRATCH)
    # writes to RO registers are ignored
    await wr(dut, m, ID, 0x55)
    assert await hr(dut, ID) == 0x20940001
    # CTRL reads 0 after set
    await wr(dut, m, CTRL, 3)
    assert await hr(dut, CTRL) == 0
    await wr(dut, m, CTRL, 0xFFFFFFFC & 0xFFFFFFFC)
    assert await hr(dut, CTRL) == 0
    await hr(dut, BUILD)
    if _has(dut, "sfp_tx_disable"):
        for _ in range(20):
            assert int(dut.sfp_tx_disable.value) == 1
            await RisingEdge(dut._ck)


# req: REQ-04, REQ-05
@cocotb.test()
async def test_unmapped(dut):
    m = await setup(dut)
    await wr(dut, m, SCRATCH, 0xCAFEF00D)
    await push(dut, m, [100, 200, 300])
    un = [0x28, 0x2C, 0x30, 0x3C, 0x40, 0x80, 0x100, 0x400, 0x800, 0xFFC, 0x00C, 0x01C + 0x100]
    for a in un:
        assert await hr(dut, a) == 0, f"unmapped {a:#x}"
    for a in un:
        await hw(dut, a, 0xFFFFFFFF)
    for a in (SCRATCH, STATUS, SAT, DONE, ID):
        await rd(dut, m, a)
    await run(dut, m)
    await pop(dut, m, 3)
    for a in un:
        assert await hr(dut, a) == 0


# req: REQ-06, REQ-34
@cocotb.test()
async def test_read_latency_hold(dut):
    m = await setup(dut)
    await wr(dut, m, SCRATCH, 0xA5A5A5A5)
    # sample at exactly 2 clocks after the h_re edge, then check hold
    dut.h_addr.value = SCRATCH
    dut.h_re.value = 1
    await RisingEdge(dut._ck)
    dut.h_re.value = 0
    await RisingEdge(dut._ck)
    await RisingEdge(dut._ck)
    await Timer(1, units="ns")
    assert int(dut.h_rdata.value) == 0xA5A5A5A5
    for _ in range(6):
        await RisingEdge(dut._ck)
        await Timer(1, units="ns")
        assert int(dut.h_rdata.value) == 0xA5A5A5A5
    # address change without h_re must not change h_rdata
    dut.h_addr.value = ID
    for _ in range(4):
        await RisingEdge(dut._ck)
    await Timer(1, units="ns")
    assert int(dut.h_rdata.value) == 0xA5A5A5A5
    assert await hr(dut, ID) == 0x20940001
    for _ in range(4):
        await RisingEdge(dut._ck)
    assert int(dut.h_rdata.value) == 0x20940001
    # write effect one clock after h_we: write then read request on the next cycle
    dut.h_addr.value = SCRATCH
    dut.h_wdata.value = 0x600DF00D
    dut.h_we.value = 1
    await RisingEdge(dut._ck)
    dut.h_we.value = 0
    dut.h_re.value = 1
    await RisingEdge(dut._ck)
    dut.h_re.value = 0
    await RisingEdge(dut._ck)
    await RisingEdge(dut._ck)
    await Timer(1, units="ns")
    assert int(dut.h_rdata.value) == 0x600DF00D


# req: REQ-07, REQ-09, REQ-19, REQ-08, REQ-17
@cocotb.test()
async def test_impulse_and_first_samples(dut):
    m = await setup(dut)
    await push(dut, m, [0, 0, 0, 32767] + [0] * 40)
    await run(dut, m)
    out = await pop(dut, m, 44)
    assert all(sgn(v & 0xFFFF) == 0 for v in out[:3]), "samples before first must give 0 output"
    assert all(v & 0x80000000 for v in out)
    # impulse response equals the model's (coeffs) response: compare against model of a second impulse
    m2 = Model()
    m2.write_reg(IN_PUSH, 32767)
    for _ in range(31):
        m2.write_reg(IN_PUSH, 0)
    m2.write_reg(CTRL, 2)
    for _ in range(100):
        m2.step()
    h = [sgn(m2.read_reg(OUT_POP) & 0xFFFF) for _ in range(32)]
    got = [sgn(v & 0xFFFF) for v in out[3:35]]
    assert got == h
    assert any(h), "impulse response is all zero"
    assert h == h[::-1], "coefficients not symmetric"
    assert all(sgn(v & 0xFFFF) == 0 for v in out[35:]), "tail not zero"


# req: REQ-07, REQ-19, REQ-26, REQ-27, REQ-21, REQ-35, REQ-20
@cocotb.test()
async def test_saturation_and_counters(dut):
    m = await setup(dut)
    m0 = Model()
    # probe coefficient sign pattern from the model's own impulse response
    m0.write_reg(IN_PUSH, 32767)
    for _ in range(31):
        m0.write_reg(IN_PUSH, 0)
    m0.write_reg(CTRL, 2)
    for _ in range(100):
        m0.step()
    h = [sgn(m0.read_reg(OUT_POP) & 0xFFFF) for _ in range(32)]
    for mag, s in ((-32768, 1), (32767, 1), (-32768, -1), (32767, -1)):
        await clear(dut, m)
        xs = [(mag * (1 if hk >= 0 else -1) * s) & 0xFFFF for hk in reversed(h)] * 3
        await push(dut, m, xs)
        assert await hr(dut, STATUS) == (len(xs) << 4)
        await rd(dut, m, STATUS, "in count")
        await hw(dut, CTRL, 2)
        m.write_reg(CTRL, 2)
        s0 = await hr(dut, STATUS)
        assert s0 & 1, "BUSY not set after RUN"
        if _has(dut, "led"):
            assert int(dut.led.value) & 1 == 1
        await wait_idle(dut)
        for _ in range(500):
            m.step()
        await rd(dut, m, STATUS, "after run")
        assert (await hr(dut, STATUS)) >> 20 == len(xs)
        assert await hr(dut, DONE) == len(xs)
        await rd(dut, m, SAT, "sat")
        await rd(dut, m, DONE, "done")
        await pop(dut, m, len(xs))
        assert (await hr(dut, STATUS)) >> 20 == 0
        if _has(dut, "led"):
            assert int(dut.led.value) & 1 == 0
    # saturating run
    assert m.read_reg(SAT) >= 0
    # saturated outputs counted: after CLEAR zero
    await clear(dut, m)
    assert await hr(dut, SAT) == 0
    assert await hr(dut, DONE) == 0
    await rd(dut, m, SAT)


# req: REQ-14, REQ-15, REQ-16, REQ-21, REQ-35, REQ-19, REQ-07, REQ-12
@cocotb.test()
async def test_fifo_full(dut):
    m = await setup(dut)
    rnd = random.Random(7)
    xs = [rnd.randrange(65536) for _ in range(DEPTH)]
    await push(dut, m, xs)
    st = await rd(dut, m, STATUS, "full in")
    assert (st >> 4) & 0xFFF == DEPTH
    # extra pushes are ignored
    await push(dut, m, [0x1234, 0x4321, 5])
    st = await rd(dut, m, STATUS, "still full")
    assert (st >> 4) & 0xFFF == DEPTH
    n = await run(dut, m)
    # one sample per clk_dsp cycle: 1024 samples take ~103 clk_25 cycles; allow slack, 1 per clk_25 would be >1024
    assert n < 500, f"datapath too slow: {n} clk_25 cycles for {DEPTH} samples"
    st = await rd(dut, m, STATUS, "full out")
    assert (st >> 20) == DEPTH
    assert (st >> 4) & 0xFFF == 0
    await rd(dut, m, DONE)
    out = await pop(dut, m, DEPTH)
    assert all(v & 0x80000000 for v in out)
    assert await hr(dut, OUT_POP) == 0
    await rd(dut, m, STATUS)
    # pop removes oldest: partial pops
    await push(dut, m, xs[:50])
    await run(dut, m)
    await pop(dut, m, 20)
    st = await rd(dut, m, STATUS, "after partial pop")
    assert (st >> 20) == 30


# req: REQ-23, REQ-22, REQ-24, REQ-37, REQ-32, REQ-18
@cocotb.test()
async def test_clear_and_history(dut):
    m = await setup(dut)
    rnd = random.Random(11)
    a = [rnd.randrange(65536) for _ in range(40)]
    b = [rnd.randrange(65536) for _ in range(40)]
    await push(dut, m, a)
    await run(dut, m)
    await push(dut, m, b)  # history from first run must persist
    await run(dut, m)
    await rd(dut, m, DONE)
    await rd(dut, m, SAT)
    await pop(dut, m, 80)
    # clear with data in both fifos and non-zero counters
    await push(dut, m, a)
    await run(dut, m)
    await push(dut, m, b[:10])
    await wr(dut, m, CTRL, 1)
    for r in (STATUS, SAT, DONE, OUT_POP, CTRL):
        await rd(dut, m, r, "after clear")
    assert await hr(dut, STATUS) == 0
    assert await hr(dut, DONE) == 0
    assert await hr(dut, OUT_POP) == 0
    # history zero: impulse-free stream gives same as fresh
    await push(dut, m, b)
    await run(dut, m)
    out = await pop(dut, m, 40)
    assert len(out) == 40
    # CLEAR and RUN in the same write: clear wins
    await push(dut, m, a)
    await wr(dut, m, CTRL, 3)
    await hr(dut, STATUS)
    assert await hr(dut, STATUS) == 0
    await rd(dut, m, STATUS)
    # RUN with empty fifo: no effect
    await wr(dut, m, CTRL, 2)
    await hr(dut, STATUS)
    assert (await hr(dut, STATUS)) & 1 == 0
    await rd(dut, m, STATUS)


# req: REQ-10, REQ-07, REQ-32, REQ-19
@cocotb.test()
async def test_chunked_stream(dut):
    m = await setup(dut)
    big = Model(FIFO_DEPTH=16384)
    rnd = random.Random(2024)
    xs = [rnd.randrange(65536) for _ in range(10000)]
    for x in xs:
        big.write_reg(IN_PUSH, x)
    big.write_reg(CTRL, 2)
    for _ in range(2000):
        big.step()
    ref = [big.read_reg(OUT_POP) for _ in range(10000)]
    got = []
    for c in range(10):
        chunk = xs[c * 1000:(c + 1) * 1000]
        for x in chunk:
            await hw(dut, IN_PUSH, x)
        await hw(dut, CTRL, 2)
        n = await wait_idle(dut)
        assert n < 1500, "1000 samples took too long"
        for _ in range(1000):
            got.append(await hr(dut, OUT_POP))
    assert got == ref
    assert await hr(dut, DONE) == 10000


# req: REQ-07, REQ-09, REQ-10, REQ-12, REQ-17, REQ-18, REQ-19, REQ-20, REQ-26, REQ-27, REQ-32, REQ-22, REQ-23
@cocotb.test()
async def test_random_traffic(dut):
    m = await setup(dut)
    seed = int(os.environ.get("RANDOM_SEED", "1")) if False else getattr(cocotb, "RANDOM_SEED", 1)
    rnd = random.Random(seed)
    for it in range(60):
        r = rnd.random()
        if r < 0.1:
            await clear(dut, m)
            await rd(dut, m, STATUS, "rnd clear")
        else:
            n = rnd.choice([1, 2, 5, 31, 32, 33, 64, 100])
            kind = rnd.choice(["rand", "rand", "max", "min", "small", "alt"])
            if kind == "rand":
                xs = [rnd.randrange(65536) for _ in range(n)]
            elif kind == "max":
                xs = [32767] * n
            elif kind == "min":
                xs = [0x8000] * n
            elif kind == "small":
                xs = [rnd.randrange(-50, 50) & 0xFFFF for _ in range(n)]
            else:
                xs = [(32767 if i & 1 else 0x8000) for i in range(n)]
            xs = xs[:max(0, DEPTH - (m.read_reg(STATUS) >> 20) - (m.read_reg(STATUS) >> 4 & 0xFFF))]
            await push(dut, m, xs)
            await rd(dut, m, STATUS, "rnd in")
            await run(dut, m)
            await rd(dut, m, STATUS, "rnd after run")
            await rd(dut, m, SAT, "rnd sat")
            await rd(dut, m, DONE, "rnd done")
            k = rnd.randint(0, (m.read_reg(STATUS) >> 20) + 1)
            await pop(dut, m, k)
            await rd(dut, m, STATUS, "rnd after pop")
            if rnd.random() < 0.3:
                await wr(dut, m, SCRATCH, rnd.getrandbits(32))
                await rd(dut, m, SCRATCH)
    # drain
    while (m.read_reg(STATUS) >> 20) > 0:
        await pop(dut, m, 1)
    await pop(dut, m, 1)
