"""Acceptance tests of p_nec_rx against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import ADDR, CMD, CTRL, DESIGN_ID, E_CHECK, E_FORMAT, GOOD, REPEATS, Model, ideal, ideal_repeat


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"JC2": 1})
        self.t = self.b.param("UNIT_CYCLES")
        self.m = Model(self.t)

    async def start(self) -> None:
        await self.b.start()
        await self.b.cycles(20 * self.t)                 # a long quiet high line

    async def drive(self, durs: list[int]) -> None:
        """Marks are low, spaces high, starting from the idle high line. A final long space follows."""
        for i, d in enumerate(durs):
            self.dut.JC2.value = 0 if i % 2 == 0 else 1
            await self.b.cycles(d)
        self.dut.JC2.value = 1
        await self.b.cycles(14 * self.t)

    async def send(self, durs: list[int]) -> tuple:
        r = self.m.receive(durs)
        await self.drive(durs)
        return r

    async def check(self) -> None:
        for off, name in ((ADDR, "ADDR"), (CMD, "CMD"), (GOOD, "GOOD"), (REPEATS, "REPEATS"), (E_FORMAT, "E_FORMAT"), (E_CHECK, "E_CHECK")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


def scaled(durs: list[int], k: float) -> list[int]:
    return [max(1, round(d * k)) for d in durs]


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_ideal_frames_and_repeats(dut):
    e = Env(dut)
    await e.start()
    for addr, cmd in ((0x04, 0x08), (0x00, 0xFF), (0xFF, 0x00), (0x5A, 0xA5)):
        assert (await e.send(ideal(addr, cmd, e.t)))[0] == "frame"
        await e.check()
    for _ in range(3):
        assert (await e.send(ideal_repeat(e.t)))[0] == "repeat"
    await e.check()
    assert e.m.c["repeat"] == 3 and e.m.c["good"] == 4


@cocotb.test()
async def test_timing_drift_is_tolerated(dut):
    e = Env(dut)
    await e.start()
    for k in (0.85, 1.15, 0.9, 1.1):
        r = await e.send(scaled(ideal(0x3C, 0xC3, e.t), k))
        assert r[0] == "frame", (k, r)
    await e.send(scaled(ideal_repeat(e.t), 1.15))
    await e.check()


@cocotb.test()
async def test_errors_are_classified(dut):
    e = Env(dut)
    await e.start()
    await e.send(ideal(0x11, 0x22, e.t))
    await e.send(ideal(0x11, 0x22, e.t, comp_flip=True))        # complement wrong: E_CHECK
    bad = ideal(0x11, 0x22, e.t)
    bad[20] = 3 * e.t                                            # a bit mark far too long: E_FORMAT
    await e.send(bad)
    bad = ideal(0x11, 0x22, e.t)
    bad[1] = 12 * e.t                                            # leader space too long: E_FORMAT
    await e.send(bad)
    bad = ideal(0x11, 0x22, e.t)
    bad[-1] = 4 * e.t                                            # stop mark too long
    await e.send(bad)
    await e.send([5 * e.t, 8 * e.t])                             # a leader mark too short: ignored, not counted
    await e.send(ideal(0x33, 0x44, e.t))                         # the receiver is still alive afterwards
    await e.check()
    assert e.m.c == {"good": 2, "repeat": 0, "format": 3, "check": 1}


@cocotb.test()
async def test_clear_and_random(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(5):
        a, c = rng.randrange(256), rng.randrange(256)
        k = rng.uniform(0.88, 1.12)
        await e.send(scaled(ideal(a, c, e.t), k))
    await e.check()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()
