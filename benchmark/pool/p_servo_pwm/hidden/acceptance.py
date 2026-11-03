"""Acceptance tests of p_servo_pwm against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.pool.poollib import Monitor, high_runs, rising, wait_rise
from model import DESIGN_ID, FRAME, POS, WIDTH, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        p = self.b.param
        self.m = Model(p("FRAME_CYCLES"), p("MIN_CYCLES"), p("STEP_CYCLES"))

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, ja1=lambda: int(self.dut.JA1.value))

    async def frames(self, sw: int, n: int = 4) -> None:
        """Set the switches, let a frame boundary pass, then check n whole frames of JA1 against the model."""
        self.dut.SW.value = sw
        await self.b.cycles(2 * self.m.frame + 10)
        self.m.new_frame(sw)
        mark = self.mon.mark()
        await self.b.cycles(n * self.m.frame + 5)
        seq = self.mon.since("ja1", mark)
        edges = rising(seq)
        w = self.m.width()
        if w == 0:
            assert not any(seq), "JA1 not low while the servo is off"
            return
        assert len(edges) >= n - 1, f"{len(edges)} frames seen"
        gaps = {b - a for a, b in zip(edges, edges[1:])}
        assert gaps == {self.m.frame}, f"frame lengths {gaps}, want {self.m.frame}"
        widths = {n_ for _, n_ in high_runs(seq)}
        assert widths == {w}, f"pulse widths {widths}, want {w}"


@cocotb.test()
async def test_identity_and_registers(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.frames(0x0000, 2)
    e.m.new_frame(0)
    await e.b.expect(POS, 0, "POS")
    await e.b.expect(WIDTH, e.m.width(), "WIDTH")
    await e.b.expect(FRAME, e.m.frame, "FRAME")


@cocotb.test()
async def test_positions(dut):
    e = Env(dut)
    await e.start()
    for sw in (0, 255, 1, 128, 77):
        await e.frames(sw)
    await e.b.expect(POS, 77, "POS")
    await e.b.expect(WIDTH, e.m.width(), "WIDTH")
    led = await peek(e.b.clk, dut.LED)
    assert led == e.m.leds(), f"LED {led:04X} != {e.m.leds():04X}"


@cocotb.test()
async def test_switch_moving_mid_pulse_is_not_seen_until_next_frame(dut):
    """The position is sampled at the frame start: a change in the middle of the pulse must not alter it."""
    e = Env(dut)
    await e.start()
    await e.frames(10, 2)
    mark = e.mon.mark()
    await wait_rise(e.b.clk, e.mon, "ja1")
    await e.b.cycles(e.m.min_c // 2 + 5 * e.m.step)      # inside the running pulse
    changed = e.mon.mark() - mark
    dut.SW.value = 200
    await e.b.cycles(3 * e.m.frame)
    runs = high_runs(e.mon.since("ja1", mark))
    old = e.m.min_c + 10 * e.m.step
    new = e.m.min_c + 200 * e.m.step
    assert len(runs) >= 3, runs
    for start, n in runs:
        want = old if start < changed else new
        assert n == want, f"pulse starting at {start} (switch moved at {changed}) is {n} clocks, want {want}"


@cocotb.test()
async def test_off_switch_and_back(dut):
    e = Env(dut)
    await e.start()
    await e.frames(40, 2)
    await e.frames(0x8000 | 40, 3)
    led = await peek(e.b.clk, dut.LED)
    assert led >> 15 == 1 and led & 0xFF == 40
    await e.b.expect(WIDTH, 0, "WIDTH when off")
    await e.frames(40, 3)


@cocotb.test()
async def test_random_positions(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(5):
        await e.frames(rng.randrange(256) | (0x8000 if rng.random() < 0.2 else 0), 3)
