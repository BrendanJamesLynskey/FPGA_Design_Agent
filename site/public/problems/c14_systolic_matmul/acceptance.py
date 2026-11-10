"""Acceptance tests of c14_systolic_matmul against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import (BURST, COUNT, DESIGN_ID, LAT, LOAD, RES0, ROW0, STATUS, W0, matmul, pack_row, rows, rows2, s32,
                   weights, weights2)


async def load_table(b: Board, W) -> None:
    for i in range(4):
        await b.write(W0 + i, pack_row(W[i]))
    await b.write(LOAD, 1)


async def burst(b: Board, rs, W, what: str) -> None:
    want = matmul(rs, W)
    for m, r in enumerate(rs):
        await b.write(ROW0 + m, pack_row(r))
    await b.write(BURST, len(rs))
    await b.cycles(40)
    await b.expect(STATUS, 1, f"DONE {what}")
    await b.expect(COUNT, len(rs), f"COUNT {what}")
    lat = await b.read(LAT)
    assert 1 <= lat <= 8, f"{what}: first-row latency {lat} clocks (must be 1..8)"
    for m in range(len(rs)):
        for j in range(4):
            await b.expect(RES0 + 4 * m + j, s32(want[m][j]), f"{what}: C[{m}][{j}] for row {rs[m]}")


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (W0, ROW0, STATUS, LAT, COUNT, RES0):
        await b.expect(off, 0, f"reset value of {off:#x}")


@cocotb.test()
async def test_burst_random_rows(dut):
    """16 rows on 16 consecutive clocks, then 16 more, against the first table."""
    b = Board(dut, {})
    await b.start()
    await load_table(b, weights())
    r = rows()
    await burst(b, r[0:16], weights(), "rows 0-15")
    await burst(b, r[16:32], weights(), "rows 16-31")


@cocotb.test()
async def test_burst_extreme_rows(dut):
    """-128 and 127 everywhere, zero rows and unit rows."""
    b = Board(dut, {})
    await b.start()
    await load_table(b, weights())
    await burst(b, rows()[32:40], weights(), "extreme rows")


@cocotb.test()
async def test_second_table_and_single_row(dut):
    """A new table replaces the old one; a one-row burst works; the old table can come back."""
    b = Board(dut, {})
    await b.start()
    await load_table(b, weights())
    await burst(b, rows()[0:4], weights(), "table 1")
    await load_table(b, weights2())
    await burst(b, rows2(), weights2(), "table 2")
    await burst(b, rows2()[5:6], weights2(), "one-row burst")
    await load_table(b, weights())
    await burst(b, rows()[4:8], weights(), "table 1 again")


@cocotb.test()
async def test_registers(dut):
    b = Board(dut, {})
    await b.start()
    await b.write(ROW0 + 15, 0xDEADBEEF)
    await b.expect(ROW0 + 15, 0xDEADBEEF, "ROW15")
    await b.write(W0 + 2, 0x01020304)
    await b.expect(W0 + 2, 0x01020304, "W2")
    await b.write(STATUS, 1)
    await b.expect(STATUS, 0, "STATUS is read-only")
    await load_table(b, weights())
    await burst(b, rows()[0:3], weights(), "three rows")
    led = await peek(b.clk, dut.LED)
    assert led == 1, f"LED {led:04X}: only LED0 (DONE) is lit"
    await b.write(BURST, 2)
    await b.cycles(40)
    await b.expect(COUNT, 2, "COUNT of the second burst")
    for off in (0x1C, 0x60, 0x7F):
        await b.expect(off, 0, "unmapped")
    await b.reset()
    await b.expect(STATUS, 0, "DONE after reset")
    await b.expect(RES0, 0, "results after reset")
