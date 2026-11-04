"""Acceptance tests of p_handshake_fsm against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, align, high_runs, script
from model import ABORTS, ACK_DELAY, DESIGN_ID, FAULTS, HOLD_LIMIT, TRANSFERS, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.ad, self.hl = self.b.param("ACK_DELAY"), self.b.param("HOLD_LIMIT")
        self.m = Model(self.ad, self.hl)

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, sw=lambda: int(self.dut.SW.value) & 1, led=lambda: int(self.dut.LED.value) & 7)

    async def play(self, steps) -> None:
        await script(self.dut, "SW", steps, self.b.clk)
        await self.b.cycles(8)
        self.m = Model(self.ad, self.hl)
        trace = self.m.run(self.mon.v["sw"])
        align(self.mon.v["led"], trace, 4, "LED[2:0]")

    def bit_runs(self, bit: int) -> list[int]:
        return [n for _, n in high_runs([(v >> bit) & 1 for v in self.mon.v["led"]])]

    async def check_regs(self) -> None:
        for off, name in ((TRANSFERS, "TRANSFERS"), (ABORTS, "ABORTS"), (FAULTS, "FAULTS"), (ACK_DELAY, "ACK_DELAY"), (HOLD_LIMIT, "HOLD_LIMIT")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.play([(0, 30)])
    await e.check_regs()


@cocotb.test()
async def test_normal_handshake(dut):
    e = Env(dut)
    await e.start()
    await e.play([(1, e.ad + 10), (0, 12), (1, e.ad + 15), (0, 12)])
    assert e.bit_runs(2) == [e.ad, e.ad], f"thinking times {e.bit_runs(2)}, want {e.ad}"
    assert e.m.transfers == 2 and e.m.faults == 0
    await e.check_regs()


@cocotb.test()
async def test_abort_is_not_acknowledged(dut):
    e = Env(dut)
    await e.start()
    await e.play([(1, e.ad - 2), (0, 10), (1, 1), (0, 10), (1, e.ad + 5), (0, 10)])
    assert e.m.aborts == 2 and e.m.transfers == 1
    await e.check_regs()


@cocotb.test()
async def test_ack_timeout_fault(dut):
    e = Env(dut)
    await e.start()
    await e.play([(1, e.ad + e.hl + 60), (0, 10), (1, e.ad + 4), (0, 10)])
    assert e.m.faults == 1 and e.m.transfers == 1
    ack = e.bit_runs(0)
    assert ack[0] == e.hl, f"ACK held {ack[0]} clocks before the timeout, want {e.hl}"
    await e.check_regs()
    await e.b.write(TRANSFERS, 1)
    e.m.write(TRANSFERS, 1)
    await e.check_regs()


@cocotb.test()
async def test_random_requests(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    steps = []
    for _ in range(20):
        steps.append((1, rng.choice([1, 2, e.ad - 1, e.ad, e.ad + 1, e.ad + 8, e.ad + e.hl + 5, 3 * e.hl])))
        steps.append((0, rng.choice([1, 2, 3, 12])))
    await e.play(steps + [(0, 20)])
    await e.check_regs()
