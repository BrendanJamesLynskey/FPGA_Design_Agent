"""Acceptance tests of c15_rmsnorm_unit against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import BUDGET_LSB, DESIGN_ID, GO, OUT0, STATUS, X0, bench_inputs, lanes_to_regs, rmsnorm_float


async def run_x(b: Board, x: list[int], what: str) -> None:
    for k, w in enumerate(lanes_to_regs(x)):
        await b.write(X0 + k, w)
    await b.write(GO, 1)
    await b.expect(STATUS, 1, f"READY {what}")
    y = []
    for k in range(8):
        w = await b.read(OUT0 + k)
        for h in (w & 0xFFFF, w >> 16):
            y.append(h - 65536 if h >= 32768 else h)
    ref = rmsnorm_float(x)
    err = max(abs(v - r) for v, r in zip(y, ref))
    assert err <= BUDGET_LSB, f"{what} input {x}: worst error {err:.3f} LSB above {BUDGET_LSB}; got {y}"


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (X0, X0 + 7, STATUS, OUT0, OUT0 + 7):
        await b.expect(off, 0, f"reset value of {off:#x}")


@cocotb.test()
async def test_special_vectors(dut):
    """All zero, one LSB, full scale both signs, alternating, a constant 5, a single -1."""
    b = Board(dut, {})
    await b.start()
    for k, x in enumerate(bench_inputs()[:7]):
        await run_x(b, x, f"special {k}")


@cocotb.test()
async def test_single_large_input(dut):
    """One big number among fifteen zeros, at four lane positions."""
    b = Board(dut, {})
    await b.start()
    for k, x in enumerate(bench_inputs()[7:11]):
        await run_x(b, x, f"impulse {k}")


@cocotb.test()
async def test_random_vectors(dut):
    b = Board(dut, {})
    await b.start()
    for k, x in enumerate(bench_inputs()[11:]):
        await run_x(b, x, f"random {k}")


@cocotb.test()
async def test_registers(dut):
    b = Board(dut, {})
    await b.start()
    await run_x(b, bench_inputs()[12], "first")
    await b.write(X0 + 7, 0x12345678)
    await b.expect(X0 + 7, 0x12345678, "X7")
    await b.expect(STATUS, 1, "READY holds until the next GO")
    await b.write(OUT0, 0xFFFF)
    led = await peek(b.clk, dut.LED)
    assert led == 1, f"LED {led:04X}: only LED0 (READY) is lit"
    for off in (0x08, 0x12, 0x28, 0x7F):
        await b.expect(off, 0, "unmapped")
    await b.reset()
    await b.expect(STATUS, 0, "READY after reset")
    await b.expect(X0, 0, "X0 after reset")
