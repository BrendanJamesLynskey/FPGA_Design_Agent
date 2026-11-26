"""cocotb bench for the 32-tap symmetric FIR register core, checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ReadOnly

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

CTRL, IN_PUSH, OUT_POP, STATUS, SAT, DONE = 16, 20, 24, 28, 32, 36
DEPTH = 1024
CLK_NS = 40
DSP_NS = 4


def _clock(sig, ns):
    try:
        return Clock(sig, ns, units="ns")
    except TypeError:
        return Clock(sig, ns, unit="ns")


def _rng():
    return random.Random(getattr(cocotb, "RANDOM_SEED", 1))


async def init(dut):
    cocotb.start_soon(_clock(dut.clk, CLK_NS).start())
    if hasattr(dut, "clk_dsp"):
        cocotb.start_soon(_clock(dut.clk_dsp, DSP_NS).start())
    for n in ("locked", "mmcm_locked", "dsp_locked"):
        if hasattr(dut, n):
            getattr(dut, n).value = 1
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    dut.rst.value = 1
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(12):
        await RisingEdge(dut.clk)
    return Model()


async def bwrite(dut, addr, val):
    dut.h_addr.value = addr
    dut.h_wdata.value = val & 0xFFFFFFFF
    dut.h_we.value = 1
    await RisingEdge(dut.clk)
    dut.h_we.value = 0


async def bread(dut, addr):
    dut.h_addr.value = addr
    dut.h_re.value = 1
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    return int(dut.h_rdata.value)


async def push_many(dut, m, vals):
    for v in vals:
        await bwrite(dut, IN_PUSH, v)
        m.write_reg(IN_PUSH, v)


def m_run(m):
    m.write_reg(CTRL, 2)
    for _ in range(5000):
        if not (m.read_reg(STATUS) & 1):
            break
        m.step()


async def wait_done(dut, m, limit=4000):
    want = len(m.outfifo)
    for _ in range(limit):
        st = await bread(dut, STATUS)
        if (st & 1) == 0 and (st >> 20) == want:
            return
    raise AssertionError("run did not finish: STATUS=0x%08x want out count %d" % (st, want))


async def do_run(dut, m):
    await bwrite(dut, CTRL, 2)
    m_run(m)
    await wait_done(dut, m)


async def drain_compare(dut, m, count=None):
    n = len(m.outfifo) if count is None else count
    for i in range(n):
        got = await bread(dut, OUT_POP)
        exp = m.read_reg(OUT_POP)
        assert got == exp, "pop %d: got 0x%08x exp 0x%08x" % (i, got, exp)


async def check_regs(dut, m):
    for off in (STATUS, SAT, DONE, 8, 0):
        got = await bread(dut, off)
        exp = m.read_reg(off)
        assert got == exp, "reg 0x%x got 0x%08x exp 0x%08x" % (off, got, exp)


def sample(rng, kind=None):
    k = kind or rng.choice(["zero", "one", "max", "min", "rand", "rand"])
    return {"zero": 0, "one": 1, "max": 0x7FFF, "min": 0x8000}.get(k) if k != "rand" else rng.getrandbits(16)


# req: REQ-01, REQ-31, REQ-16, REQ-25
@cocotb.test()
async def test_reset_values(dut):
    m = await init(dut)
    assert await bread(dut, 0) == 546570241 == 0x20940001
    assert await bread(dut, 8) == 0
    assert await bread(dut, STATUS) == m.read_reg(STATUS) == 0
    assert await bread(dut, SAT) == 0
    assert await bread(dut, DONE) == 0
    assert await bread(dut, OUT_POP) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    for _ in range(50):
        await RisingEdge(dut.clk)
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-03, REQ-31
@cocotb.test()
async def test_scratch(dut):
    m = await init(dut)
    rng = _rng()
    pats = [0xFFFFFFFF, 0, 0x12345678, 0x80000000, 1, 0xA5A5A5A5, 0x5A5A5A5A]
    pats += [rng.getrandbits(32) for _ in range(20)]
    for p in pats:
        await bwrite(dut, 8, p)
        got = await bread(dut, 8)
        assert got == p, "scratch got 0x%x exp 0x%x" % (got, p)
        assert await bread(dut, 0) == 0x20940001
    # reset clears scratch
    dut.rst.value = 1
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(12):
        await RisingEdge(dut.clk)
    assert await bread(dut, 8) == 0


# req: REQ-04, REQ-05
@cocotb.test()
async def test_unmapped(dut):
    m = await init(dut)
    addrs = [0x00C, 0x028, 0x02C, 0x030, 0x040, 0x080, 0x100, 0x3FC, 0x7FC, 0xFFC, 0x800]
    for a in addrs:
        assert await bread(dut, a) == 0, "unmapped read 0x%x" % a
    await bwrite(dut, 8, 0xCAFEF00D)
    m.write_reg(8, 0xCAFEF00D)
    await push_many(dut, m, [1, 2, 3])
    for a in addrs:
        await bwrite(dut, a, 0xFFFFFFFF)
        assert await bread(dut, a) == 0
    await check_regs(dut, m)
    await bwrite(dut, 8, 0)
    m.write_reg(8, 0)
    await do_run(dut, m)
    await drain_compare(dut, m)
    await check_regs(dut, m)


# req: REQ-06, REQ-32
@cocotb.test()
async def test_rdata_timing_hold(dut):
    m = await init(dut)
    await bwrite(dut, 8, 0xDEADBEEF)
    # read each register, sample exactly 2 clocks after the h_re edge, then check hold
    for addr, exp in ((0, 0x20940001), (8, 0xDEADBEEF), (STATUS, 0), (SAT, 0), (DONE, 0)):
        dut.h_addr.value = addr
        dut.h_re.value = 1
        await RisingEdge(dut.clk)
        dut.h_re.value = 0
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.h_rdata.value) == exp, "addr 0x%x" % addr
        for i in range(6):
            if i == 2:
                dut.h_addr.value = 0x14
                await bwrite(dut, 8, 0xDEADBEEF)
            await RisingEdge(dut.clk)
            await Timer(1, "ns")
            assert int(dut.h_rdata.value) == exp, "hold addr 0x%x" % addr


async def _impulse_like(dut, m, vals):
    await push_many(dut, m, vals)
    await do_run(dut, m)
    await drain_compare(dut, m)
    await check_regs(dut, m)


# req: REQ-07, REQ-17
@cocotb.test()
async def test_impulse(dut):
    m = await init(dut)
    await _impulse_like(dut, m, [0x7FFF] + [0] * 63)
    await _impulse_like(dut, m, [0x8000] + [0] * 63)
    await _impulse_like(dut, m, [1] + [0] * 63)


# req: REQ-08, REQ-17
@cocotb.test()
async def test_step(dut):
    m = await init(dut)
    await _impulse_like(dut, m, [0x2000] * 80)
    await _impulse_like(dut, m, [0xE000] * 80)
    await _impulse_like(dut, m, [0x7FFF] * 80)


# req: REQ-09, REQ-17, REQ-18, REQ-24
@cocotb.test()
async def test_random_chunks_10000(dut):
    m = await init(dut)
    rng = _rng()
    for _chunk in range(10):
        vals = [rng.getrandbits(16) for _ in range(1000)]
        await push_many(dut, m, vals)
        await do_run(dut, m)
        await drain_compare(dut, m)
    await check_regs(dut, m)
    assert m.read_reg(DONE) == 10000


# req: REQ-13, REQ-33, REQ-14, REQ-22, REQ-34, REQ-24
@cocotb.test()
async def test_fifo_capacity(dut):
    m = await init(dut)
    rng = _rng()
    vals = [rng.getrandbits(16) | (rng.getrandbits(16) << 16) & 0 for _ in range(DEPTH)]
    await push_many(dut, m, vals)
    st = await bread(dut, STATUS)
    assert (st >> 4) & 0xFFF == DEPTH and st == m.read_reg(STATUS)
    # full: further pushes are ignored
    await push_many(dut, m, [0x1234, 0x4321, 0xFFFF])
    st = await bread(dut, STATUS)
    assert (st >> 4) & 0xFFF == DEPTH
    await do_run(dut, m)
    st = await bread(dut, STATUS)
    assert (st >> 20) == DEPTH and (st >> 4) & 0xFFF == 0
    assert st == m.read_reg(STATUS)
    # output FIFO full: more results are dropped, SAMPLES_DONE still counts
    await push_many(dut, m, [5, 6, 7, 8, 9])
    await do_run(dut, m)
    await check_regs(dut, m)
    await drain_compare(dut, m)
    assert await bread(dut, OUT_POP) == 0
    await check_regs(dut, m)


# req: REQ-15, REQ-16, REQ-22, REQ-34
@cocotb.test()
async def test_pop_semantics(dut):
    m = await init(dut)
    assert await bread(dut, OUT_POP) == 0
    await push_many(dut, m, [0x7FFF, 0x8000, 3, 4])
    await do_run(dut, m)
    st = await bread(dut, STATUS)
    assert (st >> 20) == 4 and (st >> 4) & 0xFFF == 0
    for left in (3, 2, 1, 0):
        got = await bread(dut, OUT_POP)
        exp = m.read_reg(OUT_POP)
        assert got == exp and (got >> 31) == 1
        st = await bread(dut, STATUS)
        assert (st >> 20) == left
    assert await bread(dut, OUT_POP) == 0
    assert await bread(dut, OUT_POP) == 0


# req: REQ-18
@cocotb.test()
async def test_history_persists(dut):
    m = await init(dut)
    rng = _rng()
    for _ in range(3):
        await _impulse_like(dut, m, [rng.getrandbits(16) for _ in range(20)])
    # history of a run affects the next one: a lone zero-run after full-scale data
    await _impulse_like(dut, m, [0x7FFF] * 40)
    await _impulse_like(dut, m, [0] * 40)


# req: REQ-19, REQ-20, REQ-24, REQ-23
@cocotb.test()
async def test_clear(dut):
    m = await init(dut)
    rng = _rng()
    await _impulse_like(dut, m, [rng.getrandbits(16) for _ in range(30)])
    await push_many(dut, m, [rng.getrandbits(16) for _ in range(30)])
    await do_run(dut, m)
    await push_many(dut, m, [rng.getrandbits(16) for _ in range(10)])
    await bwrite(dut, CTRL, 1)
    m.write_reg(CTRL, 1)
    assert await bread(dut, CTRL) == 0 == m.read_reg(CTRL)
    for _ in range(6):
        await RisingEdge(dut.clk)
    await check_regs(dut, m)
    assert await bread(dut, STATUS) == 0
    assert await bread(dut, OUT_POP) == 0
    # history is zero: an impulse behaves as on a fresh filter
    await _impulse_like(dut, m, [0x4000] + [0] * 40)
    # RUN bit self-clears
    await bwrite(dut, CTRL, 2)
    assert await bread(dut, CTRL) == 0
    # CLEAR during a run aborts it
    await push_many(dut, m, [rng.getrandbits(16) for _ in range(500)])
    await bwrite(dut, CTRL, 2)
    await bwrite(dut, CTRL, 1)
    m.write_reg(CTRL, 1)
    for _ in range(40):
        await RisingEdge(dut.clk)
    await check_regs(dut, m)
    assert await bread(dut, STATUS) == 0
    await _impulse_like(dut, m, [0x7FFF] + [0] * 40)


# req: REQ-21, REQ-17, REQ-22
@cocotb.test()
async def test_busy_status(dut):
    m = await init(dut)
    rng = _rng()
    assert (await bread(dut, STATUS)) & 1 == 0
    # RUN with an empty FIFO does nothing
    await bwrite(dut, CTRL, 2)
    for _ in range(10):
        await RisingEdge(dut.clk)
    assert await bread(dut, STATUS) == 0
    vals = [rng.getrandbits(16) for _ in range(800)]
    await push_many(dut, m, vals)
    await bwrite(dut, CTRL, 2)
    m_run(m)
    st = await bread(dut, STATUS)
    assert st & 1 == 1, "BUSY not set after RUN"
    assert int(dut.led.value) & 1 == 1
    # RUN while busy ignored; pushes while busy accepted and held for the next RUN
    await bwrite(dut, CTRL, 2)
    extra = [rng.getrandbits(16) for _ in range(3)]
    await push_many(dut, m, extra)
    await wait_done(dut, m)
    st = await bread(dut, STATUS)
    assert st & 1 == 0 and (st >> 4) & 0xFFF == 3, "STATUS=0x%08x" % st
    assert int(dut.led.value) & 1 == 0
    await drain_compare(dut, m)
    await do_run(dut, m)
    await drain_compare(dut, m)
    await check_regs(dut, m)


# req: REQ-11
@cocotb.test()
async def test_throughput(dut):
    from cocotb.utils import get_sim_time
    m = await init(dut)
    rng = _rng()
    n = 1000
    await push_many(dut, m, [rng.getrandbits(16) for _ in range(n)])
    await bwrite(dut, CTRL, 2)
    t0 = get_sim_time("ns")
    m_run(m)
    seen = False
    for _ in range(2000):
        await RisingEdge(dut.clk)
        if int(dut.led.value) & 1:
            seen = True
        elif seen:
            break
    assert seen
    t1 = get_sim_time("ns")
    dsp_cycles = (t1 - t0) / DSP_NS
    assert dsp_cycles <= n + 120, "%d samples took %d dsp clocks" % (n, dsp_cycles)
    await wait_done(dut, m)
    await drain_compare(dut, m)


def _signs(m):
    h = getattr(m, "h", None)
    if h is None:
        h = model._default_coeffs(32)
    return h


# req: REQ-23, REQ-24, REQ-19
@cocotb.test()
async def test_saturation(dut):
    m = await init(dut)
    h = _signs(m)
    # newest sample pairs with h[0]: push taps in order 31..0
    pos = [0x7FFF if h[k] >= 0 else 0x8000 for k in range(31, -1, -1)]
    neg = [0x8000 if h[k] >= 0 else 0x7FFF for k in range(31, -1, -1)]
    await push_many(dut, m, pos + neg + pos + [0] * 40)
    await do_run(dut, m)
    assert m.sat > 0, "stimulus does not saturate the model"
    await check_regs(dut, m)
    await drain_compare(dut, m)
    assert await bread(dut, SAT) == m.sat
    await bwrite(dut, CTRL, 1)
    m.write_reg(CTRL, 1)
    for _ in range(6):
        await RisingEdge(dut.clk)
    assert await bread(dut, SAT) == 0 == await bread(dut, DONE)


# req: REQ-07, REQ-08, REQ-09, REQ-17, REQ-18, REQ-19, REQ-23, REQ-24, REQ-21, REQ-22, REQ-34, REQ-15, REQ-16, REQ-03, REQ-04, REQ-05
@cocotb.test()
async def test_random_ops(dut):
    m = await init(dut)
    rng = _rng()
    for it in range(150):
        r = rng.random()
        if r < 0.45:
            if len(m.infifo) + len(m.outfifo) > 900:
                continue
            kind = rng.choice(["zero", "one", "max", "min", "rand", "rand"])
            n = rng.randint(1, 60)
            vals = [sample(rng, kind if rng.random() < 0.5 else None) for _ in range(n)]
            await push_many(dut, m, vals)
        elif r < 0.65:
            if not m.infifo:
                continue
            await do_run(dut, m)
        elif r < 0.85:
            k = rng.randint(0, len(m.outfifo) + 1)
            await drain_compare(dut, m, k)
        elif r < 0.9:
            await bwrite(dut, CTRL, 1)
            m.write_reg(CTRL, 1)
            for _ in range(8):
                await RisingEdge(dut.clk)
        elif r < 0.95:
            v = rng.getrandbits(32)
            await bwrite(dut, 8, v)
            m.write_reg(8, v)
        else:
            a = rng.choice([0x0C, 0x28, 0x44, 0x200, 0xFFC])
            await bwrite(dut, a, rng.getrandbits(32))
            assert await bread(dut, a) == 0
        await check_regs(dut, m)
    await do_run(dut, m) if m.infifo else None
    await drain_compare(dut, m)
    await check_regs(dut, m)


# req: REQ-25
@cocotb.test()
async def test_sfp_constant(dut):
    m = await init(dut)
    await push_many(dut, m, list(range(100)))
    await bwrite(dut, CTRL, 2)
    for _ in range(150):
        await RisingEdge(dut.clk)
        assert int(dut.sfp_tx_disable.value) == 1
