"""Acceptance tests of c16_montgomery_mult against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import (A_HI, A_LO, B_HI, B_LO, CLOCKS, DESIGN_ID, N_HI, N_LO, R_HI, R_LO, START, STATUS, bench_cases,
                   mont_mul)

M32 = 0xFFFFFFFF


async def product(b: Board, a: int, bb: int, n: int, what: str) -> int:
    for off, v in ((A_LO, a), (A_HI, a >> 32), (B_LO, bb), (B_HI, bb >> 32), (N_LO, n), (N_HI, n >> 32)):
        await b.write(off, v & M32)
    await b.write(START, 1)
    await b.cycles(110)
    await b.expect(STATUS, 1, f"{what}: DONE and not BUSY")
    r = await b.read(R_LO) | await b.read(R_HI) << 32
    want = mont_mul(a, bb, n)
    assert r == want, f"{what}: a=0x{a:X} b=0x{bb:X} n=0x{n:X}: RTL r=0x{r:X}, model 0x{want:X}"
    clocks = await b.read(CLOCKS)
    assert 1 <= clocks <= 100, f"{what}: {clocks} clocks (must be at most 100)"
    return clocks


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (A_LO, N_HI, STATUS, R_LO, R_HI, CLOCKS):
        await b.expect(off, 0, f"reset value of {off}")


@cocotb.test()
async def test_products_64_and_40_bit(dut):
    b = Board(dut, {})
    await b.start()
    for k, (a, bb, n) in enumerate(bench_cases()[:14]):
        await product(b, a, bb, n, f"product {k}")


@cocotb.test()
async def test_edge_operands(dut):
    """0 x 5, 1 x (n-1), (n-1) x (n-1), (n-1) x 1 modulo a 64-bit prime."""
    b = Board(dut, {})
    await b.start()
    for k, (a, bb, n) in enumerate(bench_cases()[14:18]):
        await product(b, a, bb, n, f"edge {k}")


@cocotb.test()
async def test_constant_time(dut):
    """The number of clocks is the same for every product, small and large operands, many moduli."""
    b = Board(dut, {})
    await b.start()
    seen = set()
    for k, (a, bb, n) in enumerate(bench_cases()):
        seen.add(await product(b, a, bb, n, f"timing {k}"))
    assert len(seen) == 1, f"the number of clocks depends on the data: {sorted(seen)}"


@cocotb.test()
async def test_registers_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    a, bb, n = bench_cases()[0]
    await product(b, a, bb, n, "first")
    await b.write(A_LO, 0x12345678)
    await b.expect(A_LO, 0x12345678, "A_LO")
    await b.expect(R_LO, mont_mul(a, bb, n) & M32, "r holds until the next START")
    await b.write(R_LO, 0xFFFF)
    await b.write(START, 1)
    await b.cycles(110)
    led = await peek(b.clk, dut.LED)
    assert led == 1, f"LED {led:04X}: only LED0 (DONE) is lit"
    for off in (0x0B, 0x41, 0x7F):
        await b.expect(off, 0, "unmapped")
    await b.reset()
    await b.expect(STATUS, 0, "DONE after reset")
    await b.expect(A_LO, 0, "A after reset")
