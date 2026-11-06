"""Acceptance tests of c14_int8_dot_requant against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import (ACC, A_HI, A_LO, BIAS, CTRL, DESIGN_ID, GO, MULT, STATUS, W_HI, W_LO, Y, compute, pack8,
                   vectors)


async def run_case(b: Board, c: dict, what: str = "") -> None:
    acc, y = compute(**c)
    a, w = pack8(c["a"]), pack8(c["w"])
    await b.write(A_LO, a & 0xFFFFFFFF)
    await b.write(A_HI, a >> 32)
    await b.write(W_LO, w & 0xFFFFFFFF)
    await b.write(W_HI, w >> 32)
    await b.write(BIAS, c["bias"] & 0xFFFFFFFF)
    await b.write(MULT, c["mult"])
    await b.write(CTRL, c["shift"] | c["relu"] << 8)
    await b.write(GO, 1)
    await b.expect(STATUS, 1, f"READY {what}")
    await b.expect(Y, y & 0xFF, f"Y {what} {c}")
    await b.expect(ACC, acc & 0xFFFFFFFF, f"ACC {what} {c}")


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off, want in ((A_LO, 0), (W_HI, 0), (BIAS, 0), (MULT, 0), (CTRL, 1), (Y, 0), (ACC, 0), (STATUS, 0)):
        await b.expect(off, want, f"reset value of {off}")


@cocotb.test()
async def test_random_cases(dut):
    b = Board(dut, {})
    await b.start()
    for k, c in enumerate(vectors()[:10]):
        await run_case(b, c, f"random {k}")


@cocotb.test()
async def test_extremes_halves_and_bias(dut):
    """Extreme operands (both saturations, both relu settings), exact halves of both signs, bias -1 and a large positive bias."""
    b = Board(dut, {})
    await b.start()
    for k, c in enumerate(vectors()[300:316]):
        await run_case(b, c, f"special {k}")


@cocotb.test()
async def test_tail_cases(dut):
    b = Board(dut, {})
    await b.start()
    for k, c in enumerate(vectors()[316:320]):
        await run_case(b, c, f"tail {k}")


@cocotb.test()
async def test_shift_and_mult_ranges(dut):
    """Every shift 1..31 with large and small multipliers; mult above 32767 is unsigned."""
    b = Board(dut, {})
    await b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for shift in (1, 2, 3, 5, 8, 13, 15, 16, 17, 24, 29, 30, 31):
        c = dict(a=[rng.randint(-128, 127) for _ in range(8)], w=[rng.randint(-127, 127) for _ in range(8)],
                 bias=rng.randint(-3000, 3000), mult=rng.choice((65535, 40000, 3, 32768)), shift=shift,
                 relu=rng.randint(0, 1))
        await run_case(b, c, f"shift {shift}")


@cocotb.test()
async def test_ready_clears_on_go_and_regs(dut):
    b = Board(dut, {})
    await b.start()
    c = vectors()[3]
    await run_case(b, c, "first")
    await b.write(A_LO, 0x01010101)               # operands are plain registers
    await b.expect(A_LO, 0x01010101, "A_LO")
    await b.expect(STATUS, 1, "READY holds until the next GO")
    await b.write(Y, 0x55)                         # RO: ignored
    await b.write(MULT, 0xFFFF_FFFF)
    await b.expect(MULT, 0xFFFF, "MULT keeps 16 bits")
    await b.write(CTRL, 0xFFFF_FFFF)
    await b.expect(CTRL, 0x11F, "CTRL keeps shift and relu")
    led = await peek(b.clk, dut.LED)
    assert led == 1, f"LED {led:04X}: only LED0 (READY) is lit"
    for off in (0x0B, 0x41, 0x7F):
        await b.expect(off, 0, "unmapped")
    await b.reset()
    await b.expect(STATUS, 0, "READY after reset")
    await b.expect(CTRL, 1, "CTRL after reset")
