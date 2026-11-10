"""Acceptance tests of t1_press_classifier against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import DESIGN_ID, LAST, LONG_COUNT, SHORT_COUNT, STATUS, Model

IDLE = {"BTNC": 0}
NAMES = ("SHORT_COUNT", "LONG_COUNT", "LAST", "STATUS")


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, IDLE)
        self.dut = dut
        self.n = self.b.param("DEBOUNCE_CYCLES")
        self.long = self.b.param("LONG_CYCLES")
        self.tick = self.b.param("TICK_CYCLES")
        self.m = Model(self.long, self.tick)

    async def start(self) -> None:
        await self.b.start()

    async def press(self, h: int) -> None:
        """A clean press: BTNC high for exactly h clocks."""
        self.dut.BTNC.value = 1
        await self.b.cycles(h)
        self.dut.BTNC.value = 0
        await self.b.cycles(self.n + 6)
        self.m.press(h)

    async def check_regs(self) -> None:
        for off in (SHORT_COUNT, LONG_COUNT, LAST, STATUS):
            await self.b.expect(off, self.m.read(off), NAMES[off])

    async def check_leds(self) -> None:
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_short_presses(dut):
    e = Env(dut)
    await e.start()
    for h in (e.n + 2, 40, 100, e.long // 2 + 1):
        await e.press(h)
        await e.check_regs()
        await e.check_leds()


@cocotb.test()
async def test_long_press_not_short(dut):
    """Trap: the textbook button-press counter counts every press; a long press here must never count as SHORT."""
    e = Env(dut)
    await e.start()
    for h in (e.long + 50, 2 * e.long + 1, e.long + 7):
        await e.press(h)
        await e.check_regs()
        await e.check_leds()
    await e.press(60)                       # one short in between
    await e.press(3 * e.long)
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_threshold_boundary(dut):
    e = Env(dut)
    await e.start()
    await e.press(e.long - 1)               # one clock short of the threshold: SHORT
    await e.check_regs()
    await e.press(e.long)                   # exactly the threshold: LONG
    await e.check_regs()
    await e.press(e.long + 1)
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_length_units(dut):
    e = Env(dut)
    await e.start()
    for h in (3 * e.tick - 1, 3 * e.tick, 3 * e.tick + 1, 10 * e.tick + e.tick - 1):
        await e.press(h + e.n)              # keep above the debounce time
        await e.check_regs()


@cocotb.test()
async def test_debounce_rejects_bounce(dut):
    e = Env(dut)
    await e.start()
    pin = dut.BTNC
    for width in (1, 3, e.n // 2, e.n - 3):     # glitches shorter than the debounce time never start a press
        pin.value = 1
        await e.b.cycles(width)
        pin.value = 0
        await e.b.cycles(e.n + 4)
    await e.check_regs()
    # chatter at the start, a short dip in the middle, chatter at the release: one press
    for w in (2, 5, 3, 7):
        pin.value = 1
        await e.b.cycles(w)
        pin.value = 0
        await e.b.cycles(w)
    pin.value = 1
    await e.b.cycles(80)
    pin.value = 0
    await e.b.cycles(e.n - 4)                   # dip shorter than the debounce time
    pin.value = 1
    await e.b.cycles(70)
    pin.value = 0
    await e.b.cycles(4)
    pin.value = 1
    await e.b.cycles(3)
    pin.value = 0
    await e.b.cycles(e.n + 6)
    e.m.press(80 + (e.n - 4) + 70 + 4 + 3)      # high from the steady start to the last release
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_length_saturates(dut):
    e = Env(dut)
    await e.start()
    await e.press(0xFFFF * e.tick + 5 * e.tick)
    await e.check_regs()
    await e.press(e.long // 3)
    await e.check_regs()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    for h in (50, e.long + 10, 70, 2 * e.long):
        await e.press(h)
    await e.check_regs()
    await e.b.write(SHORT_COUNT, 0x1234)        # any write clears; the LED toggles keep their state
    e.m.write(SHORT_COUNT, 0x1234)
    await e.check_regs()
    await e.check_leds()
    await e.b.write(LONG_COUNT, 0)
    e.m.write(LONG_COUNT, 0)
    await e.b.write(LAST, 0xFFFF)               # read-only
    await e.b.write(STATUS, 7)
    await e.check_regs()
    await e.check_leds()
    for off in (0x04, 0x20, 0x7F):
        await e.b.expect(off, 0, "unmapped")
    dut.BTNC.value = 1                          # STATUS[0] shows the debounced level while held
    await e.b.cycles(e.n + 4)
    await e.b.expect(STATUS, e.m.read(STATUS, level=1), "STATUS while held")
    await e.b.expect(SHORT_COUNT, e.m.read(SHORT_COUNT), "nothing classified while held")
    await e.b.expect(LONG_COUNT, e.m.read(LONG_COUNT), "nothing classified while held")


@cocotb.test()
async def test_random_presses(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(16):
        r = rng.random()
        if r < 0.1:
            off = rng.choice((SHORT_COUNT, LONG_COUNT))
            await e.b.write(off, rng.getrandbits(32))
            e.m.write(off, 0)
        elif r < 0.55:
            await e.press(rng.randrange(e.n + 1, e.long))
        else:
            await e.press(rng.randrange(e.long - 3, 3 * e.long))
    await e.check_regs()
    await e.check_leds()
