"""Acceptance tests of p_tennis_score against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek, scan_display
from model import DESIGN_ID, GAMES_A, GAMES_B, PTS_A, PTS_B, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"BTNL": 0, "BTNR": 0, "BTNC": 0})
        self.m = Model()
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
        if btn == "BTNL":
            self.m.point(0)
        elif btn == "BTNR":
            self.m.point(1)
        else:
            self.m.new_game()

    async def points(self, seq: str) -> None:
        for ch in seq:
            await self.press("BTNL" if ch == "A" else "BTNR")

    async def check(self, display: bool = True) -> None:
        for off, name in ((PTS_A, "PTS_A"), (PTS_B, "PTS_B"), (GAMES_A, "GAMES_A"), (GAMES_B, "GAMES_B")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"
        if display:
            seen = await scan_display(self.dut, self.b.clk, self.slot)
            assert {k: v[0] for k, v in seen.items()} == self.m.display(), f"display {seen} != {self.m.display()}"
            assert all(v[1] == 1 for v in seen.values()), "DP lit"


@cocotb.test()
async def test_identity_and_start(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_plain_game(dut):
    e = Env(dut)
    await e.start()
    for ch in "AABAB":
        await e.points(ch)
        await e.check()
    await e.points("A")                      # A wins the game 40-30
    await e.check()
    assert e.m.winner == 0
    await e.points("BB")                     # ignored after the win
    await e.check()


@cocotb.test()
async def test_deuce_and_advantage(dut):
    e = Env(dut)
    await e.start()
    await e.points("AAABBB")
    await e.check()
    for ch in "AB":                          # advantage then back to deuce, twice
        await e.points(ch)
        await e.check()
    await e.points("BB")
    await e.check()
    assert e.m.winner == 1


@cocotb.test()
async def test_new_game_keeps_game_count(dut):
    e = Env(dut)
    await e.start()
    await e.points("AAAA")
    await e.press("BTNC")
    await e.check()
    await e.points("BBBB")
    await e.press("BTNC")
    await e.points("AAAABBB")                 # a finished game then ignored points
    await e.check()
    assert e.m.games == [2, 1]
    await e.b.write(GAMES_A, 1)
    e.m.write(GAMES_A, 1)
    await e.check(display=False)


@cocotb.test()
async def test_bounce_and_simultaneous(dut):
    e = Env(dut)
    await e.start()
    pin = dut.BTNL
    for width in (1, 3, e.n - 3):             # too short to count
        pin.value = 1
        await e.b.cycles(width)
        pin.value = 0
        await e.b.cycles(e.n + 4)
    await e.check(display=False)
    for w in (2, 5, 3):                        # chatter then a steady level: one point
        pin.value = 1
        await e.b.cycles(w)
        pin.value = 0
        await e.b.cycles(w)
    pin.value = 1
    await e.b.cycles(4 * e.n)
    pin.value = 0
    await e.b.cycles(e.n + 6)
    e.m.point(0)
    await e.check(display=False)
    dut.BTNL.value = 1
    dut.BTNR.value = 1
    await e.b.cycles(e.n + 6)
    dut.BTNL.value = 0
    dut.BTNR.value = 0
    await e.b.cycles(e.n + 6)
    await e.check()                            # same-clock presses cancel


@cocotb.test()
async def test_random_play(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(30):
        r = rng.random()
        await e.press("BTNC" if r < 0.08 else ("BTNL" if r < 0.55 else "BTNR"))
    await e.check()
