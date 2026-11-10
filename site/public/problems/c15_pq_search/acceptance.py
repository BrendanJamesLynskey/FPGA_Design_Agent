"""Acceptance tests of c15_pq_search against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import BURST, CODE, DESIGN_ID, RES_D, RES_I, START, STATUS, TADDR, TDATA, bench_queries


async def load_table(b: Board, table) -> None:
    await b.write(TADDR, 0)
    for g in range(8):
        for c in range(16):
            await b.write(TDATA, table[g][c])


async def run_query(b: Board, table, entries, want, what: str) -> None:
    await load_table(b, table)
    await b.expect(TADDR, 128 & 0x7F, "TADDR advanced past the table")
    await b.write(START, 1)
    for c in range(0, len(entries), 16):
        chunk = entries[c:c + 16]
        for k, e in enumerate(chunk):
            await b.write(CODE + k, e)
        last = c + 16 >= len(entries)
        await b.write(BURST, len(chunk) | (0x100 if last else 0))
        await b.cycles(len(chunk) + 12)
        if not last:
            await b.expect(STATUS, 0, f"{what}: DONE must stay low before the last entry")
    await b.expect(STATUS, 1, f"{what}: DONE")
    for k in range(8):
        if k < len(want):
            await b.expect(RES_D + k, 1 << 24 | want[k][0], f"{what}: place {k} distance")
            await b.expect(RES_I + k, want[k][1], f"{what}: place {k} entry")
        else:
            await b.expect(RES_D + k, 0, f"{what}: place {k} unfilled")


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (TADDR, STATUS, RES_D, RES_I + 7):
        await b.expect(off, 0, f"reset value of {off:#x}")


@cocotb.test()
async def test_first_query(dut):
    b = Board(dut, {})
    await b.start()
    t, e, w = bench_queries()[0]
    await run_query(b, t, e, w, "query 0")


@cocotb.test()
async def test_second_query_after_first(dut):
    """START forgets the first result and restarts the numbering; the table is replaced."""
    b = Board(dut, {})
    await b.start()
    qs = bench_queries()
    await run_query(b, *qs[0], "query 0")
    await run_query(b, *qs[1], "query 1")


@cocotb.test()
async def test_equal_distances_and_short_database(dut):
    """Every distance equal (order by entry number) and a database of 20 entries (two bursts)."""
    b = Board(dut, {})
    await b.start()
    await run_query(b, *bench_queries()[2], "equal distances")


@cocotb.test()
async def test_short_query_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    t, e, w = bench_queries()[1]
    await run_query(b, t, e[:5], [p for p in __import__("model").top_of(t, e[:5])], "five entries")
    led = await peek(b.clk, dut.LED)
    assert led & 3 == 1, f"LED {led:04X}: LED0 (DONE) lit, LED1 (BUSY) dark"
    await b.reset()
    await b.expect(STATUS, 0, "DONE after reset")
    await b.expect(RES_D, 0, "result after reset")
    for off in (0x03, 0x50, 0x7F):
        await b.expect(off, 0, "unmapped")
