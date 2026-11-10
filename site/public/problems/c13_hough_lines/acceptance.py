"""Acceptance tests of c13_hough_lines against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import CLEAR, DESIGN_ID, PT, RD_CNT, RD_SEL, STATUS, accumulate, bench_pictures, read_bins


async def picture(b: Board, name: str, pts) -> None:
    await b.write(CLEAR, 1)
    for x, y in pts:
        await b.write(PT, x | y << 8)
    await b.expect(STATUS, 0, f"{name}: not busy after the last point")
    acc = accumulate(pts)
    for k, r in read_bins(acc):
        await b.write(RD_SEL, k | r << 8)
        await b.expect(RD_CNT, int(acc[k][r]), f"{name}: count of direction {k}, distance index {r}")


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (RD_SEL, STATUS):
        await b.expect(off, 0, f"reset value of {off}")


@cocotb.test()
async def test_diagonal_line(dut):
    b = Board(dut, {})
    await b.start()
    n, p = bench_pictures()[0]
    await picture(b, n, p)


@cocotb.test()
async def test_vertical_line(dut):
    b = Board(dut, {})
    await b.start()
    n, p = bench_pictures()[1]
    await picture(b, n, p)


@cocotb.test()
async def test_four_lines_then_clear(dut):
    """Several lines at once, then CLEAR and a different picture: nothing is left over."""
    b = Board(dut, {})
    await b.start()
    n, p = bench_pictures()[2]
    await picture(b, n, p)
    n2, p2 = bench_pictures()[0]
    await picture(b, n2 + " after clear", p2)


@cocotb.test()
async def test_corners_and_registers(dut):
    """Points at the picture corners reach the table edges (rho = -48 and +47 are inside), RD_SEL is a plain register."""
    b = Board(dut, {})
    await b.start()
    pts = [(0, 0), (31, 31), (31, 0), (0, 31), (16, 16)]
    await b.write(CLEAR, 1)
    for x, y in pts:
        await b.write(PT, x | y << 8)
    acc = accumulate(pts)
    for k in range(16):
        for r in (0, 1, 47, 48, 94, 95):
            await b.write(RD_SEL, k | r << 8)
            await b.expect(RD_CNT, int(acc[k][r]), f"corners: direction {k}, distance index {r}")
    await b.write(RD_SEL, 0xFFFF_FFFF)
    await b.expect(RD_SEL, 0x7F0F, "RD_SEL keeps k and r")
    led = await peek(b.clk, dut.LED)
    assert led == 0, f"LED {led:04X}: idle"
    for off in (0x05, 0x41, 0x7F):
        await b.expect(off, 0, "unmapped")
