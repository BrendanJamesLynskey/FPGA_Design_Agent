"""Acceptance tests of t1_gray_stepper against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import ReadOnly, RisingEdge
from model import BIN, CTRL, DESIGN_ID, GRAY, RATE, STEPS, Model, gray

IDLE = {"BTNU": 0, "SW": 0}
NAMES = ("GRAY", "BIN", "CTRL", "RATE", "STEPS")


class Watch:
    """Records every change of LED[9:0] as (clock index, old, new)."""

    def __init__(self, clk, led) -> None:
        self.clk, self.led, self.events, self.t = clk, led, [], 0
        self.task = cocotb.start_soon(self.run())

    async def run(self) -> None:
        prev = None
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()
            self.t += 1
            v = int(self.led.value) & 0x3FF
            if prev is not None and v != prev:
                self.events.append((self.t, prev, v))
            prev = v

    def take(self) -> list[tuple[int, int, int]]:
        ev, self.events = self.events, []
        return ev


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, IDLE)
        self.dut, self.m = dut, Model()
        self.n = self.b.param("DEBOUNCE_CYCLES")
        self.tick = self.b.param("TICK_CYCLES")
        self.w: Watch | None = None

    async def start(self) -> None:
        await self.b.start()
        self.w = Watch(self.b.clk, self.dut.LED)

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def press(self) -> None:
        self.dut.BTNU.value = 1
        await self.b.cycles(self.n + 6)
        self.dut.BTNU.value = 0
        await self.b.cycles(self.n + 6)
        self.m.step()

    async def direction(self, d: int) -> None:
        self.dut.SW.value = d << 15
        await self.b.cycles(4)
        self.m.dir = d

    def check_steps(self, ev, period: int | None = None) -> None:
        """Each event is one step of the model: one bit, the right next code; optionally evenly spaced."""
        for i, (t, old, new) in enumerate(ev):
            assert bin(old ^ new).count("1") == 1, f"step {old:010b} -> {new:010b} changes more than one LED"
            assert new == self.m.next_gray(old), f"step {old:010b} -> {new:010b}, model says {self.m.next_gray(old):010b}"
            if period and i:
                assert t - ev[i - 1][0] == period, f"automatic steps {t - ev[i - 1][0]} clocks apart, want {period}"

    async def check_regs(self) -> None:
        for off in range(5):
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
async def test_press_steps_both_ways(dut):
    e = Env(dut)
    await e.start()
    for d, k in ((0, 4), (1, 6), (0, 1)):
        await e.direction(d)
        for _ in range(k):
            e.w.take()
            await e.press()
            ev = e.w.take()
            assert len(ev) == 1, f"one press gave {len(ev)} LED changes"
        await e.check_regs()
        await e.check_leds()


@cocotb.test()
async def test_wrap_changes_one_led(dut):
    e = Env(dut)
    await e.start()
    await e.wr(BIN, 1022)
    e.w.take()
    for d, k in ((0, 3), (1, 3)):                # 1022 -> 1023 -> 0 -> 1, then back through the wrap
        await e.direction(d)
        for _ in range(k):
            before = e.m.read(GRAY)
            await e.press()
            ev = e.w.take()
            assert len(ev) == 1
            assert ev[0][1] == before
            assert bin(ev[0][1] ^ ev[0][2]).count("1") == 1, f"wrap step {ev[0][1]:010b} -> {ev[0][2]:010b}"
            assert ev[0][2] == e.m.read(GRAY)
    await e.check_regs()


@cocotb.test()
async def test_every_transition_one_bit(dut):
    """All 1024 transitions in each direction (REQ-01's simulation half): automatic mode at the fastest rate."""
    e = Env(dut)
    await e.start()
    for d in (0, 1):
        await e.direction(d)
        await e.wr(RATE, 1)
        e.w.take()
        await e.b.write(CTRL, 1)
        e.m.write(CTRL, 1)
        await e.b.cycles(1030 * e.tick)
        await e.b.write(CTRL, 0)
        e.m.write(CTRL, 0)
        ev = e.w.take()
        assert len(ev) > 1024, f"only {len(ev)} automatic steps"
        e.check_steps(ev, period=e.tick)
        e.m.step(len(ev))
        await e.check_regs()


@cocotb.test()
async def test_auto_rate_exact(dut):
    e = Env(dut)
    await e.start()
    await e.wr(BIN, 1017)
    await e.wr(RATE, 5)
    e.w.take()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.b.cycles(14 * 5 * e.tick)
    await e.wr(RATE, 0)                          # stops; AUTO stays set
    ev = e.w.take()
    assert len(ev) >= 10, f"only {len(ev)} automatic steps at RATE = 5"
    e.check_steps(ev, period=5 * e.tick)
    e.m.step(len(ev))
    await e.b.cycles(40 * e.tick)
    assert not e.w.take(), "RATE = 0 must stand still"
    await e.check_regs()
    await e.check_leds()
    await e.direction(1)                         # runs again, now down, and a press still steps
    e.w.take()
    await e.wr(RATE, 3)
    await e.b.cycles(10 * 3 * e.tick)
    ev = e.w.take()
    assert len(ev) >= 6, f"only {len(ev)} automatic steps at RATE = 3"
    e.check_steps(ev, period=3 * e.tick)
    e.m.step(len(ev))
    await e.b.write(CTRL, 0)
    e.m.write(CTRL, 0)
    e.m.step(len(e.w.take()))
    await e.press()
    assert len(e.w.take()) == 1
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_press_during_auto(dut):
    """v1.2: a press while AUTO = 1 makes one extra step and does not move the automatic grid (the prescaler restarts
    only on a CTRL or RATE write): the automatic steps stay exactly RATE * TICK_CYCLES clocks apart across the press."""
    e = Env(dut)
    await e.start()
    await e.wr(RATE, 100)
    period = 100 * e.tick
    e.w.take()
    await e.wr(CTRL, 1)
    for _ in range(2 * period):
        if e.w.events:
            break
        await e.b.cycles(1)
    assert e.w.events, "no automatic step"
    await e.b.cycles(period // 4)
    t_press = e.w.t
    await e.press()                              # about 2 * (DEBOUNCE_CYCLES + 6) clocks, inside one period
    await e.b.cycles(3 * period)
    await e.wr(CTRL, 0)
    ev = e.w.take()
    e.check_steps(ev)
    window = (t_press, t_press + e.n + 12)
    auto = [x for x in ev if not window[0] <= x[0] <= window[1]]
    assert len(ev) - len(auto) == 1, f"the press gave {len(ev) - len(auto)} LED changes"
    assert len(auto) >= 4, f"only {len(auto)} automatic steps"
    for a, b in zip(auto, auto[1:]):
        assert b[0] - a[0] == period, f"automatic steps {b[0] - a[0]} clocks apart across a press, want {period}"
    e.m.step(len(ev) - 1)                        # the press was counted by press()
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_debounce_rejects_bounce(dut):
    e = Env(dut)
    await e.start()
    pin = dut.BTNU
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
    await e.b.cycles(4 * e.n)                    # held: no repeat
    pin.value = 0
    await e.b.cycles(e.n + 6)
    e.m.step()
    await e.check_regs()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.wr(BIN, 0xFFFF_F2A5)                 # only [9:0] taken
    await e.b.write(GRAY, 0x155)                 # read-only
    await e.b.write(STEPS, 9)
    await e.wr(RATE, 0x1_0007)                   # only [15:0]
    await e.direction(1)
    await e.check_regs()
    await e.check_leds()
    await e.wr(RATE, 0)
    await e.wr(CTRL, 0x103)                      # AUTO set; DIR is read-only, other bits ignored
    await e.check_regs()
    await e.check_leds()
    for off in (0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_random_sequence(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(14):
        r = rng.random()
        if r < 0.2:
            await e.wr(BIN, rng.randrange(1024))
        elif r < 0.35:
            await e.direction(rng.randrange(2))
        else:
            e.w.take()
            await e.press()
            assert len(e.w.take()) == 1
    await e.check_regs()
    await e.check_leds()
