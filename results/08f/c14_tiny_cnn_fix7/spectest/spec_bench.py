import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

import spec_ref

DEB = 8
CPB = 16
PARAMS = {"DEBOUNCE_CYCLES": DEB, "CLKS_PER_BIT": CPB}
SEEDS = (1,)

SEGNAMES = "abcdefg"
TIMEOUT = 400000


def _val(sig):
    try:
        return int(sig.value)
    except Exception:
        return None


def read_display(dut):
    """Return (an0_enabled, set of lit segments)."""
    an = _val(dut.AN)
    segs = [dut.CA, dut.CB, dut.CC, dut.CD, dut.CE, dut.CF, dut.CG]
    lit = set()
    for n, s in zip(SEGNAMES, segs):
        v = _val(s)
        if v is None:
            return None, None
        if v == 0:  # cathodes are active low
            lit.add(n)
    return an, lit


async def uart_monitor(dut, out):
    while True:
        await FallingEdge(dut.UART_RXD_OUT)
        await ClockCycles(dut.CLK100MHZ, CPB // 2)
        if _val(dut.UART_RXD_OUT) != 0:
            continue
        byte = 0
        for i in range(8):
            await ClockCycles(dut.CLK100MHZ, CPB)
            byte |= (_val(dut.UART_RXD_OUT) or 0) << i  # least significant bit first
        await ClockCycles(dut.CLK100MHZ, CPB)
        stop = _val(dut.UART_RXD_OUT)
        out.append((byte, stop))


async def setup(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, units="ns").start())
    dut.CPU_RESETN.value = 0
    dut.BTNC.value = 0
    dut.SW.value = 0
    if hasattr(dut, "UART_TXD_IN"):
        dut.UART_TXD_IN.value = 1
    await ClockCycles(dut.CLK100MHZ, 5)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 5)
    got = []
    cocotb.start_soon(uart_monitor(dut, got))
    return got


async def press(dut, hold):
    dut.BTNC.value = 1
    await ClockCycles(dut.CLK100MHZ, hold)
    dut.BTNC.value = 0
    await ClockCycles(dut.CLK100MHZ, DEB + 4)


async def wait_two(dut, got, n_before):
    for _ in range(TIMEOUT // 100):
        if len(got) >= n_before + 2:
            return True
        await ClockCycles(dut.CLK100MHZ, 100)
    return False


async def run_picture(dut, got, pic, swhigh=0):
    cls, letter = spec_ref.expected(pic)
    n0 = len(got)
    dut.SW.value = (swhigh << 3) | pic  # SW0..SW2 choose the picture
    await ClockCycles(dut.CLK100MHZ, 3)
    await press(dut, 3 * DEB)
    ok = await wait_two(dut, got, n0)
    assert ok, f"picture {pic}: expected letter {chr(letter)} then line feed on serial, design sent {got[n0:]}"
    b0, s0 = got[n0]
    b1, s1 = got[n0 + 1]
    assert b0 == letter and s0 == 1, (
        f"picture {pic}: expected letter {chr(letter)} (class {cls}) 8N1 with stop bit 1, got 0x{b0:02x} stop={s0}")
    assert b1 == 0x0A and s1 == 1, f"picture {pic}: expected line feed 0x0A after the letter, got 0x{b1:02x}"
    await ClockCycles(dut.CLK100MHZ, 4 * CPB)
    an, lit = read_display(dut)
    assert an == 0xFE, f"picture {pic}: expected AN=0xFE (right-hand digit only), got {an}"
    assert lit == spec_ref.DIGIT_SEGS[cls], (
        f"picture {pic}: expected digit {cls} (segments {sorted(spec_ref.DIGIT_SEGS[cls])}), "
        f"display shows {sorted(lit) if lit is not None else None}")
    await ClockCycles(dut.CLK100MHZ, 40 * CPB)
    assert len(got) == n0 + 2, f"picture {pic}: expected exactly one letter and a line feed per press, saw {got[n0:]}"


@cocotb.test()
async def idle_blank_display_and_quiet_serial_after_reset(dut):
    got = await setup(dut)
    assert _val(dut.UART_RXD_OUT) == 1, "expected serial line idle high after reset"
    await ClockCycles(dut.CLK100MHZ, 50 * CPB)
    assert not got, f"expected nothing sent before any button press, got {got}"
    an, lit = read_display(dut)
    assert an is not None, "AN unknown after reset"
    assert (an & 1) == 1 or lit == set(), (
        f"expected right-hand digit blank before the first answer, AN={an:#x} lit={sorted(lit)}")


@cocotb.test()
async def all_eight_pictures_letter_and_digit_in_order(dut):
    got = await setup(dut)
    for pic in range(8):
        await run_picture(dut, got, pic)


@cocotb.test()
async def all_eight_pictures_reverse_order_ignoring_other_switches(dut):
    got = await setup(dut)
    rnd = random.Random(7)
    for pic in reversed(range(8)):
        # only SW0..SW2 choose the picture; the other switches must not matter
        await run_picture(dut, got, pic, swhigh=rnd.randrange(0, 1 << 13))


@cocotb.test()
async def short_button_glitch_is_debounced_away(dut):
    got = await setup(dut)
    dut.SW.value = 1
    for _ in range(3):
        dut.BTNC.value = 1
        await ClockCycles(dut.CLK100MHZ, max(1, DEB // 2))
        dut.BTNC.value = 0
        await ClockCycles(dut.CLK100MHZ, 30)
    await ClockCycles(dut.CLK100MHZ, 3000)
    assert not got, f"expected a button blip shorter than DEBOUNCE_CYCLES to be ignored, design sent {got}"
    # a real, bouncy-then-stable press still works
    cls, letter = spec_ref.expected(1)
    dut.BTNC.value = 1
    await ClockCycles(dut.CLK100MHZ, 2)
    dut.BTNC.value = 0
    await ClockCycles(dut.CLK100MHZ, 2)
    await press(dut, 4 * DEB)
    ok = await wait_two(dut, got, 0)
    assert ok, "expected the stable press to classify picture 1"
    assert got[0][0] == letter, f"picture 1: expected {chr(letter)}, got 0x{got[0][0]:02x}"
