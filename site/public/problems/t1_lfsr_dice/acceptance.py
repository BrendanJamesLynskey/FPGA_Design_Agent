"""Acceptance tests of t1_lfsr_dice against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, scan_display
from model import DESIGN_ID, HISTORY, ROLL, ROLLS, SEED, STATE, STEP, TAPS, Model

IDLE = {"BTNC": 0}
NAMES = ("STATE", "SEED", "TAPS", "ROLL", "HISTORY", "STEP", "ROLLS")


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, IDLE)
        self.dut, self.m = dut, Model()
        self.n = self.b.param("DEBOUNCE_CYCLES")
        self.slot = 1 << self.b.param("REFRESH_BITS")

    async def start(self) -> None:
        await self.b.start()

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def press(self) -> None:
        self.dut.BTNC.value = 1
        await self.b.cycles(self.n + 6)
        self.dut.BTNC.value = 0
        await self.b.cycles(self.n + 6)
        self.m.press()

    async def check_regs(self) -> None:
        for off in range(7):
            await self.b.expect(off, self.m.read(off), NAMES[off])

    async def check_display(self) -> None:
        seen = await scan_display(self.dut, self.b.clk, self.slot)
        want = self.m.display()
        assert {k: v[0] for k, v in seen.items()} == want, f"display {seen} != model {want}"
        assert all(v[1] == 1 for v in seen.values()), "DP lit"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.check_display()


@cocotb.test()
async def test_press_rolls(dut):
    e = Env(dut)
    await e.start()
    for i in range(10):
        await e.press()
        await e.b.expect(ROLL, e.m.read(ROLL), "ROLL")
        await e.b.expect(STATE, e.m.read(STATE), "STATE")
        if i % 3 == 0:
            await e.check_display()
    await e.check_regs()


@cocotb.test()
async def test_seed_and_zero_seed(dut):
    e = Env(dut)
    await e.start()
    for seed in (0x1234, 0xFFFF, 0x0006, 0x0000, 0x0001):
        await e.wr(SEED, seed)
        await e.check_regs()
        await e.press()
        await e.check_regs()
    await e.check_display()


@cocotb.test()
async def test_never_stuck_at_zero(dut):
    e = Env(dut)
    await e.start()
    await e.wr(TAPS, 0x0400)
    await e.wr(SEED, 0x0801)            # one step gives 0x0400 ^ 0x0400 = 0: must become 0x0001
    await e.press()
    await e.check_regs()
    await e.press()
    await e.check_regs()
    await e.wr(TAPS, 0x0000)            # no taps: the state shifts down to 1 and stays there
    await e.wr(SEED, 0x8000)
    await e.wr(STEP, 40)
    await e.b.cycles(60)
    await e.check_regs()


@cocotb.test()
async def test_step_burst_and_period(dut):
    e = Env(dut)
    await e.start()
    await e.wr(STEP, 1000)
    await e.b.cycles(1010)
    await e.check_regs()
    await e.wr(STEP, 0xFFFF)            # the reset taps are maximal: 65535 steps come back to the start
    left = await e.b.read(STEP)
    assert 0 < left < 0xFFFF, f"STEP should read the steps left during a burst, got {left}"
    await e.b.cycles(66000)
    await e.check_regs()
    s0 = await e.b.read(STATE)
    await e.wr(STEP, 0xFFFF)
    await e.b.cycles(66000)
    assert await e.b.read(STATE) == s0


@cocotb.test()
async def test_press_lost_during_burst(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(STEP, 20000)
    dut.BTNC.value = 1                  # this press lands inside the burst: lost
    await e.b.cycles(e.n + 6)
    dut.BTNC.value = 0
    await e.b.cycles(21000)
    e.m.write(STEP, 20000)
    await e.check_regs()
    await e.press()                     # and a later one counts
    await e.check_regs()


@cocotb.test()
async def test_taps_register(dut):
    e = Env(dut)
    await e.start()
    for taps in (0x8016, 0xD008, 0xB400):
        await e.wr(TAPS, taps)
        for _ in range(3):
            await e.press()
        await e.check_regs()


@cocotb.test()
async def test_debounce_rejects_bounce(dut):
    e = Env(dut)
    await e.start()
    pin = dut.BTNC
    for width in (1, 3, e.n // 2, e.n - 3):
        pin.value = 1
        await e.b.cycles(width)
        pin.value = 0
        await e.b.cycles(e.n + 4)
    await e.check_regs()
    for w in (2, 5, 3, 7):
        pin.value = 1
        await e.b.cycles(w)
        pin.value = 0
        await e.b.cycles(w)
    pin.value = 1
    await e.b.cycles(4 * e.n)
    pin.value = 0
    await e.b.cycles(e.n + 6)
    e.m.press()
    await e.check_regs()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.wr(SEED, 0xABCD_5A5A)
    await e.wr(TAPS, 0x1_B400)
    await e.b.write(STATE, 0x1111)      # read-only
    await e.b.write(ROLL, 3)
    await e.b.write(HISTORY, 0x4444)
    await e.b.write(ROLLS, 9)
    await e.check_regs()
    for off in (0x07, 0x50, 0x7F):
        await e.b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_random_sequence(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(16):
        r = rng.random()
        if r < 0.15:
            await e.wr(SEED, rng.getrandbits(16))
        elif r < 0.3:
            n = rng.randrange(1, 3000)
            await e.wr(STEP, n)
            await e.b.cycles(n + 10)
        else:
            await e.press()
    await e.check_regs()
    await e.check_display()


@cocotb.test()
async def test_all_glyphs(dut):
    e = Env(dut)
    await e.start()
    from model import lstep
    for k in (6, 1, 2, 3, 4, 5):
        seed = next(s for s in range(1, 200) if lstep(s, 0xB400) % 6 + 1 == k)
        await e.wr(SEED, seed)
        await e.press()
        assert e.m.roll == k
        await e.check_display()
    await e.b.expect(HISTORY, e.m.read(HISTORY), "HISTORY")
