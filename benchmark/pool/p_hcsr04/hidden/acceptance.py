"""Acceptance tests of p_hcsr04 against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import RisingEdge
from model import CTRL, DESIGN_ID, DIST, GOOD, OOR, RAW, START, STATUS, TIMEOUTS, WIDTH, Model

DELAY = 20          # the ranger raises the echo this many clocks after the trigger falls


class Ranger:
    """The HC-SR04 stand-in: answers each trigger with an echo of the next scheduled width (None: no echo)."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.queue: list[int | None] = []
        self.trig_widths: list[int] = []
        self.echo_high_at_trigger = False

    async def run(self) -> None:
        d = self.dut
        d.JD2.value = 0
        prev = 0
        while True:
            await RisingEdge(d.CLK100MHZ)
            trig = int(d.JD1.value)
            if trig and not prev:
                self.echo_high_at_trigger |= bool(int(d.JD2.value))
                n = 1
                while True:
                    await RisingEdge(d.CLK100MHZ)
                    if not int(d.JD1.value):
                        break
                    n += 1
                self.trig_widths.append(n)
                width = self.queue.pop(0) if self.queue else None
                if width is not None:
                    for _ in range(DELAY):
                        await RisingEdge(d.CLK100MHZ)
                    d.JD2.value = 1
                    for _ in range(width):
                        await RisingEdge(d.CLK100MHZ)
                    d.JD2.value = 0
                prev = 0
                continue
            prev = trig


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"JD2": 0})
        self.m = Model(self.b.param("CLKS_PER_CM"), self.b.param("MAX_ECHO"))
        self.max_echo = self.b.param("MAX_ECHO")
        self.trig = self.b.param("TRIG_CYCLES")
        self.r = Ranger(dut)

    async def start(self) -> None:
        await self.b.start()
        cocotb.start_soon(self.r.run())

    async def wait_idle(self) -> None:
        for _ in range(60):
            await self.b.cycles(300)
            if not (await self.b.read(STATUS)) & 1:
                return
        raise AssertionError("the ping never finished")

    async def ping(self, width: int | None) -> None:
        self.r.queue.append(width)
        await self.b.write(START, 1)
        await self.wait_idle()
        self.m.ping(width)

    async def check(self) -> None:
        for off, name in ((RAW, "RAW"), (DIST, "DIST"), (WIDTH, "WIDTH"), (GOOD, "GOOD"), (TIMEOUTS, "TIMEOUTS"), (OOR, "OOR")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(200)
    assert int(dut.JD1.value) == 0 and not e.r.trig_widths, "trigger without a start"
    await e.check()


@cocotb.test()
async def test_trigger_width_and_distance_rounding(dut):
    e = Env(dut)
    await e.start()
    cpc = e.m.cpc
    for w in (cpc * 30, cpc * 30 + cpc - 1, cpc * 31, cpc * 2 + 1):
        await e.ping(w)
        await e.check()
    assert set(e.r.trig_widths) == {e.trig}, f"trigger widths {e.r.trig_widths}, want {e.trig}"


@cocotb.test()
async def test_median_of_three_window(dut):
    e = Env(dut)
    await e.start()
    cpc = e.m.cpc
    for cm in (40, 12, 41, 80, 79, 5):
        await e.ping(cpc * cm + 3)
        await e.check()
    await e.ping(None)                          # a time-out leaves the window alone
    await e.ping(e.max_echo + 40)               # so does an out-of-range echo
    await e.check()
    assert e.m.timeouts == 1 and e.m.oor == 1
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()


@cocotb.test()
async def test_no_trigger_while_echo_is_high(dut):
    e = Env(dut)
    await e.start()
    await e.ping(e.max_echo // 2)
    long_echo = e.max_echo + 12000
    e.r.queue.append(long_echo)                 # abandoned at MAX_ECHO, but the echo stays high long after
    await e.b.write(START, 1)
    await e.b.cycles(e.max_echo // 3)
    await e.b.write(START, 1)                   # ignored while busy
    await e.wait_idle()
    e.m.ping(long_echo)
    assert int(dut.JD2.value) == 1, "the test needs the echo to still be high here"
    e.r.queue.append(e.max_echo // 3)
    await e.b.write(START, 1)                   # the echo is still high: the ping must wait for it to fall
    await e.b.cycles(200)
    await e.wait_idle()
    e.m.ping(e.max_echo // 3)
    await e.check()
    assert not e.r.echo_high_at_trigger, "the trigger went out while the echo was high"
    assert len(e.r.trig_widths) == 3, f"{len(e.r.trig_widths)} triggers for 3 pings"


@cocotb.test()
async def test_random_pings(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(6):
        r = rng.random()
        await e.ping(None if r < 0.12 else (e.max_echo + rng.randrange(20, 500) if r < 0.25 else rng.randrange(60, e.max_echo - 5)))
    await e.check()
