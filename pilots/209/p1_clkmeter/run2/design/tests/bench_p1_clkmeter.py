import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ClockCycles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

PARAMS = dict(GATE_LEN_DEFAULT=2000,
              LED_HALF_PERIOD_C3_CYCLES=16,
              LED_HALF_PERIOD_REF_CYCLES=125)
GATE_MIN = 1000
ID = 546373633

R_ID, R_BUILD, R_SCR, R_GL, R_CTRL, R_ST, R_CNT, R_GA, R_MD = 0, 4, 8, 16, 20, 24, 28, 32, 36


def new_model():
    return model.Model(**PARAMS)


async def start_clocks(dut):
    cocotb.start_soon(Clock(dut.clk, 6400, "ps").start())
    cocotb.start_soon(Clock(dut.c3_clk, 40000, "ps").start())


async def reset(dut):
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 3)
    await FallingEdge(dut.clk)


async def setup(dut):
    await start_clocks(dut)
    await reset(dut)
    return new_model()


async def wr(dut, addr, val):
    await FallingEdge(dut.clk)
    dut.h_we.value = 1
    dut.h_addr.value = addr
    dut.h_wdata.value = val
    await FallingEdge(dut.clk)
    dut.h_we.value = 0


async def rd(dut, addr):
    await FallingEdge(dut.clk)
    dut.h_re.value = 1
    dut.h_addr.value = addr
    await FallingEdge(dut.clk)
    dut.h_re.value = 0
    await FallingEdge(dut.clk)
    v = int(dut.h_rdata.value)
    if hasattr(dut, "sfp_tx_disable"):
        assert int(dut.sfp_tx_disable.value) == 1
    return v


async def chk(dut, m, addr, tol=0):
    got = await rd(dut, addr)
    exp = m.read_reg(addr)
    assert abs(got - exp) <= tol, f"reg 0x{addr:x}: got {got:#x} exp {exp:#x}"
    return got


async def measure(dut, m, gate_reg=None):
    """Start a measurement on RTL and model, wait for it, compare."""
    await wr(dut, R_CTRL, 1 | (m.led_en << 1))
    m.write_reg(R_CTRL, 1 | (m.led_en << 1))
    glat = max(m.gate_len, GATE_MIN)
    n = glat + 40
    await ClockCycles(dut.clk, n)
    for _ in range(n):
        m.step()
    await chk(dut, m, R_ST)
    await chk(dut, m, R_GA)
    await chk(dut, m, R_MD)
    got = await chk(dut, m, R_CNT, tol=2)
    ideal = glat * 4 / 25
    assert abs(got - ideal) <= 2, f"count {got} vs ideal {ideal}"


# req: REQ-01, REQ-23, REQ-04, REQ-12, REQ-24, REQ-15, REQ-10
@cocotb.test()
async def test_reset_values(dut):
    m = await setup(dut)
    assert await rd(dut, R_ID) == 0x20910001
    for a in (R_ID, R_SCR, R_GL, R_CTRL, R_ST, R_CNT, R_GA, R_MD):
        await chk(dut, m, a)
    assert await rd(dut, R_SCR) == 0
    assert await rd(dut, R_GL) == PARAMS["GATE_LEN_DEFAULT"]
    assert (await rd(dut, R_CTRL)) & 2 == 0
    assert int(dut.led.value) == 0
    await rd(dut, R_BUILD)
    for _ in range(50):
        await FallingEdge(dut.clk)
        assert int(dut.led.value) == 0


# req: REQ-03, REQ-19, REQ-18, REQ-26, REQ-17, REQ-25, REQ-01
@cocotb.test()
async def test_register_port(dut):
    m = await setup(dut)
    for v in (0xFFFFFFFF, 0x12345678, 0, 0xA5A5A5A5, 1):
        await wr(dut, R_SCR, v)
        m.write_reg(R_SCR, v)
        # read issued the clock right after h_we sees the new value
        await chk(dut, m, R_SCR)
    await wr(dut, R_SCR, 0xCAFEF00D)
    m.write_reg(R_SCR, 0xCAFEF00D)
    # RO writes ignored
    for a in (R_ID, R_BUILD, R_ST, R_CNT, R_GA, R_MD):
        before = await rd(dut, a)
        await wr(dut, a, 0xDEADBEEF)
        assert await rd(dut, a) == before
    assert await rd(dut, R_ID) == 0x20910001
    # unmapped addresses read 0 and ignore writes
    for a in (0x00C, 0x02C, 0x030, 0x100, 0x400, 0x800, 0xFFC):
        assert await rd(dut, a) == 0
        await wr(dut, a, 0xFFFFFFFF)
        assert await rd(dut, a) == 0
    await chk(dut, m, R_SCR)
    await chk(dut, m, R_GL)
    await chk(dut, m, R_CTRL)
    # hold: value stays until next h_re even if address changes
    await FallingEdge(dut.clk)
    dut.h_re.value = 1
    dut.h_addr.value = R_SCR
    await FallingEdge(dut.clk)
    dut.h_re.value = 0
    dut.h_addr.value = R_GL
    await FallingEdge(dut.clk)
    for _ in range(6):
        assert int(dut.h_rdata.value) == 0xCAFEF00D
        await FallingEdge(dut.clk)
    # reset restores scratch
    await reset(dut)
    m.reset()
    await chk(dut, m, R_SCR)


# req: REQ-07, REQ-09, REQ-05, REQ-06, REQ-10, REQ-04
@cocotb.test()
async def test_measurement_basic(dut):
    m = await setup(dut)
    await measure(dut, m)
    assert await rd(dut, R_ST) == 2
    assert await rd(dut, R_GA) == PARAMS["GATE_LEN_DEFAULT"]
    assert await rd(dut, R_MD) == 1
    # second start: BUSY=1, DONE=0 on the very next clock; COUNT holds old value
    old = await rd(dut, R_CNT)
    await wr(dut, R_CTRL, 1)
    m.write_reg(R_CTRL, 1)
    assert await rd(dut, R_ST) == 1
    assert await rd(dut, R_CNT) == old
    assert await rd(dut, R_GA) == PARAMS["GATE_LEN_DEFAULT"]
    # START always reads 0
    assert (await rd(dut, R_CTRL)) & 1 == 0
    await ClockCycles(dut.clk, PARAMS["GATE_LEN_DEFAULT"] + 40)
    for _ in range(PARAMS["GATE_LEN_DEFAULT"] + 40 + 10):
        m.step()
    await chk(dut, m, R_ST)
    await chk(dut, m, R_MD)
    assert await rd(dut, R_MD) == 2
    await chk(dut, m, R_CNT, tol=2)
    assert (await rd(dut, R_CTRL)) & 1 == 0


# req: REQ-08, REQ-05, REQ-09, REQ-07
@cocotb.test()
async def test_start_while_busy(dut):
    m = await setup(dut)
    await wr(dut, R_GL, 1200)
    m.write_reg(R_GL, 1200)
    await wr(dut, R_CTRL, 1)
    m.write_reg(R_CTRL, 1)
    await ClockCycles(dut.clk, 400)
    for _ in range(400 + 10):
        m.step()
    # START while busy and GATE_LEN change while busy: ignored by running gate
    await wr(dut, R_CTRL, 1)
    m.write_reg(R_CTRL, 1)
    await wr(dut, R_GL, 5000)
    m.write_reg(R_GL, 5000)
    assert await rd(dut, R_ST) == 1
    await ClockCycles(dut.clk, 500)
    for _ in range(500):
        m.step()
    assert await rd(dut, R_ST) == 1  # ~920 cycles in, gate 1200
    await ClockCycles(dut.clk, 1200 - 920 + 40)
    for _ in range(1200 - 920 + 40):
        m.step()
    await chk(dut, m, R_ST)
    assert await rd(dut, R_ST) == 2
    assert await rd(dut, R_GA) == 1200
    assert await rd(dut, R_MD) == 1
    assert await rd(dut, R_GL) == 5000
    await ClockCycles(dut.clk, 300)
    assert await rd(dut, R_MD) == 1  # no second measurement was started
    assert await rd(dut, R_ST) == 2


# req: REQ-11, REQ-05, REQ-06
@cocotb.test()
async def test_gate_clamp(dut):
    m = await setup(dut)
    for gl in (5, 999, 1000, 1001):
        await wr(dut, R_GL, gl)
        m.write_reg(R_GL, gl)
        assert await rd(dut, R_GL) == gl
        await wr(dut, R_CTRL, 1)
        m.write_reg(R_CTRL, 1)
        await ClockCycles(dut.clk, 800)
        for _ in range(800):
            m.step()
        assert await rd(dut, R_ST) == 1  # still within 1000-cycle gate
        await ClockCycles(dut.clk, 400)
        for _ in range(400):
            m.step()
        await chk(dut, m, R_ST)
        await chk(dut, m, R_GA)
        await chk(dut, m, R_MD)
        await chk(dut, m, R_CNT, tol=2)
        assert await rd(dut, R_GA) == max(gl, GATE_MIN)
        assert await rd(dut, R_GL) == gl


# req: REQ-12, REQ-24, REQ-13, REQ-14
@cocotb.test()
async def test_leds(dut):
    m = await setup(dut)
    assert int(dut.led.value) == 0
    await wr(dut, R_CTRL, 2)
    m.write_reg(R_CTRL, 2)
    assert (await rd(dut, R_CTRL)) == 2
    prev = None
    last = [None, None]
    ivals = [[], []]
    nsamp = 125 * 6 + 40
    for i in range(nsamp):
        await FallingEdge(dut.clk)
        v = int(dut.led.value)
        if prev is not None:
            for b in (0, 1):
                if ((v ^ prev) >> b) & 1:
                    if last[b] is not None:
                        ivals[b].append(i - last[b])
                    last[b] = i
        prev = v
    assert len(ivals[1]) >= 4, ivals
    assert all(x == PARAMS["LED_HALF_PERIOD_REF_CYCLES"] for x in ivals[1]), ivals
    exp0 = PARAMS["LED_HALF_PERIOD_C3_CYCLES"] * 25 / 4  # ref cycles
    assert len(ivals[0]) >= 4, ivals
    assert all(abs(x - exp0) <= 1 for x in ivals[0]), ivals
    # LED_EN=0 forces both LEDs low
    await wr(dut, R_CTRL, 0)
    await ClockCycles(dut.clk, 4)
    for _ in range(300):
        await FallingEdge(dut.clk)
        assert int(dut.led.value) == 0
    # LED_EN survives a START write that sets it
    await wr(dut, R_CTRL, 3)
    assert (await rd(dut, R_CTRL)) == 2
    await ClockCycles(dut.clk, 20)
    # reset clears LED_EN
    await reset(dut)
    assert int(dut.led.value) == 0
    assert (await rd(dut, R_CTRL)) == 0


# req: REQ-15, REQ-18, REQ-17
@cocotb.test()
async def test_sfp_tx_disable(dut):
    await setup(dut)
    if hasattr(dut, "sfp_tx_disable"):
        for _ in range(100):
            await FallingEdge(dut.clk)
            assert int(dut.sfp_tx_disable.value) == 1
        dut.rst.value = 1
        await FallingEdge(dut.clk)
        assert int(dut.sfp_tx_disable.value) == 1
        dut.rst.value = 0


# req: REQ-03, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-17, REQ-18, REQ-25, REQ-26, REQ-19, REQ-12, REQ-24
@cocotb.test()
async def test_random_traffic(dut):
    seed = int(os.environ.get("RANDOM_SEED", getattr(cocotb, "RANDOM_SEED", 1)))
    rng = random.Random(seed)
    m = await setup(dut)
    vals = (0, 1, 0xFFFFFFFF)

    def rv():
        c = rng.randrange(4)
        return vals[c] if c < 3 else rng.getrandbits(32)

    nmeas = 0
    for _ in range(60):
        op = rng.choice(["scr", "scr", "unm", "ro", "gl", "led", "meas", "rd"])
        if op == "scr":
            v = rv()
            await wr(dut, R_SCR, v)
            m.write_reg(R_SCR, v)
            await chk(dut, m, R_SCR)
        elif op == "unm":
            a = rng.choice([0x00C, 0x02C, 0x040, 0x1F0, 0x7FC, 0xFF0])
            await wr(dut, a, rv())
            assert await rd(dut, a) == 0
        elif op == "ro":
            a = rng.choice([R_ID, R_BUILD, R_ST, R_CNT, R_GA, R_MD])
            before = await rd(dut, a)
            await wr(dut, a, rv())
            assert await rd(dut, a) == before
        elif op == "gl":
            v = rng.choice([0, 1, 999, 1000, 1001, 1100, 1500, 3000, rng.randrange(1000)])
            await wr(dut, R_GL, v)
            m.write_reg(R_GL, v)
            await chk(dut, m, R_GL)
        elif op == "led":
            v = rng.choice([0, 2])
            await wr(dut, R_CTRL, v)
            m.write_reg(R_CTRL, v)
            await chk(dut, m, R_CTRL)
        elif op == "meas" and nmeas < 5:
            nmeas += 1
            if m.gate_len > 3000:
                await wr(dut, R_GL, 1000)
                m.write_reg(R_GL, 1000)
            await measure(dut, m)
        else:
            a = rng.choice([R_ID, R_SCR, R_GL, R_CTRL, R_ST, R_GA, R_MD])
            await chk(dut, m, a)
    for a in (R_ID, R_SCR, R_GL, R_CTRL, R_ST, R_GA, R_MD):
        await chk(dut, m, a)
