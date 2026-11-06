"""Acceptance tests of c14_nexys_tiny_cnn against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek, seg_pins
from cocotb.triggers import ClockCycles
from model import LETTERS, SEG_OF, forward, load


def expected():
    w, b, cfg, imgs = load()
    out = []
    for k in range(8):
        lg = forward(imgs[k], w, b, cfg)
        cls = max(range(4), key=lambda i: (lg[i], -i))          # the lowest index wins a tie
        out.append(cls)
    return out


async def press(b: Board, k: int, what: str) -> None:
    dut = b.dut
    dut.SW.value = k
    await ClockCycles(b.clk, 5)
    dut.BTNC.value = 1
    await ClockCycles(b.clk, 60)
    dut.BTNC.value = 0
    cls = EXP[k]
    got = await b.uart.recv(2, 60_000)
    assert got == (LETTERS[cls] + "\n").encode(), f"{what}: picture {k}: UART {got!r}, expected {LETTERS[cls]!r} + LF"
    await ClockCycles(b.clk, 40)
    seg = seg_pins(dut)
    assert seg == SEG_OF[cls], f"{what}: picture {k}: display segments 0x{seg:02X}, expected 0x{SEG_OF[cls]:02X} (digit {cls})"
    assert int(dut.AN.value) == 0xFE, f"{what}: only the right-hand digit may be lit (AN=0x{int(dut.AN.value):02X})"
    await ClockCycles(b.clk, 100)


EXP = expected()


async def boot(dut) -> Board:
    b = Board(dut, {"BTNC": 0, "SW": 0})
    await b.start()
    await b.cycles(1500)                  # the reference loads its parameter memories after reset
    return b


@cocotb.test()
async def test_blank_before_first_answer(dut):
    b = await boot(dut)
    seg = seg_pins(dut)
    assert seg == 0x7F, f"display must be blank before the first answer (segments 0x{seg:02X})"
    await b.uart.expect_silence(2000)


@cocotb.test()
async def test_pictures_0_to_3(dut):
    b = await boot(dut)
    for k in range(4):
        await press(b, k, "first half")


@cocotb.test()
async def test_pictures_4_to_7(dut):
    b = await boot(dut)
    for k in range(4, 8):
        await press(b, k, "second half")


@cocotb.test()
async def test_glitch_is_not_a_press(dut):
    """A button pulse shorter than the debounce time starts nothing."""
    b = await boot(dut)
    dut.SW.value = 2
    dut.BTNC.value = 1
    await ClockCycles(b.clk, 6)
    dut.BTNC.value = 0
    await b.uart.expect_silence(3000)
    await press(b, 5, "after a glitch")


@cocotb.test()
async def test_reset_blanks_the_display(dut):
    b = await boot(dut)
    await press(b, 1, "before reset")
    await b.reset()
    await b.cycles(20)
    assert seg_pins(dut) == 0x7F, "reset must blank the display"
