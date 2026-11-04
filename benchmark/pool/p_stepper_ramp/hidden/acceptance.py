"""Acceptance tests of p_stepper_ramp against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.pool.poollib import Monitor, falling, high_runs, rising
from model import DESIGN_ID, MOVE, POSITION, STATUS, Model, gaps


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        p = self.b.param
        self.start_i, self.min_i, self.dec = p("START_INT"), p("MIN_INT"), p("RAMP_DEC")
        self.pulse, self.setup, self.hold = p("PULSE_CYCLES"), p("DIR_SETUP"), p("HOLD_CYCLES")
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, step=lambda: int(self.dut.JA1.value), dr=lambda: int(self.dut.JA2.value),
                           en=lambda: int(self.dut.JA3.value), led=lambda: int(self.dut.LED.value))

    async def move(self, n: int) -> None:
        mark = self.mon.mark()
        await self.b.write(MOVE, n & 0xFFFF)
        self.m.write(MOVE, n & 0xFFFF)
        steps = abs(n)
        total = self.setup + sum(gaps(steps, self.start_i, self.min_i, self.dec)) + self.pulse + self.hold
        await self.b.cycles(total + 300)
        self.m.finish()
        if steps == 0:
            return
        step, dr, en = (self.mon.since(k, mark) for k in ("step", "dr", "en"))
        starts = rising(step)
        assert len(starts) == steps, f"{len(starts)} STEP pulses for a move of {n}"
        want_gaps = gaps(steps, self.start_i, self.min_i, self.dec)
        got_gaps = [b - a for a, b in zip(starts, starts[1:])]
        assert got_gaps == want_gaps, f"step spacing {got_gaps[:12]}.., want {want_gaps[:12]}.."
        assert {w for _, w in high_runs(step)} <= {self.pulse}, "STEP pulse width"
        first_fall = falling(en)
        assert first_fall, "driver never enabled"
        assert starts[0] - first_fall[0] == self.setup, f"first step {starts[0] - first_fall[0]} clocks after enabling, want {self.setup}"
        en_rise = rising(en)
        last_step_end = starts[-1] + self.pulse
        assert en_rise and en_rise[-1] - last_step_end == self.hold, f"driver held {en_rise[-1] - last_step_end} clocks after the last pulse, want {self.hold}"
        want_dir = 1 if n > 0 else 0
        seg = dr[first_fall[0]: en_rise[-1]]
        assert set(seg) == {want_dir}, "DIR wrong or changed during the move"

    async def check(self) -> None:
        for off, name in ((POSITION, "POSITION"), (STATUS, "STATUS")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(50)
    assert not any(e.mon.v["step"]) and all(e.mon.v["en"]), "STEP must idle low and the driver disabled (JA3 high)"
    await e.check()


@cocotb.test()
async def test_long_move_trapezoid_both_directions(dut):
    e = Env(dut)
    await e.start()
    await e.move(40)
    await e.check()
    await e.move(-33)
    await e.check()
    assert e.m.pos == 7
    led = await peek(e.b.clk, dut.LED)
    assert led & 1 == 0, "driver still enabled after the hold time"


@cocotb.test()
async def test_short_moves_never_reach_top_speed(dut):
    e = Env(dut)
    await e.start()
    for n in (1, 2, 3, 7, -6, 12):
        await e.move(n)
    await e.check()


@cocotb.test()
async def test_refused_and_zero_moves(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(MOVE, 0)                      # nothing happens, nothing counted
    await e.b.cycles(40)
    assert not any(e.mon.v["step"]) and all(e.mon.v["en"])
    mark = e.mon.mark()
    await e.b.write(MOVE, 250)
    e.m.write(MOVE, 250)
    await e.b.write(MOVE, 0xFFF0)                 # -16 while busy: refused
    e.m.write(MOVE, 0xFFF0)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    total = e.setup + sum(gaps(250, e.start_i, e.min_i, e.dec)) + e.pulse + e.hold
    await e.b.cycles(total + 300)
    e.m.finish()
    assert len(rising(e.mon.since("step", mark))) == 250, "the refused move added steps"
    await e.check()
    assert e.m.refused == 1 and e.m.pos == 250


@cocotb.test()
async def test_random_moves(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(4):
        await e.move(rng.choice([-1, 1]) * rng.randrange(1, 30))
    await e.check()
    led = await peek(e.b.clk, dut.LED)
    assert led & 6 == (e.m.dir << 2), "LED[2] must follow DIR after the moves"
