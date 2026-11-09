import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p

import spec_ref as m

CPB = 8
PARAMS = {"CLKS_PER_BIT": CPB, "TIMEOUT_CYCLES": 4000, "BUILD_STAMP": 0}
SEEDS = (1,)


async def start(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, units="ns").start())
    dut.CPU_RESETN.value = 0
    dut.UART_TXD_IN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)
    return UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, CPB)


async def reset(dut):
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)


async def wr(bfm, addr, val):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_WRITE, addr, val & 0xFFFFFFFF)))
    assert r.status == p.ST_OK, f"write 0x{addr:02X}: expected OK, got {r.status_name}"


async def rd(bfm, addr):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_READ, addr)))
    assert r.status == p.ST_OK, f"read 0x{addr:02X}: expected OK, got {r.status_name}"
    return r.data


async def run(bfm, a, w, bias, mult, shift, relu):
    await wr(bfm, m.A_LO, m.pack8(a[:4]))
    await wr(bfm, m.A_HI, m.pack8(a[4:]))
    await wr(bfm, m.W_LO, m.pack8(w[:4]))
    await wr(bfm, m.W_HI, m.pack8(w[4:]))
    await wr(bfm, m.BIAS, bias)
    await wr(bfm, m.MULT, mult)
    await wr(bfm, m.CTRL, (relu << 8) | shift)
    await wr(bfm, m.GO, 1)
    for _ in range(20):
        if (await rd(bfm, m.STATUS)) & 1:
            break
    else:
        assert False, "READY (STATUS[0]) never became 1 after GO"
    y = await rd(bfm, m.Y)
    acc = await rd(bfm, m.ACC)
    ey, eacc = m.compute(a, w, bias, mult, shift, relu)
    desc = f"a={a} w={w} bias={bias} mult={mult} shift={shift} relu={relu}"
    assert m.s32(acc) == eacc, f"ACC expected {eacc} (signed 32-bit), got {m.s32(acc)}; {desc}"
    assert m.s8(y) == ey, f"Y expected {ey} (signed 8-bit), got {m.s8(y)}; {desc}"


def vec(a0=0, w0=0, **kw):
    a = [a0] + [0] * 7
    w = [w0] + [0] * 7
    return a, w


@cocotb.test()
async def reset_state_id_and_leds(dut):
    bfm = await start(dut)
    # "The design ID is DOTQ"; DESIGN_ID is four ASCII chars MSB first (PROTOCOL.md)
    assert await rd(bfm, p.REG_DESIGN_ID) == m.DESIGN_ID, "DESIGN_ID expected 'DOTQ' = 0x444F5451"
    # Q1: reset values A_LO 0, CTRL 1; READY 0
    assert await rd(bfm, m.A_LO) == 0, "A_LO reset value expected 0"
    assert await rd(bfm, m.CTRL) & 0x11F == 1, "CTRL reset value expected 1 (shift=1, relu=0)"
    assert await rd(bfm, m.STATUS) & 1 == 0, "READY expected 0 after reset"
    # Q5: Y and ACC read 0 while READY is 0
    assert await rd(bfm, m.Y) == 0, "Y expected 0 while READY=0"
    assert await rd(bfm, m.ACC) == 0, "ACC expected 0 while READY=0"
    # Q6 / LED0 shows ready
    assert int(dut.LED.value) == 0, f"LED expected all low while not ready, got {int(dut.LED.value):#x}"


@cocotb.test()
async def ready_led_and_reset_clears(dut):
    bfm = await start(dut)
    a = [3, -4, 5, 6, 7, 8, 9, 10]
    w = [1, 2, 3, 4, 5, 6, 7, 8]
    await run(bfm, a, w, 100, 3, 2, 0)
    await ClockCycles(dut.CLK100MHZ, 4)
    assert int(dut.LED.value) == 1, f"LED0 expected = READY(1) and LED[15:1] low, got {int(dut.LED.value):#x}"
    await wr(bfm, m.BIAS, 0x1234)
    assert await rd(bfm, m.BIAS) == 0x1234, "BIAS expected to read back what was written"
    await reset(dut)
    assert int(dut.LED.value) == 0, "LED0 expected 0 after CPU_RESETN (ready cleared)"
    assert await rd(bfm, m.STATUS) & 1 == 0, "READY expected cleared by CPU_RESETN"
    for reg, nm in ((m.A_LO, "A_LO"), (m.A_HI, "A_HI"), (m.W_LO, "W_LO"), (m.W_HI, "W_HI"),
                    (m.BIAS, "BIAS"), (m.MULT, "MULT")):
        assert await rd(bfm, reg) == 0, f"{nm} expected cleared by CPU_RESETN"
    assert await rd(bfm, m.ACC) == 0, "ACC expected 0 after reset"


@cocotb.test()
async def unused_window_registers_read_zero(dut):
    bfm = await start(dut)
    await wr(bfm, 0x8B, 0xFFFFFFFF)  # writes ignored
    assert await rd(bfm, 0x8B) == 0, "0x0B (window) expected to read 0, writes ignored"
    assert await rd(bfm, 0xFF) == 0, "0x7F (window) expected to read 0"
    await wr(bfm, m.MULT, 0xABCD)
    assert await rd(bfm, m.MULT) == 0xABCD, "MULT expected to read back 16 bits written"


@cocotb.test()
async def extreme_inputs_and_saturation(dut):
    bfm = await start(dut)
    # most positive products: -128 * -127 each; clamps to 127
    await run(bfm, [-128] * 8, [-127] * 8, 0, 1, 1, 0)
    # most negative products: -128 * 127; clamps to -128, relu gives 0
    await run(bfm, [-128] * 8, [127] * 8, 0, 1, 1, 0)
    await run(bfm, [-128] * 8, [127] * 8, 0, 1, 1, 1)
    await run(bfm, [127] * 8, [127] * 8, 0, 65535, 1, 0)
    # large bias without 32-bit overflow, extreme multiplier and shift
    await run(bfm, [127] * 8, [127] * 8, 2**31 - 1 - 129032, 65535, 31, 0)
    await run(bfm, [0] * 8, [0] * 8, -2**31, 1, 31, 0)   # exactly -1
    await run(bfm, [0] * 8, [0] * 8, -2**31, 65535, 1, 0)
    await run(bfm, [1] * 8, [1] * 8, 0, 0, 5, 0)          # mult 0


@cocotb.test()
async def exact_halves_round_up(dut):
    bfm = await start(dut)
    a, w = vec(5, 1)
    await run(bfm, a, w, 0, 1, 1, 0)      # 2.5 -> 3
    a, w = vec(-5, 1)
    await run(bfm, a, w, 0, 1, 1, 0)      # -2.5 -> -2
    await run(bfm, [0] * 8, [0] * 8, 2**30, 1, 31, 0)   # 0.5 -> 1
    await run(bfm, [0] * 8, [0] * 8, -2, 1, 2, 0)       # -0.5 -> 0
    await run(bfm, [0] * 8, [0] * 8, 2, 1, 2, 0)        # 0.5 -> 1
    await run(bfm, [0] * 8, [0] * 8, -3, 1, 2, 0)       # -0.75 -> -1
    await run(bfm, [0] * 8, [0] * 8, -1, 1, 1, 1)       # -0.5 -> 0 (relu)


@cocotb.test()
async def relu_switch(dut):
    bfm = await start(dut)
    a, w = vec(-7, 3)
    await run(bfm, a, w, 0, 1, 1, 0)   # -21/2 = -10.5 -> -10
    await run(bfm, a, w, 0, 1, 1, 1)   # relu -> 0
    a, w = vec(100, 100)
    await run(bfm, a, w, 0, 1, 1, 1)   # saturate to 127


@cocotb.test()
async def operand_lane_positions(dut):
    bfm = await start(dut)
    # each lane carries a distinct weight so that a lane swap changes acc
    a = [1, 2, 3, 4, 5, 6, 7, 8]
    w = [10, -20, 30, -40, 50, -60, 70, -80]
    await run(bfm, a, w, 7, 1, 1, 0)
    a = [-1, 2, -3, 4, -5, 6, -7, 8]
    w = [127, 1, -127, 2, 3, -3, 5, 100]
    await run(bfm, a, w, -9, 1, 1, 0)


@cocotb.test()
async def random_vectors(dut, seed=None):
    bfm = await start(dut)
    rng = random.Random(1234)
    for _ in range(6):
        a = [rng.randint(-128, 127) for _ in range(8)]
        w = [rng.randint(-127, 127) for _ in range(8)]
        bias = rng.randint(-5000, 5000)
        shift = rng.randint(1, 31)
        mult = rng.randint(0, min(65535, 2 ** (shift - 1) if shift < 17 else 65535))
        await run(bfm, a, w, bias, mult, shift, rng.randint(0, 1))


@cocotb.test()
async def new_go_replaces_result(dut):
    bfm = await start(dut)
    a, w = vec(10, 10)
    await run(bfm, a, w, 0, 1, 1, 0)    # 50
    a, w = vec(-3, 4)
    await run(bfm, a, w, 0, 1, 1, 0)    # second GO gives the new result
