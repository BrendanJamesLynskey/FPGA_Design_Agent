"""Acceptance tests of d20_slow_fsm_ramp against model.py (hidden from the agent). The timing constraints are graded
separately (grade_constraints.py, on the agent's routed build)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import ReadOnly, RisingEdge
from model import ACC, DESIGN_ID, GO, LEVEL, STATE, STEP, TOP, acc_of_ramp, ramp


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b = dut, Board(dut, {})
        self.log: list[tuple[int, int]] = []       # (COPY = LED[15:8], state = LED[1:0]) per rising edge
        self.mon = None

    async def start(self) -> None:
        await self.b.start()
        self.mon = cocotb.start_soon(self.watch())

    async def watch(self) -> None:
        while True:
            await RisingEdge(self.b.clk)
            await ReadOnly()
            v = int(self.dut.LED.value)
            self.log.append((v >> 8 & 0xFF, v & 0x3))
            assert v >> 2 & 0x3F == 0, f"LED[7:2] = {v >> 2 & 0x3F:#x}, must be 0"

    def take(self) -> list[tuple[int, int]]:
        out, self.log = self.log, []
        return out

    async def wait_idle(self, limit: int) -> None:
        for _ in range(limit // 16 + 2):
            await self.b.cycles(16)
            if self.log and self.log[-1] == (0, 0) and all(x == (0, 0) for x in self.log[-16:]):
                return
        raise AssertionError(f"no return to idle with COPY 0 within {limit} clocks")

    async def one_ramp(self, step: int, top: int) -> None:
        """Run one ramp from idle and check COPY's runs (values and 8-clock lengths) and the state on the LEDs."""
        await self.b.write(STEP, step)
        await self.b.write(TOP, top)
        self.take()
        await self.b.write(GO, 1)
        want = ramp(step, top)
        await self.wait_idle(8 * (len(want) + 4) + 2000)
        await self.b.cycles(24)
        log = self.take()
        runs: list[list[int]] = []                  # [value, length]
        for c, _ in log:
            if runs and runs[-1][0] == c:
                runs[-1][1] += 1
            else:
                runs.append([c, 1])
        assert runs and runs[0][0] == 0, "COPY must be 0 before the ramp"
        got = [v for v, _ in runs[1:]]
        assert got == want, f"STEP {step}, TOP {top}: COPY showed {got}, the spec gives {want}"
        lens = [n for _, n in runs[1:-1]]
        assert all(n == 8 for n in lens), f"STEP {step}, TOP {top}: COPY held its values for {lens} clocks, not 8 each"
        states = [s for _, s in log]
        assert set(states) <= {0, 1, 2}, f"state values {sorted(set(states))}"
        assert 1 in states and 2 in states, "the state never showed UP and DOWN"
        edges = [i for i in range(1, len(states)) if states[i] != states[i - 1]]
        assert all((b - a) % 8 == 0 for a, b in zip(edges, edges[1:])), f"state changes not on the tick: {edges}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off, want, what in ((STEP, 1, "STEP"), (TOP, 255, "TOP"), (STATE, 0, "STATE"), (LEVEL, 0, "LEVEL"), (ACC, 0, "ACC"),
                            (GO, 0, "GO"), (0x06, 0, "unmapped 0x06"), (0x7F, 0, "unmapped 0x7F")):
        await e.b.expect(off, want, f"{what} at reset")


@cocotb.test()
async def test_ramp_levels_and_tick_spacing(dut):
    e = Env(dut)
    await e.start()
    for step, top in ((16, 100), (1, 20), (50, 255), (7, 7), (200, 120)):
        await e.one_ramp(step, top)


@cocotb.test()
async def test_acc_sums_the_copy_every_clock(dut):
    e = Env(dut)
    await e.start()
    for step, top in ((10, 60), (3, 40), (255, 255)):
        await e.b.write(ACC, 0)
        await e.b.expect(ACC, 0, "ACC after a clear")
        await e.one_ramp(step, top)
        await e.b.expect(ACC, acc_of_ramp(step, top), f"ACC after one ramp of STEP {step}, TOP {top}")


@cocotb.test()
async def test_go_ignored_while_running_and_step_zero(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(STEP, 0)
    await e.b.expect(STEP, 1, "STEP after a write of 0")
    await e.b.write(STEP, 1)
    await e.b.write(TOP, 255)
    await e.b.write(GO, 1)
    await e.b.cycles(40)
    st = await e.b.read(STATE)
    assert st == 1, f"STATE {st} during the ramp up, want 1"
    e.take()
    await e.b.write(GO, 1)                           # ignored: not idle
    await e.wait_idle(8 * 520 + 6000)
    states = [s for _, s in e.take()]
    starts = sum(1 for a, b in zip(states, states[1:]) if a == 0 and b == 1)
    assert starts == 0, "a GO written during the ramp started a second ramp"
    await e.b.cycles(400)
    assert all(x == (0, 0) for x in e.take()), "a GO written during the ramp started a second ramp"
    await e.b.expect(STATE, 0, "STATE after the ramp")


@cocotb.test()
async def test_random_ramps(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(4):
        await e.one_ramp(rng.randrange(1, 256), rng.randrange(1, 256))
