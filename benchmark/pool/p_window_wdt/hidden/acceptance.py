"""Acceptance tests of p_window_wdt against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, high_runs, now_clk
from model import BADKEYS, DESIGN_ID, EARLYS, KICK, LATES, STATUS, WIN_CLOSE, WIN_OPEN, Model

EFF = 640          # clocks from the start of a shell write request to its effect on the window


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        p = self.b.param
        self.m = Model(p("WIN_OPEN"), p("WIN_CLOSE"))
        self.pulse = p("RST_PULSE")
        self.mt = 0

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, ja1=lambda: int(self.dut.JA1.value), led=lambda: int(self.dut.LED.value))
        self.mt = now_clk()

    def sync(self, t: int) -> None:
        if t > self.mt:
            self.m.advance(t - self.mt)
            self.mt = t

    async def wait_until_c(self, target: int) -> None:
        """Wait so that a kick launched now takes effect when the counter is about `target`."""
        await self.wait(max(0, target - self.m.c - EFF))

    async def wait(self, n: int) -> None:
        await self.b.cycles(n)
        self.sync(now_clk())

    async def enable(self, on: bool) -> None:
        self.dut.SW.value = int(on)
        await self.b.cycles(3)
        self.mt = now_clk()
        self.m.enable(on)

    async def kick(self, key: int = 0x6B) -> None:
        t0 = now_clk()
        await self.b.write(KICK, key)
        self.sync(t0 + EFF)
        self.m.kick(key)
        self.sync(now_clk())

    async def read(self, off: int, what: str) -> None:
        t0 = now_clk()
        got = await self.b.read(off)
        self.sync(t0 + EFF)
        want = self.m.read(off)
        self.sync(now_clk())
        assert got == want, f"{what}: RTL {got}, model {want}"

    async def check(self) -> None:
        for off, name in ((STATUS, "STATUS"), (EARLYS, "EARLYS"), (LATES, "LATES"), (BADKEYS, "BADKEYS"),
                          (WIN_OPEN, "WIN_OPEN"), (WIN_CLOSE, "WIN_CLOSE")):
            await self.read(off, name)

    def check_pulses(self) -> None:
        runs = high_runs(self.mon.v["ja1"])
        assert all(n == self.pulse for _, n in runs), f"pulse widths {[n for _, n in runs]}, want {self.pulse}"
        assert len(runs) == self.m.faults, f"{len(runs)} pulses for {self.m.faults} faults"


@cocotb.test()
async def test_identity_and_idle_when_disabled(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.wait(3 * e.m.wc)                   # disabled: nothing times out
    await e.check()
    assert e.m.faults == 0
    await e.kick()                              # key kicks while disabled are harmless
    await e.check()
    e.check_pulses()


@cocotb.test()
async def test_good_kicks_in_window(dut):
    e = Env(dut)
    await e.start()
    await e.enable(True)
    for _ in range(3):
        await e.wait((e.m.wo + e.m.wc) // 2 - EFF)
        await e.kick()
    await e.check()
    assert e.m.faults == 0 and e.m.fe is False and e.m.fl is False
    e.check_pulses()


@cocotb.test()
async def test_early_kick_is_a_fault(dut):
    e = Env(dut)
    await e.start()
    await e.enable(True)
    await e.wait(e.m.wo // 3)
    await e.kick()
    assert e.m.early == 1
    await e.read(STATUS, "STATUS")
    await e.read(EARLYS, "EARLYS")
    assert int(dut.LED.value) & 1 == 1, "LED[0] should hold the fault"
    await e.wait_until_c((e.m.wo + e.m.wc) // 2)
    await e.kick()                              # a good kick after the early-fault restart
    await e.check()
    assert e.m.early == 1 and e.m.late == 0
    e.check_pulses()


@cocotb.test()
async def test_late_fault_and_repeat(dut):
    e = Env(dut)
    await e.start()
    await e.enable(True)
    await e.wait(int(2.5 * (e.m.wc + 1)))      # two late faults, the third not yet due
    await e.enable(False)                      # freeze the state before reading it back
    assert e.m.late == 2
    await e.check()
    await e.wait(100)
    e.check_pulses()
    await e.b.write(STATUS, 1)
    e.m.clear()
    await e.check()
    assert int(dut.LED.value) & 1 == 0


@cocotb.test()
async def test_wrong_keys_ignored(dut):
    e = Env(dut)
    await e.start()
    await e.enable(True)
    await e.wait(e.m.wo + 300)
    for key in (0x00, 0x6A, 0xEB, 0xFF):
        await e.kick(key)                       # wrong keys inside the window do not restart the timing
    await e.wait(4000)                          # so the window closes on schedule
    await e.enable(False)
    await e.check()
    assert e.m.bad == 4 and e.m.late == 1
    e.check_pulses()
