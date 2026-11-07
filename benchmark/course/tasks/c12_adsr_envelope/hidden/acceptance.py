"""Acceptance tests of c12_adsr_envelope against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from model import ATK, DEC, DESIGN_ID, GATE, LEVEL, REL, SNAP, STATE, SUS, TICK, boundary_script, run, script

REGS = (GATE, ATK, DEC, SUS, REL)


async def play(b: Board, sc: list[list[int]], what: str, per_tick_check: bool = True) -> None:
    """Run a script tick by tick (one tick per TICK write), writing only the registers that change, and compare level and state after every tick."""
    want = run(sc)
    cur = [None] * 5
    for k, row in enumerate(sc):
        for reg, v, c in zip(REGS, row, cur):
            if v != c:
                await b.write(reg, v)
        cur = list(row)
        await b.write(TICK, 1)
        snap = await b.read(SNAP)
        got = [snap & 0xFFFF, snap >> 16]
        assert got == want[k], f"{what}: tick {k} (gate/atk/dec/sus/rel {row}): RTL level/state {got}, model {want[k]}"


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (GATE, ATK, DEC, SUS, REL, LEVEL, STATE, SNAP):
        await b.expect(off, 0, f"reset value of {off:#x}")


@cocotb.test()
async def test_course_script(dut):
    b = Board(dut, {})
    await b.start()
    await play(b, script(), "script")


@cocotb.test()
async def test_boundaries(dut):
    b = Board(dut, {})
    await b.start()
    await play(b, boundary_script(), "boundaries")


@cocotb.test()
async def test_holds_between_ticks_and_consecutive_tick_clocks(dut):
    b = Board(dut, {})
    await b.start()
    await b.write(ATK, 700)
    await b.write(DEC, 50)
    await b.write(SUS, 3000)
    await b.write(REL, 400)
    await b.write(GATE, 1)
    await b.write(TICK, 1)                       # gate rises: attack, level unchanged
    await b.expect(SNAP, 1 << 16, "after the gate rises")
    await b.cycles(300)                          # no tick: nothing moves, however long we wait
    await b.expect(SNAP, 1 << 16, "no tick, no change")
    await b.write(TICK, 5)                       # five consecutive tick clocks = five attack steps
    await b.expect(LEVEL, 3500, "five consecutive ticks")
    await b.expect(STATE, 1, "still attacking")
    await b.write(TICK, 16)                      # 16 more: 3500 + 11200 = 14700 (attack continues)
    await b.expect(LEVEL, 14700, "sixteen consecutive ticks")
    await b.write(GATE, 0)
    await b.cycles(200)
    await b.expect(SNAP, 14700 | 1 << 16, "the gate alone does nothing without a tick")
    await b.write(TICK, 1)
    await b.expect(SNAP, 14700 | 4 << 16, "release on the first tick after the gate falls")
    await b.reset()
    await b.expect(SNAP, 0, "SNAP after reset")
    await b.expect(ATK, 0, "ATK after reset")
