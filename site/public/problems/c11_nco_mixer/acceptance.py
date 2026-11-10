"""Acceptance tests of c11_nco_mixer against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from model import DESIGN_ID, FW, FWS, GO, MASK, NOUT, OUT, SAMP, STATUS, VMASK, mix, stimulus


def s12(v: int) -> int:
    return v - 4096 if v & 0x800 else v


async def burst(b: Board, xs: list[int], mask: int) -> list[tuple[int, int]]:
    for k, x in enumerate(xs):
        await b.write(SAMP + k, x & 0xFFF)
    await b.write(MASK, mask)
    await b.write(GO, 1)
    for _ in range(50):
        if await b.read(STATUS) & 1:
            break
    else:
        raise AssertionError("DONE never rose")
    await b.expect(VMASK, mask, f"VMASK: a result must appear exactly one clock after each enabled clock (mask {mask:08X})")
    await b.expect(NOUT, len(xs), "NOUT")
    out = []
    for k in range(len(xs)):
        v = await b.read(OUT + k)
        out.append((s12(v & 0xFFF), s12(v >> 16 & 0xFFF)))
    return out


async def run(b: Board, fw: int, xs: list[int], rng: random.Random) -> None:
    """One run from a fresh reset: the whole sample stream in bursts of 16, compared with the model."""
    await b.reset()
    await b.write(FW, fw)
    want = mix(xs, fw)
    got: list[tuple[int, int]] = []
    for k in range(0, len(xs), 16):
        chunk = xs[k:k + 16]
        mask = sum(1 << p for p in rng.sample(range(32), len(chunk)))
        got += await burst(b, chunk, mask)
    bad = [k for k, (g, w) in enumerate(zip(got, want)) if g != w]
    assert not bad, f"fw {fw:#06x}: {len(bad)} of {len(want)} pairs differ, first at {bad[0]}: x {xs[bad[0]]}, RTL (i, q) {got[bad[0]]}, model {want[bad[0]]}"


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off, want in ((MASK, 0), (STATUS, 0), (NOUT, 0), (VMASK, 0), (FW, 0), (SAMP, 0), (OUT, 0)):
        await b.expect(off, want, f"reset value of {off:#x}")


@cocotb.test()
async def test_first_frequency_word(dut):
    b = Board(dut, {})
    await b.start()
    r = stimulus()[0]
    await run(b, r["fw"], r["x"], random.Random(int(cocotb.RANDOM_SEED)))


@cocotb.test()
async def test_second_frequency_word(dut):
    b = Board(dut, {})
    await b.start()
    r = stimulus()[1]
    await run(b, r["fw"], r["x"], random.Random(int(cocotb.RANDOM_SEED) + 1))


@cocotb.test()
async def test_consecutive_clocks_and_single_sample(dut):
    b = Board(dut, {})
    await b.start()
    await b.write(FW, 0x4000)
    xs = [1000, -1000, 2047, -2048]
    want = mix(xs + [5], 0x4000)
    got = await burst(b, xs, 0x0000000F)
    assert got == want[:4], f"consecutive clocks: RTL {got}, model {want[:4]}"
    got = await burst(b, [5], 0x80000000)
    assert got == want[4:], f"one sample at clock 31 continues the phase: RTL {got}, model {want[4:]}"
    await burst(b, [], 0)
    await b.expect(NOUT, 0, "no sample, no result")
