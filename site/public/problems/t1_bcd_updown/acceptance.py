"""Acceptance tests of t1_bcd_updown against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek, scan_display
from model import BCD, COUNT, DESIGN_ID, STEP, WRAPS, Model

IDLE = {"BTNU": 0, "BTND": 0, "SW": 0}


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, IDLE)
        self.dut, self.m = dut, Model()
        self.n = self.b.param("DEBOUNCE_CYCLES")
        self.slot = 1 << self.b.param("REFRESH_BITS")

    async def start(self) -> None:
        await self.b.start()

    async def press(self, btn: str) -> None:
        pin = getattr(self.dut, btn)
        pin.value = 1
        await self.b.cycles(self.n + 6)
        pin.value = 0
        await self.b.cycles(self.n + 6)
        self.m.press(up=btn == "BTNU", down=btn == "BTND")

    async def switches(self, v: int) -> None:
        self.dut.SW.value = v
        await self.b.cycles(4)
        self.m.sw = v

    async def check_regs(self) -> None:
        for off in (COUNT, BCD, WRAPS, STEP):
            await self.b.expect(off, self.m.read(off), ("COUNT", "BCD", "WRAPS", "STEP")[off])

    async def check_display(self) -> None:
        seen = await scan_display(self.dut, self.b.clk, self.slot)
        want = self.m.display()
        assert {k: v[0] for k, v in seen.items()} == want, f"display {seen} != model {want}"
        assert all(v[1] == 1 for v in seen.values()), "DP lit"

    async def check_leds(self) -> None:
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.check_display()


@cocotb.test()
async def test_steps_from_switches(dut):
    e = Env(dut)
    await e.start()
    for sw in (0, 1, 2, 3, 2, 1):
        await e.switches(sw)
        await e.press("BTNU")
        await e.check_regs()
    await e.press("BTND")
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_wrap_both_ends(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(COUNT, 9998)
    e.m.write(COUNT, 9998)
    await e.switches(2)            # step 5
    await e.press("BTNU")          # 9998 + 5 -> 3, one wrap
    await e.check_regs()
    await e.switches(3)            # step 10
    await e.press("BTND")          # 3 - 10 -> 9993, second wrap
    await e.check_regs()
    await e.b.write(COUNT, 9999)
    e.m.write(COUNT, 9999)
    await e.switches(0)            # step 1: 9999 -> 0 exactly at the boundary
    await e.press("BTNU")
    await e.check_regs()
    await e.press("BTND")          # 0 -> 9999
    await e.check_regs()
    await e.b.write(WRAPS, 0x55)
    e.m.write(WRAPS, 0x55)
    await e.check_regs()


@cocotb.test()
async def test_debounce_rejects_bounce(dut):
    e = Env(dut)
    await e.start()
    pin = dut.BTNU
    for width in (1, 3, e.n // 2, e.n - 3):      # every pulse shorter than the debounce time
        pin.value = 1
        await e.b.cycles(width)
        pin.value = 0
        await e.b.cycles(e.n + 4)
    await e.check_regs()                         # no press yet
    # a bouncy press: chatter then a long steady level counts once
    for w in (2, 5, 3, 7):
        pin.value = 1
        await e.b.cycles(w)
        pin.value = 0
        await e.b.cycles(w)
    pin.value = 1
    await e.b.cycles(4 * e.n)                    # held: no repeat
    pin.value = 0
    await e.b.cycles(e.n + 6)
    e.m.press(up=True)
    await e.check_regs()


@cocotb.test()
async def test_decimal_display(dut):
    e = Env(dut)
    await e.start()
    for v in (4071, 9999, 1000, 806):
        await e.b.write(COUNT, v)
        e.m.write(COUNT, v)
        await e.check_display()
        await e.check_leds()


@cocotb.test()
async def test_leading_zero_blanking(dut):
    """Trap: a textbook decimal display shows all four digits; this spec blanks leading zeros."""
    e = Env(dut)
    await e.start()
    for v in (0, 7, 42, 305):
        await e.b.write(COUNT, v)
        e.m.write(COUNT, v)
        await e.check_display()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(COUNT, 1234)
    e.m.write(COUNT, 1234)
    await e.b.write(COUNT, 10000)      # out of range: ignored
    e.m.write(COUNT, 10000)
    await e.b.write(BCD, 0x9999)       # read-only
    await e.b.write(STEP, 7)
    await e.check_regs()
    for off in (0x04, 0x10, 0x7F):
        await e.b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_random_sequence(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(14):
        r = rng.random()
        if r < 0.15:
            await e.switches(rng.randrange(4))
        elif r < 0.3:
            v = rng.choice([rng.randrange(10000), rng.randrange(9990, 10000), rng.randrange(10), 10000 + rng.randrange(6000)])
            await e.b.write(COUNT, v)
            e.m.write(COUNT, v)
        else:
            await e.press(rng.choice(("BTNU", "BTND")))
    await e.check_regs()
    await e.check_display()
    await e.check_leds()


@cocotb.test()
async def test_simultaneous_presses_cancel(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(COUNT, 50)
    e.m.write(COUNT, 50)
    dut.BTNU.value = 1
    dut.BTND.value = 1
    await e.b.cycles(e.n + 6)
    dut.BTNU.value = 0
    dut.BTND.value = 0
    await e.b.cycles(e.n + 6)
    e.m.press(up=True, down=True)
    await e.check_regs()
