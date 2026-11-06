"""Acceptance tests of c15_softmax_unit against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import BUDGET, DESIGN_ID, GO, OUT0, STATUS, X0, bench_inputs, lanes_to_regs, softmax_float


async def run_x(b: Board, x: list[int], what: str) -> list[int]:
    for k, w in enumerate(lanes_to_regs(x)):
        await b.write(X0 + k, w)
    await b.write(GO, 1)
    await b.expect(STATUS, 1, f"READY {what}")
    p = []
    for k in range(4):
        w = await b.read(OUT0 + k)
        p += [w & 0xFFFF, w >> 16]
    ref = softmax_float(x)
    err = max(abs(v / 32768 - r) for v, r in zip(p, ref))
    assert err <= BUDGET, f"{what} scores {x}: worst error {err:.5f} above {BUDGET:.5f}; got {p}"
    assert abs(sum(p) / 32768 - 1) <= BUDGET, f"{what} scores {x}: probabilities sum to {sum(p) / 32768:.5f}"
    return p


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (X0, X0 + 3, STATUS, OUT0, OUT0 + 3):
        await b.expect(off, 0, f"reset value of {off:#x}")


@cocotb.test()
async def test_special_score_sets(dut):
    """All zero, one large and seven minimum, all minimum, one 1000, a ramp."""
    b = Board(dut, {})
    await b.start()
    for k, x in enumerate(bench_inputs()[:5]):
        await run_x(b, x, f"special {k}")


@cocotb.test()
async def test_random_score_sets(dut):
    b = Board(dut, {})
    await b.start()
    xs = bench_inputs()
    for k, x in enumerate(xs[5:-5]):
        await run_x(b, x, f"random {k}")


@cocotb.test()
async def test_offset_invariance(dut):
    """The same differences shifted by large offsets (the course's five shifted copies): the answer must not move."""
    b = Board(dut, {})
    await b.start()
    xs = bench_inputs()
    for k, x in enumerate(xs[-5:]):
        await run_x(b, x, f"shifted {k}")


@cocotb.test()
async def test_registers(dut):
    b = Board(dut, {})
    await b.start()
    x = bench_inputs()[7]
    await run_x(b, x, "first")
    await b.write(X0, 0x12345678)
    await b.expect(X0, 0x12345678, "X0")
    await b.expect(STATUS, 1, "READY holds until the next GO")
    await b.write(OUT0, 0xFFFF)
    led = await peek(b.clk, dut.LED)
    assert led == 1, f"LED {led:04X}: only LED0 (READY) is lit"
    for off in (0x04, 0x12, 0x24, 0x7F):
        await b.expect(off, 0, "unmapped")
    await b.reset()
    await b.expect(STATUS, 0, "READY after reset")
    await b.expect(X0, 0, "X0 after reset")
