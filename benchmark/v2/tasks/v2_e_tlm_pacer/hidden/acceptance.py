"""Hidden bench of the telemetry pacer: ticks and requests applied through the shell, the counter and totals compared with the model."""

from __future__ import annotations

import cocotb
from benchmark.lib.net_bench import Inst, RegEnv, seeded_rng
from model import CNT, CTRL, DESIGN_ID, EFF, FRAMES, OVERRUNS, REQ, STAT, TAKE, TICK, Model

ALLR = (CTRL, REQ, EFF, STAT, FRAMES, OVERRUNS, CNT)


class Pace(RegEnv):
    FLOOR = {"a": 4, "b": 16}

    def __init__(self, dut, which: str = "a") -> None:
        self.floor = self.FLOOR[which]
        super().__init__(Inst(dut, which, CLKS_PER_BIT=8, PERIOD_MIN=self.floor), Model(self.floor))

    async def ticks(self, n: int) -> None:
        while n > 0:
            k = min(n, 255)
            await self.wr(TICK, k)
            n -= k

    async def view(self, what: str = "") -> None:
        await self.regs(ALLR, what)


@cocotb.test()
async def test_pace_identity_defaults_and_reset(dut):
    p = Pace(dut)
    await p.b.start()
    assert await p.b.shell_id() == DESIGN_ID
    await p.regs(range(10), "at reset")
    await p.wr(CTRL, 1)
    await p.ticks(150)
    await p.b.reset()
    p.m = Model(p.floor)
    await p.regs(range(10), "after reset")
    await p.led(0, "led after reset")


@cocotb.test()
async def test_pace_one_frame_exactly_every_period(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 10)
    await p.wr(CTRL, 1)
    await p.b.expect(EFF, 10, "period in force from the switch-on")
    await p.ticks(9)
    await p.view("nine ticks")
    assert p.m.frames == 0
    await p.ticks(1)
    await p.view("the tenth tick")
    assert p.m.frames == 1 and p.m.wait == 1 and p.m.count == 0
    await p.wr(TAKE, 0)
    for k in range(4):
        await p.ticks(9)
        assert p.m.wait == 0
        await p.ticks(1)
        await p.view(f"frame {k + 2}")
        await p.wr(TAKE, 1)
    await p.led(p.m.frames, "LED shows the frame total")
    assert p.m.frames == 5 and p.m.over == 0


@cocotb.test()
async def test_pace_overruns_are_dropped_not_queued(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 6)
    await p.wr(CTRL, 1)
    await p.ticks(6)
    await p.view("first frame waiting")
    await p.ticks(18)
    await p.view("three more fell due while waiting")
    assert p.m.over == 3 and p.m.frames == 1
    await p.wr(TAKE, 0)
    await p.b.expect(STAT, 2, "taken: nothing waits")
    await p.wr(TAKE, 0)
    await p.view("taking again does nothing")
    await p.ticks(5)
    assert p.m.wait == 0
    await p.ticks(1)
    await p.view("no queued frame appears, the next one falls due on schedule")
    assert p.m.frames == 2 and p.m.over == 3


@cocotb.test()
async def test_pace_period_clamp_and_deferred_change(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 0)
    await p.b.expect(REQ, 0, "the request is kept as asked")
    await p.wr(CTRL, 1)
    await p.b.expect(EFF, p.floor, "raised to the minimum")
    await p.ticks(p.floor * 2 + 1)
    await p.view("at the minimum")
    await p.wr(TAKE, 0)
    await p.wr(REQ, 40)
    await p.b.expect(EFF, p.floor, "a new request does not change the period in force")
    await p.ticks(p.floor - 1 - 1)
    await p.view("end of the count under the old period")
    await p.ticks(1)
    await p.view("the old period ended: new one in force")
    assert p.m.eff == 40
    await p.ticks(39)
    await p.view("39 ticks into 40")
    await p.ticks(1)
    await p.view("40")
    await p.wr(REQ, 3)
    await p.wr(CTRL, 0)
    await p.wr(REQ, 9)
    await p.view("a request written while off leaves the period in force alone")
    await p.wr(REQ, 3)
    await p.wr(CTRL, 1)
    await p.view("switch-on takes the new request at once")
    await p.wr(REQ, 0xFFFF)
    await p.b.expect(REQ, 0xFFFF, "largest request")
    await p.wr(REQ, 0x12340010)
    await p.b.expect(REQ, 0x0010, "only 16 bits")


@cocotb.test()
async def test_pace_switch_off_forgets_the_waiting_frame_and_keeps_the_totals(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 5)
    await p.wr(CTRL, 1)
    await p.ticks(13)
    await p.view("two periods and 3 ticks")
    assert p.m.frames == 1 and p.m.over == 1 and p.m.count == 3
    await p.wr(CTRL, 0)
    await p.view("switched off")
    assert p.m.wait == 0 and p.m.count == 0 and p.m.frames == 1
    await p.ticks(40)
    await p.view("ticks while off do nothing")
    await p.wr(CTRL, 0xFFFFFFFE)
    await p.b.expect(CTRL, 0, "only bit 0 enables")
    await p.wr(CTRL, 1)
    await p.wr(CTRL, 1)                                   # already on: no restart
    await p.ticks(3)
    await p.wr(CTRL, 1)
    await p.view("a second enable does not restart the count")
    assert p.m.count == 3
    await p.ticks(2)
    await p.view("frame after a fresh start")
    assert p.m.frames == 2


@cocotb.test()
async def test_pace_long_period_and_counter_reads(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 700)
    await p.wr(CTRL, 1)
    for n in (255, 255, 189, 1):
        await p.ticks(n)
        await p.regs((CNT, FRAMES, STAT), f"after {n}")
    assert p.m.frames == 1
    await p.ticks(255)
    await p.regs((CNT,), "into the second period")
    await p.wr(CTRL, 0)
    await p.wr(REQ, 1100)
    await p.wr(CTRL, 1)
    for n in (255, 255, 255, 255, 79, 1):
        await p.ticks(n)
        await p.regs((CNT, FRAMES, STAT), f"1100-tick period, after {n}")
    await p.poke_read_only((EFF, STAT, FRAMES, OVERRUNS, CNT), 0x4444)
    await p.view("read-only writes")
    await p.unmapped((0x09, 0x40, 0x7F))


@cocotb.test()
async def test_pace_random_mix(dut):
    p = Pace(dut)
    await p.b.start()
    rng = seeded_rng()
    for k in range(25):
        c = rng.randrange(6)
        if c == 0:
            await p.wr(REQ, rng.choice([0, 1, 3, 4, 5, 15, 16, 17, 20, rng.randrange(1, 60)]))
        elif c == 1:
            await p.wr(CTRL, rng.randrange(2))
        elif c == 2:
            await p.wr(TAKE, 0)
        else:
            await p.wr(TICK, rng.choice([1, 3, 7, 15, 16, 17, 30, rng.randrange(0, 256)]))
        await p.view(f"random {k}")


@cocotb.test()
async def test_pace_second_period_floor(dut):
    """The copy with a different PERIOD_MIN: its own floor applies to the request, at switch-on and at the boundary."""
    p = Pace(dut, "b")
    await p.b.start()
    await p.regs(range(9), "at reset")
    await p.wr(REQ, 5)
    await p.wr(CTRL, 1)
    await p.b.expect(EFF, 16, "floor 16")
    await p.ticks(15)
    await p.view("15 ticks")
    await p.ticks(1)
    await p.view("16 ticks: the first frame")
    assert p.m.frames == 1
    await p.wr(REQ, 100)
    await p.ticks(16)
    await p.view("old period ends, 100 in force")
    assert p.m.eff == 100 and p.m.over == 1
    await p.wr(REQ, 17)
    await p.ticks(100)
    await p.view("the 100 count ends")
    await p.ticks(17)
    await p.view("17 is above the floor")


@cocotb.test()
async def test_pace_reset_clears_request_and_totals_and_unmapped_writes_do_nothing(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 7)
    await p.wr(CTRL, 1)
    await p.ticks(20)
    await p.poke_unmapped((0x09, 0x20, 0x40, 0x7F))
    await p.regs(range(10), "after unmapped writes")
    await p.b.reset()
    p.m = Model(p.floor)
    await p.regs(range(10), "after reset")
    await p.led(0, "led")
