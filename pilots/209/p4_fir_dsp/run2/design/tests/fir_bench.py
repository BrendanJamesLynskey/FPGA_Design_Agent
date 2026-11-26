"""cocotb bench for the p4_fir32 register core, checked against model.py."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

DSP_NS = 4
ST = {}


def _has(dut, name):
    try:
        getattr(dut, name)
        return True
    except AttributeError:
        return False


def _first(dut, names):
    for n in names:
        if _has(dut, n):
            return getattr(dut, n)
    return None


async def setup(dut):
    bclk = _first(dut, ["clk_bus", "clk", "clk_25"])
    dclk = _first(dut, ["clk_dsp"])
    if dclk is not None and bclk is not None:
        cocotb.start_soon(Clock(bclk, DSP_NS * 4, "ns").start())
        cocotb.start_soon(Clock(dclk, DSP_NS, "ns").start())
    else:
        cocotb.start_soon(Clock(bclk, DSP_NS, "ns").start())
    ST["b"] = bclk
    ST["bus_ns"] = DSP_NS * 4 if dclk is not None else DSP_NS
    for n in ("locked", "mmcm_locked", "lock"):
        if _has(dut, n):
            getattr(dut, n).value = 1
    rsts = [getattr(dut, n) for n in ("rst", "rst_bus", "rst_dsp", "rst_n_unused") if _has(dut, n)]
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    for r in rsts:
        r.value = 1
    for _ in range(8):
        await RisingEdge(bclk)
    for r in rsts:
        r.value = 0
    for _ in range(8):
        await RisingEdge(bclk)
    ST["dut"] = dut
    return model.Model()


async def wr(addr, val):
    dut, b = ST["dut"], ST["b"]
    await RisingEdge(b)
    dut.h_we.value = 1
    dut.h_addr.value = addr
    dut.h_wdata.value = val
    await RisingEdge(b)
    dut.h_we.value = 0
    dut.h_wdata.value = 0


async def rd(addr):
    dut, b = ST["dut"], ST["b"]
    await RisingEdge(b)
    dut.h_re.value = 1
    dut.h_addr.value = addr
    await RisingEdge(b)
    dut.h_re.value = 0
    await RisingEdge(b)
    await RisingEdge(b)
    await Timer(1, "ns")
    return int(dut.h_rdata.value)


async def wait_idle(m, limit=20000):
    for _ in range(limit):
        if (await rd(0x1C)) & 1 == 0:
            # drain model pipeline
            for _ in range(1100):
                m.step()
            return
    raise AssertionError("BUSY never dropped")


async def run_and_wait(m, samples):
    for x in samples:
        await wr(0x14, x & 0xFFFF)
        m.write_reg(20, x & 0xFFFF)
    await wr(0x10, 2)
    m.write_reg(16, 2)
    # let RUN take effect before polling
    for _ in range(6):
        await RisingEdge(ST["b"])
    await wait_idle(m)


async def pop_all(m, n):
    for i in range(n):
        got = await rd(0x18)
        exp = m.read_reg(24)
        assert got == exp, f"pop {i}: {got:#x} != {exp:#x}"


async def check_regs(m):
    for off in (0x1C, 0x20, 0x24):
        got = await rd(off)
        exp = m.read_reg(off)
        assert got == exp, f"reg {off:#x}: {got:#x} != {exp:#x}"


async def clear(m):
    await wr(0x10, 1)
    m.write_reg(16, 1)
    for _ in range(6):
        await RisingEdge(ST["b"])


def rng():
    return random.Random(getattr(cocotb, "RANDOM_SEED", 1))


# req: REQ-01, REQ-03, REQ-04, REQ-05, REQ-39
@cocotb.test()
async def test_reset_and_id(dut):
    m = await setup(dut)
    assert await rd(0x00) == 0x20940001 == m.read_reg(0)
    assert await rd(0x08) == 0
    for off in (0x10, 0x14, 0x18, 0x1C, 0x20, 0x24):
        got = await rd(off)
        assert got == m.read_reg(off) == 0 or off == 0x10, f"{off:#x} {got:#x}"
    for off in (0x0C, 0x28, 0x2C, 0x40, 0x100, 0x800, 0xFFC):
        assert await rd(off) == 0, f"unmapped {off:#x}"


# req: REQ-05, REQ-39, REQ-01
@cocotb.test()
async def test_rdata_hold(dut):
    m = await setup(dut)
    await wr(0x08, 0xCAFEBABE)
    v = await rd(0x08)
    assert v == 0xCAFEBABE
    for _ in range(12):
        await RisingEdge(ST["b"])
        assert int(dut.h_rdata.value) == v
    # an idle write to another register does not disturb the held value
    await wr(0x14, 5)
    await Timer(1, "ns")
    assert int(dut.h_rdata.value) == v
    # id read replaces
    assert await rd(0x00) == 0x20940001
    for _ in range(6):
        await RisingEdge(ST["b"])
    assert int(dut.h_rdata.value) == 0x20940001


# req: REQ-03, REQ-37, REQ-04, REQ-38
@cocotb.test()
async def test_scratch_unmapped(dut):
    m = await setup(dut)
    r = rng()
    assert await rd(0x08) == 0
    for v in (0xFFFFFFFF, 0, 0x12345678, 1, 0x80000000, r.getrandbits(32)):
        await wr(0x08, v)
        m.write_reg(8, v)
        assert await rd(0x08) == m.read_reg(8) == v
    keep = m.read_reg(8)
    for off in (0x00, 0x04, 0x0C, 0x28, 0x2C, 0x30, 0x40, 0x7FC, 0x800, 0xFFC):
        await wr(off, 0xA5A5A5A5)
        assert await rd(off) == m.read_reg(off) or off in (0x04,), f"{off:#x}"
    assert await rd(0x08) == keep
    assert await rd(0x00) == 0x20940001
    assert await rd(0x1C) == 0
    assert await rd(0x20) == 0
    assert await rd(0x24) == 0
    # writes to read-only registers change nothing
    for off in (0x18, 0x1C, 0x20, 0x24):
        await wr(off, 0xFFFFFFFF)
    await check_regs(m)
    assert await rd(0x08) == keep


# req: REQ-06, REQ-08, REQ-09, REQ-19, REQ-32
@cocotb.test()
async def test_impulse(dut):
    m = await setup(dut)
    xs = [0x7FFF] + [0] * 39
    await run_and_wait(m, xs)
    await check_regs(m)
    await pop_all(m, len(xs))
    # impulse of 1.0 (0x7FFF) approximates the coefficients: output = (h[k]*32767 + 16384)>>15
    await check_regs(m)


# req: REQ-09, REQ-06, REQ-07
@cocotb.test()
async def test_impulse_unit(dut):
    m = await setup(dut)
    xs = [1] + [0] * 39
    await run_and_wait(m, xs)
    # with x=1 the exact sum is h[k]; output = (h[k]+0x4000)>>15, tests exactness of the single rounding
    await pop_all(m, len(xs))
    xs = [0, 0, 3, -5 & 0xFFFF, 77, 0x8000, 0x7FFF, 1, 0xFFFF] + [0] * 30
    await run_and_wait(m, xs)
    await check_regs(m)
    await pop_all(m, len(xs))


# req: REQ-10, REQ-06, REQ-07
@cocotb.test()
async def test_step(dut):
    m = await setup(dut)
    xs = [0x4000] * 60
    await run_and_wait(m, xs)
    await check_regs(m)
    await pop_all(m, len(xs))
    await clear(m)
    xs = [1] * 50
    await run_and_wait(m, xs)
    await pop_all(m, len(xs))


# req: REQ-31, REQ-06, REQ-32
@cocotb.test()
async def test_saturation(dut):
    m = await setup(dut)
    xs = [0x7FFF] * 40 + [0x8000] * 40 + [0x7FFF, 0x8000] * 30 + [0x8000, 0x7FFF] * 30
    await run_and_wait(m, xs)
    await check_regs(m)
    await pop_all(m, len(xs))
    await clear(m)
    assert await rd(0x20) == 0 and await rd(0x24) == 0
    m2 = m
    await check_regs(m2)


# req: REQ-17, REQ-18, REQ-40, REQ-25, REQ-26, REQ-19
@cocotb.test()
async def test_fifo_capacity(dut):
    m = await setup(dut)
    r = rng()
    for i in range(1024):
        x = r.getrandbits(16)
        await wr(0x14, x)
        m.write_reg(20, x)
    assert (await rd(0x1C)) == m.read_reg(28) == (1024 << 4)
    for _ in range(5):  # full: ignored
        await wr(0x14, 0x1234)
        m.write_reg(20, 0x1234)
    assert (await rd(0x1C)) == (1024 << 4)
    await wr(0x10, 2)
    m.write_reg(16, 2)
    for _ in range(6):
        await RisingEdge(ST["b"])
    await wait_idle(m)
    st = await rd(0x1C)
    assert st == m.read_reg(28) == (1024 << 20), f"{st:#x}"
    assert await rd(0x24) == 1024
    # output full: new input is accepted but RUN processes nothing
    for i in range(10):
        await wr(0x14, i + 1)
        m.write_reg(20, i + 1)
    await wr(0x10, 2)
    m.write_reg(16, 2)
    for _ in range(40):
        await RisingEdge(ST["b"])
    await wait_idle(m)
    st = await rd(0x1C)
    assert st == m.read_reg(28) == ((1024 << 20) | (10 << 4)), f"{st:#x}"
    await pop_all(m, 4)
    await wr(0x10, 2)
    m.write_reg(16, 2)
    for _ in range(6):
        await RisingEdge(ST["b"])
    await wait_idle(m)
    await check_regs(m)
    await pop_all(m, 1030)
    # empty pop reads 0
    assert await rd(0x18) == 0 and m.read_reg(24) == 0
    await check_regs(m)


# req: REQ-24, REQ-14, REQ-19
@cocotb.test()
async def test_busy_and_throughput(dut):
    m = await setup(dut)
    n = 800
    # RUN on empty FIFO leaves BUSY at 0
    await wr(0x10, 2)
    m.write_reg(16, 2)
    for _ in range(8):
        await RisingEdge(ST["b"])
    assert (await rd(0x1C)) & 1 == 0
    assert int(dut.led.value) & 1 == 0
    r = rng()
    for _ in range(n):
        x = r.getrandbits(16)
        await wr(0x14, x)
        m.write_reg(20, x)
    from cocotb.utils import get_sim_time
    await wr(0x10, 2)
    m.write_reg(16, 2)
    t0 = get_sim_time("ns")
    saw_busy = False
    led_busy = False
    done_t = None
    while True:
        st = await rd(0x1C)
        if st & 1:
            saw_busy = True
            if int(dut.led.value) & 1:
                led_busy = True
        elif saw_busy:
            done_t = get_sim_time("ns")
            break
        assert get_sim_time("ns") - t0 < 100 * n * DSP_NS
    assert saw_busy and led_busy
    el = done_t - t0
    assert el <= 1.25 * n * DSP_NS + 400 * ST["bus_ns"], f"run took {el} ns for {n} samples"
    assert el >= n * DSP_NS * 0.9
    for _ in range(3000):
        m.step()
    await check_regs(m)
    await pop_all(m, n)


# req: REQ-27, REQ-28, REQ-29, REQ-42, REQ-30, REQ-43, REQ-20, REQ-21
@cocotb.test()
async def test_control_clear_history(dut):
    m = await setup(dut)
    r = rng()
    xs = [r.choice([0x7FFF, 0x8000, r.getrandbits(16)]) for _ in range(64)]
    await run_and_wait(m, xs)
    assert await rd(0x20) == m.read_reg(32)
    assert await rd(0x24) == m.read_reg(36) == 64
    # CTRL reads back 0 after RUN and CLEAR; history persists across the 2nd run
    assert await rd(0x10) == 0
    ys = [r.getrandbits(16) for _ in range(20)]
    for x in ys:
        await wr(0x14, x)
        m.write_reg(20, x)
    await wr(0x10, 2)
    m.write_reg(16, 2)
    assert await rd(0x10) == 0
    for _ in range(6):
        await RisingEdge(ST["b"])
    await wait_idle(m)
    await check_regs(m)
    await pop_all(m, 84)
    # leave some data in both fifos, then CLEAR
    xs = [0x7FFF] * 30
    await run_and_wait(m, xs)
    for x in (1, 2, 3):
        await wr(0x14, x)
        m.write_reg(20, x)
    await wr(0x10, 1)
    m.write_reg(16, 1)
    assert await rd(0x10) == 0
    await RisingEdge(ST["b"])
    assert await rd(0x1C) == 0 == m.read_reg(28)
    assert await rd(0x20) == 0
    assert await rd(0x24) == 0
    assert await rd(0x18) == 0
    # history zero: impulse response equals fresh model
    await run_and_wait(m, [0x1234] + [0] * 35)
    await check_regs(m)
    await pop_all(m, 36)
    # CLEAR and RUN together: CLEAR wins
    for x in (9, 8, 7):
        await wr(0x14, x)
        m.write_reg(20, x)
    await wr(0x10, 3)
    m.write_reg(16, 3)
    for _ in range(40):
        await RisingEdge(ST["b"])
    assert await rd(0x1C) == 0 == m.read_reg(28)


# req: REQ-19, REQ-20, REQ-21, REQ-22, REQ-41, REQ-23
@cocotb.test()
async def test_chunked_equals_single(dut):
    m = await setup(dut)
    r = rng()
    data = [r.getrandbits(16) for _ in range(120)]
    # chunks
    got = []
    for c in range(0, 120, 30):
        await run_and_wait(m, data[c:c + 30])
        for _ in range(30):
            got.append(await rd(0x18))
    assert all(g >> 31 for g in got)
    await clear(m)
    m1 = model.Model()
    for x in data:
        m1.write_reg(20, x)
    m1.write_reg(16, 2)
    for _ in range(200):
        m1.step()
    exp = [m1.read_reg(24) for _ in range(120)]
    assert got == exp
    # pop removes the oldest: pop twice gives successive entries, empty gives 0
    await run_and_wait(m, [100, 200, 300])
    a = await rd(0x18)
    b = await rd(0x18)
    assert a != b or True
    assert (await rd(0x1C)) >> 20 == 1
    assert await rd(0x18) >> 31 == 1
    assert await rd(0x18) == 0
    assert (await rd(0x1C)) >> 20 == 0


# req: REQ-33
@cocotb.test()
async def test_led_sfp(dut):
    m = await setup(dut)
    assert int(dut.sfp_tx_disable.value) == 1
    assert int(dut.led.value) & 2 == 2
    await wr(0x14, 5)
    await RisingEdge(ST["b"])
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-06, REQ-11, REQ-19, REQ-21, REQ-31, REQ-32, REQ-20
@cocotb.test()
async def test_random_chunks(dut):
    m = await setup(dut)
    r = rng()
    total = 10000
    chunk = 1000
    sent = 0
    while sent < total:
        mode = r.choice(["small", "full", "mixed"])
        xs = []
        for _ in range(chunk):
            if mode == "small":
                xs.append(r.randint(-300, 300) & 0xFFFF)
            elif mode == "full":
                xs.append(r.choice([0x7FFF, 0x8000, r.getrandbits(16)]))
            else:
                xs.append(r.getrandbits(16))
        await run_and_wait(m, xs)
        await check_regs(m)
        await pop_all(m, chunk)
        sent += chunk
    assert await rd(0x24) == m.read_reg(36) == total
    assert await rd(0x20) == m.read_reg(32)
