"""cocotb bench for a generated custom-instruction wrapper (hwsw/cfu.py) on its own, around ip_lib/crc32_step. The
bench plays the pipeline: one instruction at a time in EX, start held until the result is taken, hold (a memory stall)
and kill (an EX flush) at random, never both in one clock, as the BRV32P core drives them. Its operands are right only
on the instruction's first clock in EX; on every later clock the bench drives other values, as a core's forwarding
path may show a stale value once EX is held. Each result taken must equal the model's for the first-clock operands.

The core never reaches some of these sequences (a retry inside the unit's latency after a kill: a trap handler takes
longer), so this bench is where the wrapper's in-flight logic is tested. Environment: CFU_LATENCY (the variant's
latency), CFU_OPS (instructions in the random soak, default 3000)."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from ip_lib.crc32_step.model import crc32_word

LAT = int(os.environ.get("CFU_LATENCY", "1"))
OPS = int(os.environ.get("CFU_OPS", "3000"))


async def _reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("start", "hold", "kill", "funct3", "funct7", "a", "b"):
        getattr(dut, s).value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


class Pipe:
    """Drives the wrapper one clock at a time and checks every result taken. Counts the cases that matter."""

    def __init__(self, dut, rng: random.Random):
        self.d, self.rng = dut, rng
        self.n = {"taken": 0, "killed_before_start": 0, "killed_in_flight": 0, "killed_result_held": 0,
                  "starts_delayed": 0, "held_results": 0}

    async def clock(self, ins: dict | None, kill: bool, hold: bool) -> str:
        """One clock with `ins` in EX (or none). Returns 'taken', 'killed', 'wait' or 'idle'."""
        d = self.d
        assert not (kill and hold), "the core never kills during a memory stall"
        d.start.value = 1 if ins else 0
        if ins:
            first = ins["clocks"] == 0
            d.a.value = ins["a"] if first else self.rng.getrandbits(32)     # stale forwarding after the first clock
            d.b.value = ins["b"] if first else self.rng.getrandbits(32)
        else:
            d.a.value, d.b.value = self.rng.getrandbits(32), self.rng.getrandbits(32)
        d.kill.value = int(kill)
        d.hold.value = int(hold)
        await ReadOnly()
        busy, valid = int(d.busy.value), int(d.valid.value)
        active, inflight = int(d.active.value), int(d.inflight.value)
        out = "idle"
        if ins:
            assert busy != valid, f"start high but busy={busy} valid={valid}"
            if kill:
                key = ("killed_before_start" if not active else
                       "killed_in_flight" if inflight else "killed_result_held")
                self.n[key] += 1
                out = "killed"
            elif valid and not hold:
                want = crc32_word(ins["a"], ins["b"])
                got = int(d.result.value)
                assert got == want, f"result 0x{got:08x}, want 0x{want:08x} for a=0x{ins['a']:08x} b=0x{ins['b']:08x}"
                if ins.get("held_value") is not None:
                    assert got == ins["held_value"], "result changed while hold was high"
                self.n["taken"] += 1
                out = "taken"
            else:
                if valid and hold:
                    if ins.get("held_value") is None:
                        self.n["held_results"] += 1
                    ins["held_value"] = int(d.result.value)
                if not active and inflight:
                    self.n["starts_delayed"] += 1
                out = "wait"
            ins["clocks"] += 1
            assert ins["clocks"] < 4 * LAT + 50, "instruction never completed"
        await FallingEdge(d.clk)
        return out


def _new(rng):
    return {"a": rng.getrandbits(32), "b": rng.getrandbits(32), "clocks": 0, "held_value": None}


@cocotb.test()
async def kill_then_quick_retry(dut):
    """Directed: start an operation, kill it one clock later, and issue the next instruction in the very next clock.
    For a multi-cycle unit the retry must wait for the killed operation, then compute on its own first-clock operands
    (the bench drives other values on every later clock)."""
    await _reset(dut)
    rng = random.Random(1)
    p = Pipe(dut, rng)
    for gap in range(0, LAT + 2):
        for kill_at in range(1, LAT + 1):
            ins = _new(rng)
            for _ in range(kill_at):
                assert await p.clock(ins, False, False) == "wait" or LAT == 1
            assert await p.clock(ins, True, False) == "killed"
            for _ in range(gap):
                await p.clock(None, False, False)
            ins = _new(rng)
            while await p.clock(ins, False, False) != "taken":
                pass
    assert p.n["taken"] == (LAT + 2) * LAT
    if LAT > 1:
        assert p.n["starts_delayed"] > 0 and p.n["killed_in_flight"] > 0, p.n
    dut._log.info(f"directed: {p.n}")


@cocotb.test()
async def random_soak(dut):
    """Random instructions back to back or with gaps, with random hold and kill, every result checked."""
    await _reset(dut)
    rng = random.Random(int(os.environ.get("CFU_SEED", "64")))
    p = Pipe(dut, rng)
    ins = None
    for _ in range(OPS * (LAT + 3)):
        if ins is None and rng.random() < 0.85:
            ins = _new(rng)
        kill = ins is not None and rng.random() < 0.12
        hold = not kill and rng.random() < 0.3
        r = await p.clock(ins, kill, hold)
        if r in ("taken", "killed"):
            ins = None
    dut._log.info(f"soak: {p.n}")
    assert p.n["taken"] > OPS // 2
    assert p.n["killed_before_start"] and p.n["killed_in_flight"] and p.n["held_results"], p.n
    if LAT > 1:
        assert p.n["starts_delayed"] and p.n["killed_result_held"], p.n
