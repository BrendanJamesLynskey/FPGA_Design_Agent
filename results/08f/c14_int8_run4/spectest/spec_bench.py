import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

import spec_ref as R
from shell.host import protocol as p
from shell.tests.uart_bfm import UartBfm

CPB = 10
PARAMS = {"CLKS_PER_BIT": CPB, "TIMEOUT_CYCLES": 600}
SEEDS = (1,)


class Env:
    pass


async def setup(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, units="ns").start())
    dut.UART_TXD_IN.value = 1
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)
    e = Env()
    e.dut = dut
    e.bfm = UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, CPB)
    e.cache = {}
    return e


def led0(dut):
    return int(dut.LED.value) & 1


async def xact(e, cmd, addr, data=0):
    raw = await e.bfm.transact(p.encode_request(cmd, addr, data))
    return p.decode_response(raw)


async def wr(e, off, val):
    r = await xact(e, p.CMD_WRITE, R.WINDOW + off, val & 0xFFFFFFFF)
    assert r.ok, f"write to window offset {off:#x} should be OK, got {r.status_name}"
    return r


async def rd(e, off):
    r = await xact(e, p.CMD_READ, R.WINDOW + off)
    assert r.ok, f"read of window offset {off:#x} should be OK, got {r.status_name}"
    return r.data


async def run_vec(e, a, w, bias, mult, shift, relu, tag=""):
    words = {
        R.A_LO: R.pack(a[:4]), R.A_HI: R.pack(a[4:]),
        R.W_LO: R.pack(w[:4]), R.W_HI: R.pack(w[4:]),
        R.BIAS: bias & 0xFFFFFFFF, R.MULT: mult,
        R.CTRL: R.ctrl_word(shift, relu),
    }
    for off, v in words.items():
        if e.cache.get(off) != v:
            await wr(e, off, v)
            e.cache[off] = v
    await wr(e, R.GO, 1)
    await ClockCycles(e.dut.CLK100MHZ, 5)
    assert led0(e.dut) == 1, f"{tag}: LED0 (ready) should be 1 after GO completes, got 0"
    y = await rd(e, R.Y)
    acc = await rd(e, R.ACC)
    ey, eacc = R.compute(a, w, bias, mult, shift, relu)
    assert acc == eacc & 0xFFFFFFFF, (
        f"{tag}: acc expected {eacc} (sum of products + bias), got {acc:#x}")
    assert (y & 0xFF) == (ey & 0xFF), (
        f"{tag}: y expected {ey} (acc={eacc}, mult={mult}, shift={shift}, relu={relu}), "
        f"got {y & 0xFF:#04x}")


@cocotb.test()
async def reset_state_id_and_zero_reads(dut):
    e = await setup(dut)
    r = await xact(e, p.CMD_READ, p.REG_DESIGN_ID)
    assert r.ok and r.data == R.DESIGN_ID, f"design ID expected 'DOTQ' 0x444F5451, got {r.data:#x}"
    assert led0(dut) == 0, "LED0 shows ready flag: expected 0 after reset"
    for off in (R.A_LO, R.A_HI, R.W_LO, R.W_HI, R.BIAS, R.MULT):
        assert await rd(e, off) == 0, f"register {off:#x} expected reset value 0"
    assert await rd(e, R.CTRL) == 1, "CTRL reset value expected 1"
    assert await rd(e, R.Y) == 0, "Y expected 0 while READY is 0"
    assert await rd(e, R.ACC) == 0, "ACC expected 0 while READY is 0"
    for off in (0x0B, 0x40, 0x7F):
        assert await rd(e, off) == 0, f"offset {off:#x} (0x0B-0x7F) expected to read 0"


@cocotb.test()
async def registers_read_back(dut):
    e = await setup(dut)
    vals = {R.A_LO: 0x80FF7F01, R.A_HI: 0x12345678, R.W_LO: 0x7F817F01,
            R.W_HI: 0xDEADBEEF, R.BIAS: 0x80000001, R.MULT: 0xFFFF,
            R.CTRL: R.ctrl_word(31, 1)}
    for off, v in vals.items():
        await wr(e, off, v)
    for off, v in vals.items():
        got = await rd(e, off)
        assert got == v, f"register {off:#x} expected read-back {v:#x}, got {got:#x}"


@cocotb.test()
async def extreme_inputs_dot_product(dut):
    e = await setup(dut)
    cases = [
        ([-128] * 8, [-127] * 8, 0),
        ([-128] * 8, [127] * 8, 0),
        ([127] * 8, [127] * 8, 0),
        ([127] * 8, [-127] * 8, 0),
        ([-128, 127, -1, 0, 1, -128, 127, 5], [127, -127, -127, 99, -3, 127, 127, -127], -7),
    ]
    for i, (a, w, b) in enumerate(cases):
        await run_vec(e, a, w, b, 1, 1, 0, f"extreme{i}")
        # y limited, acc exact
        await run_vec(e, a, w, b, 1, 31, 0, f"extreme{i}_s31")


@cocotb.test()
async def rounding_exact_halves_go_up(dut):
    e = await setup(dut)
    z = [0] * 8
    # mult/2^shift = 1/2: acc 5 -> 2.5 -> 3, -5 -> -2.5 -> -2
    for acc in (5, -5, 4, -4, 3, -3, 1, -1, 0):
        await run_vec(e, z, z, acc, 1, 1, 0, f"half_acc{acc}")
    # shift 3, mult 3: acc*3/8, halves e.g. acc=4 -> 1.5, acc=-4 -> -1.5, acc=12 -> 4.5
    for acc in (4, -4, 12, -12, 20, -20, 7, -7):
        await run_vec(e, z, z, acc, 3, 3, 0, f"half3_acc{acc}")
    # relu with negative half: -0.5 -> 0 (round up), result limited at 0
    await run_vec(e, z, z, -1, 1, 1, 1, "relu_neg_half")


@cocotb.test()
async def limiting_both_ends_and_relu(dut):
    e = await setup(dut)
    z = [0] * 8
    for relu in (0, 1):
        for acc in (127, 128, 1000, -127, -128, -129, -1000, 100000, -100000):
            await run_vec(e, z, z, acc, 1, 1, relu, f"clamp_relu{relu}_acc{acc}")
            await run_vec(e, z, z, acc, 2, 1, relu, f"clamp_x1_relu{relu}_acc{acc}")


@cocotb.test()
async def large_bias_and_wide_scaling(dut):
    e = await setup(dut)
    a = [-128] * 8
    w = [127] * 8
    sum_p = -128 * 127 * 8
    # keep acc within 32 bits (the request defines no overflow)
    hi_bias = (2**31 - 1) + 0 - 0
    cases = [
        (hi_bias - 130048, [127] * 8, [127] * 8, 65535, 31),
        (-(2**31) - sum_p, a, w, 65535, 31),
        (-(2**31), [0] * 8, [0] * 8, 65535, 31),
        (2**31 - 1, [0] * 8, [0] * 8, 65535, 16),
        (2**31 - 1, [0] * 8, [0] * 8, 1, 31),
        (-(2**31), [0] * 8, [0] * 8, 1, 31),
        (2**30, [0] * 8, [0] * 8, 1, 23),
        (2**30, [0] * 8, [0] * 8, 1, 24),
        (-(2**30), [0] * 8, [0] * 8, 1, 24),
        (2**30 + 2**22, [0] * 8, [0] * 8, 1, 23),
    ]
    for i, (b, aa, ww, m, s) in enumerate(cases):
        for relu in (0, 1):
            await run_vec(e, aa, ww, b, m, s, relu, f"big{i}_relu{relu}")


@cocotb.test()
async def random_vectors_match_model(dut):
    e = await setup(dut)
    rng = random.Random(1234)
    for i in range(12):
        a = [rng.randint(-128, 127) for _ in range(8)]
        w = [rng.randint(-127, 127) for _ in range(8)]
        shift = rng.randint(1, 31)
        mult = rng.randint(0, 65535)
        bias = rng.randint(-200000, 200000) if i % 2 else rng.randint(-2**30, 2**30)
        # aim result near the output range so it is not always limited
        if i % 3 == 0:
            shift = rng.randint(1, 16)
            mult = max(1, min(65535, (127 << shift) // max(1, abs(sum(x * y for x, y in zip(a, w)) + bias) or 1)))
        await run_vec(e, a, w, bias, mult, shift, rng.randint(0, 1), f"rand{i}")


@cocotb.test()
async def results_hold_and_ready_timing(dut):
    e = await setup(dut)
    a = [3, -5, 7, 9, -11, 13, 15, -17]
    w = [2, 4, -6, 8, 10, -12, 14, 16]
    await run_vec(e, a, w, 100, 1, 1, 0, "first")
    ey, eacc = R.compute(a, w, 100, 1, 1, 0)
    # Change inputs without GO: Y and ACC must hold
    await wr(e, R.BIAS, 5000)
    await wr(e, R.CTRL, R.ctrl_word(3, 1))
    e.cache.clear()
    assert (await rd(e, R.Y)) & 0xFF == ey & 0xFF, "Y expected to hold until next GO"
    assert await rd(e, R.ACC) == eacc & 0xFFFFFFFF, "ACC expected to hold until next GO"
    assert led0(dut) == 1, "LED0 expected to stay 1 until next GO"
    # Ready after GO within 8 clocks: low run on LED0 during the GO frame
    state = {"run": 0, "max": 0}

    async def mon():
        while True:
            await RisingEdge(dut.CLK100MHZ)
            if led0(dut) == 0:
                state["run"] += 1
                state["max"] = max(state["max"], state["run"])
            else:
                state["run"] = 0

    t = cocotb.start_soon(mon())
    await wr(e, R.GO, 1)
    await ClockCycles(dut.CLK100MHZ, 20)
    t.cancel()
    assert state["max"] <= 9, f"READY expected back to 1 within 8 clocks of GO, LED0 low for {state['max']} clocks"
    assert led0(dut) == 1, "LED0 expected 1 after GO"
    ey, eacc = R.compute(a, w, 5000, 1, 3, 1)
    assert await rd(e, R.ACC) == eacc & 0xFFFFFFFF, "ACC after new GO should use the newly loaded bias"
    assert (await rd(e, R.Y)) & 0xFF == ey & 0xFF, "Y after new GO should use the newly loaded ctrl"


@cocotb.test()
async def reset_clears_loaded_numbers_and_ready(dut):
    e = await setup(dut)
    a = [1] * 8
    await run_vec(e, a, a, 3, 1, 1, 0, "pre_reset")
    assert led0(dut) == 1
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)
    assert led0(dut) == 0, "CPU_RESETN expected to clear the ready flag (LED0)"
    for off in (R.A_LO, R.A_HI, R.W_LO, R.W_HI, R.BIAS, R.MULT, R.Y, R.ACC):
        assert await rd(e, off) == 0, f"register {off:#x} expected 0 after CPU_RESETN"
    assert await rd(e, R.CTRL) == 1, "CTRL expected reset value 1 after CPU_RESETN"
