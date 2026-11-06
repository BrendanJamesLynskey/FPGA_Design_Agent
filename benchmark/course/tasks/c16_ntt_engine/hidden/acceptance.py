"""Acceptance tests of c16_ntt_engine against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import (CYCLES, DESIGN_ID, LD_DATA, LD_PTR, RD_DATA, RD_PTR, START_FWD, START_INV, STATUS, bench_cases,
                   intt, ntt)


async def transform(b: Board, name: str, op: str, poly: list[int]) -> None:
    await b.write(LD_PTR, 0)
    for p in range(128):
        await b.write(LD_DATA, poly[2 * p] | poly[2 * p + 1] << 16)
    await b.write(START_INV if op == "inverse" else START_FWD, 1)
    await b.cycles(1250)
    await b.expect(STATUS, 2, f"{name}: DONE and not BUSY")
    cyc = await b.read(CYCLES)
    assert 100 <= cyc <= 1200, f"{name}: BUSY for {cyc} clocks (must be at most 1200)"
    want = (intt if op == "inverse" else ntt)(poly)
    await b.write(RD_PTR, 0)
    for p in range(128):
        got = await b.read(RD_DATA)
        w = want[2 * p] | want[2 * p + 1] << 16
        assert got == w, f"{name}: {op} coefficients {2 * p},{2 * p + 1}: RTL 0x{got:08X}, model 0x{w:08X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (LD_PTR, RD_PTR, STATUS, CYCLES):
        await b.expect(off, 0, f"reset value of {off}")


@cocotb.test()
async def test_forward_random(dut):
    b = Board(dut, {})
    await b.start()
    await transform(b, *bench_cases()[2])


@cocotb.test()
async def test_inverse_random(dut):
    b = Board(dut, {})
    await b.start()
    await transform(b, *bench_cases()[3])


@cocotb.test()
async def test_forward_edge_polynomials(dut):
    """A single one (the transform is all ones) and all coefficients 3328 (the largest values)."""
    b = Board(dut, {})
    await b.start()
    for c in bench_cases()[:2]:
        await transform(b, *c)


@cocotb.test()
async def test_registers_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    await b.write(LD_PTR, 5)
    await b.write(LD_DATA, 0x0123_0456)
    await b.expect(LD_PTR, 6, "LD_PTR advances per write")
    await b.write(RD_PTR, 5)
    await b.expect(RD_DATA, 0x0123_0456, "pair 5 reads back")
    await b.expect(RD_PTR, 6, "RD_PTR advances per read")
    await b.write(STATUS, 3)
    await b.expect(STATUS, 0, "STATUS is read-only")
    for off in (0x08, 0x41, 0x7F):
        await b.expect(off, 0, "unmapped")
    led = await peek(b.clk, dut.LED)
    assert led == 0, f"LED {led:04X}: idle, nothing done"
    await b.reset()
    await b.expect(LD_PTR, 0, "LD_PTR after reset")
