"""Acceptance tests of t1_elevator_fsm against model.py (hidden from the agent).

The clocked model and the RTL run side by side. Events seen on the pins (LED[14] rise = depart, LED[3:0] change =
arrive, LED[15] rise/fall = door open/close) must match the model's events in order and floor, and every interval
that does not include idle time must match exactly (FLOOR_CYCLES, DOOR_CYCLES, 0). Calls are placed well away from
the car's decision clocks, so a design whose call latency differs by a few clocks gets the same order."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import ReadOnly, RisingEdge
from cocotb.utils import get_sim_time
from model import DESIGN_ID, DIR, DOOR, FLOOR, IDLE, MOVES, MOVING, PENDING, STATE, Model

NAMES = ("FLOOR", "DIR", "PENDING", "STATE", "MOVES")
SW_LAT = 2              # clocks from a switch change to the call being seen (model time base)


class Watch:
    def __init__(self, dut, clk) -> None:
        self.events: list[tuple[int, str, int]] = []
        cocotb.start_soon(self.run(dut, clk))

    async def run(self, dut, clk) -> None:
        prev = None
        while True:
            await RisingEdge(clk)
            await ReadOnly()
            v = int(dut.LED.value)
            t = int(get_sim_time("ns")) // 10
            if prev is not None and v != prev:
                fl = [k for k in range(4) if v >> k & 1]
                assert len(fl) == 1, f"LED[3:0] = {v & 15:04b} is not one-hot"
                assert not (v >> 15 & 1 and v >> 14 & 1), "door open while moving"
                f = fl[0]
                if prev >> 15 & 1 and not v >> 15 & 1:
                    self.events.append((t, "close", f))
                if v >> 14 & 1 and not prev >> 14 & 1:
                    self.events.append((t, "depart", f))
                if v & 15 != prev & 15:
                    self.events.append((t, "arrive", f))
                if v >> 15 & 1 and not prev >> 15 & 1:
                    self.events.append((t, "open", f))
            prev = v


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"SW": 0})
        self.dut = dut
        self.fc = self.b.param("FLOOR_CYCLES")
        self.dc = self.b.param("DOOR_CYCLES")
        self.cpb = self.b.param("CLKS_PER_BIT")
        self.m = Model(self.fc, self.dc)
        self.sw = 0
        self.w: Watch | None = None

    def now(self) -> int:
        return int(get_sim_time("ns")) // 10

    async def start(self) -> None:
        await self.b.start()
        self.m.t = self.now()
        self.w = Watch(self.dut, self.b.clk)

    async def switch(self, k: int, v: int) -> None:
        old = self.sw >> k & 1
        self.sw = (self.sw & ~(1 << k)) | v << k
        self.dut.SW.value = self.sw
        if v and not old:
            self.m.call(self.now() + SW_LAT, 1 << k)
        await self.b.cycles(1)

    async def flick(self, *floors: int) -> None:
        """Switches up together then down again: one call each, all seen on the same clock."""
        mask = sum(1 << k for k in floors)
        new = mask & ~self.sw
        self.sw |= mask
        self.dut.SW.value = self.sw
        if new:
            self.m.call(self.now() + SW_LAT, new)
        await self.b.cycles(6)
        self.sw &= ~mask
        self.dut.SW.value = self.sw
        await self.b.cycles(1)

    async def shell_call(self, mask: int) -> None:
        await self.b.write(PENDING, mask)
        self.m.call(self.now() - 70 * self.cpb - 3, mask & 15)   # the write acted before the 7-byte response

    async def wait(self, n: int) -> None:
        await self.b.cycles(n)

    async def settle(self, limit: int = 20000) -> None:
        """Wait until the model says the car is idle with nothing pending, then a little more."""
        self.m.run_to(self.now())
        n = 0
        while not (self.m.state == IDLE and self.m.pend == 0 and not self.m.sched):
            self.m.step()
            n += 1
            assert n < limit
        await self.b.cycles(max(0, self.m.t - self.now()) + 20)
        self.m.run_to(self.now())

    def check_events(self) -> None:
        self.m.run_to(self.now() - 4)
        got = [(k, f) for _, k, f in self.w.events]
        want = [(k, f) for _, k, f in self.m.events]
        assert got == want, f"events {got} != model {want}"
        for i in range(1, len(want)):
            dm = self.m.events[i][0] - self.m.events[i - 1][0]
            dr = self.w.events[i][0] - self.w.events[i - 1][0]
            if want[i][0] in ("depart", "open") and dm != 0:
                continue                                       # idle time before a call: not compared
            assert dr == dm, f"{want[i - 1]} -> {want[i]} took {dr} clocks, model {dm}"

    async def check_regs(self) -> None:
        self.m.run_to(self.now())
        for off in range(5):
            await self.b.expect(off, self.m.read(off), NAMES[off])

    async def check_leds(self) -> None:
        self.m.run_to(self.now())
        led = await peek(self.b.clk, self.dut.LED)
        self.m.run_to(self.now())
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_single_call(dut):
    e = Env(dut)
    await e.start()
    await e.flick(2)
    await e.settle()
    e.check_events()
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_scan_keeps_direction(dut):
    """From floor 1 going up, calls for 0 and 3 together: SCAN goes up to 3 first (nearest-first would go to 0)."""
    e = Env(dut)
    await e.start()
    await e.flick(1)
    await e.settle()
    await e.flick(0, 3)
    await e.settle()
    e.check_events()
    assert [f for _, k, f in e.w.events if k == "open"] == [1, 3, 0]
    await e.check_regs()


@cocotb.test()
async def test_call_on_the_way_and_behind(dut):
    e = Env(dut)
    await e.start()
    await e.flick(3)
    await e.wait(e.fc // 2)                       # between 0 and 1: call 2 (ahead) and 0 (behind)
    await e.flick(2)
    await e.check_leds()                          # mid-move: LED[7:4] show the calls, LED[14] moving
    await e.wait(e.fc)
    await e.flick(0)
    await e.settle()
    e.check_events()
    assert [f for _, k, f in e.w.events if k == "open"] == [2, 3, 0]
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_call_at_current_floor(dut):
    e = Env(dut)
    await e.start()
    await e.flick(0)                              # idle at 0: the door opens, no move
    await e.wait(e.dc // 3)
    await e.flick(0)                              # door open here: ignored
    await e.wait(e.dc // 3)
    await e.check_leds()
    await e.flick(1)                              # another floor during the door: kept
    await e.settle()
    e.check_events()
    assert [f for _, k, f in e.w.events if k == "open"] == [0, 1]
    await e.check_regs()


@cocotb.test()
async def test_switch_edges_only(dut):
    e = Env(dut)
    await e.start()
    await e.switch(2, 1)
    await e.settle()
    await e.wait(2 * e.fc)                        # held up: no second call
    await e.switch(2, 0)
    await e.wait(e.fc)
    await e.check_regs()
    await e.switch(2, 1)                          # up again at floor 2 (idle): door opens again
    await e.settle()
    await e.switch(2, 0)
    e.check_events()
    await e.check_regs()


@cocotb.test()
async def test_turns_round_at_the_top(dut):
    e = Env(dut)
    await e.start()
    await e.flick(3)
    await e.settle()
    await e.flick(1)
    await e.wait(e.fc // 2)
    e.m.run_to(e.now())
    assert e.m.state == MOVING and e.m.dir == 1
    await e.b.expect(DIR, 1, "DIR while moving down")
    await e.settle()
    e.check_events()
    await e.check_regs()


@cocotb.test()
async def test_shell_calls_and_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.shell_call(0b0100)                    # W1S: call 2
    await e.b.write(PENDING, 0)                   # zeros do nothing
    for off in (FLOOR, DIR, STATE, MOVES):
        await e.b.write(off, 3)                   # read-only
    await e.settle()
    await e.flick(0)                              # from 2 down to 0 (800 clocks): a shell call for 3
    await e.shell_call(0b1000)                    # lands mid-way and must add to the calls, not replace them
    await e.settle()
    e.check_events()
    await e.check_regs()
    for off in (0x05, 0x22, 0x7F):
        await e.b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_random_calls(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(12):
        await e.wait(rng.randrange(50, e.fc + e.dc))
        e.m.run_to(e.now())
        # keep calls away from the model's decision clocks
        lim = e.fc if e.m.state == MOVING else e.dc if e.m.state == DOOR else None
        if lim is not None and not (12 < e.m.timer < lim - 12):
            await e.wait(30)
        await e.flick(*rng.sample(range(4), rng.randrange(1, 3)))
    await e.settle(60000)
    e.check_events()
    await e.check_regs()
    await e.check_leds()
