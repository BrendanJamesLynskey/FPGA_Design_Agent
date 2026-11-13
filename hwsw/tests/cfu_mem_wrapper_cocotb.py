"""cocotb bench for the MEM-completion style of the generated custom-instruction wrapper (hwsw/cfu.py --style mem) on
its own, around ip_lib/crc32_step. The bench plays the BRV32P pipeline from EX to MEM: an instruction leaves EX (issue,
with its operands) only in a clock in which MEM is not held (neither by the unit's own stall nor by another stall,
`hold`); it is then in MEM until a clock with neither, when its result is taken and checked against the model. Other
MEM stalls (`hold`) come at random, so results also arrive while MEM is held. Instructions come back to back (an issue
in the clock the one before leaves MEM) or with gaps. Operands are driven only in the issue clock; on every other clock
the bench drives other values, so a unit that read them late would be caught.

Environment: CFU_LATENCY (the variant's latency), CFU_OPS (instructions in the random soak, default 3000)."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, Timer

from ip_lib.crc32_step.model import crc32_word

LAT = int(os.environ.get("CFU_LATENCY", "1"))
OPS = int(os.environ.get("CFU_OPS", "3000"))


async def _reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("issue", "in_mem", "hold", "funct3", "funct7", "a", "b"):
        getattr(dut, s).value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1


async def run(dut, rng: random.Random, n_ins: int, p_new: float, p_hold: float) -> dict:
    """n_ins instructions through EX and MEM; returns counts of the cases that matter."""
    n = {"taken": 0, "back_to_back": 0, "result_under_hold": 0, "stall_clocks": 0}
    mem = None                                    # the instruction in MEM: its expected result
    issued = 0
    while n["taken"] < n_ins:
        hold = rng.random() < p_hold
        dut.in_mem.value = int(mem is not None)
        dut.hold.value = int(hold)
        dut.issue.value = 0
        dut.a.value, dut.b.value = rng.getrandbits(32), rng.getrandbits(32)
        await Timer(1, unit="ns")                 # let stall settle (it depends on in_mem)
        stall = int(dut.stall.value)
        if mem is not None and stall:
            n["stall_clocks"] += 1
        mem_held = mem is not None and (stall or hold)
        leaving = mem is not None and not mem_held
        new = None
        if issued < n_ins and not stall and not hold and rng.random() < p_new:   # EX moves on only without a MEM stall
            a, b = rng.getrandbits(32), rng.getrandbits(32)
            dut.issue.value, dut.a.value, dut.b.value = 1, a, b
            new = crc32_word(a, b)
            issued += 1
            n["back_to_back"] += leaving
        await ReadOnly()
        if mem is not None:
            if leaving:
                got = int(dut.result.value)
                assert got == mem, f"result 0x{got:08x}, want 0x{mem:08x}"
                n["taken"] += 1
            elif hold and not stall:
                n["result_under_hold"] += 1
        if leaving:
            mem = None
        if new is not None:
            mem = new
        await FallingEdge(dut.clk)
    return n


@cocotb.test()
async def back_to_back_and_gaps(dut):
    """Directed: instructions back to back with no other stall, then with one-clock gaps; the unit holds MEM for
    exactly latency - 1 clocks per instruction."""
    await _reset(dut)
    rng = random.Random(1)
    n = await run(dut, rng, 50, 1.0, 0.0)
    assert n["stall_clocks"] == 50 * (LAT - 1), n
    assert n["back_to_back"] == 49, n
    n = await run(dut, rng, 50, 0.5, 0.0)
    dut._log.info(f"directed: {n}")


@cocotb.test()
async def random_soak(dut):
    """Random issue and random other MEM stalls, every result checked."""
    await _reset(dut)
    rng = random.Random(int(os.environ.get("CFU_SEED", "64")))
    n = await run(dut, rng, OPS, 0.8, 0.3)
    dut._log.info(f"soak: {n}")
    assert n["back_to_back"] and n["result_under_hold"], n
