"""Acceptance tests of c9_median3x3 against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from model import DESIGN_ID, GO, MASK, MED, NOUT, STATUS, VMASK, WIN, median, pack_win, windows


def mask_of(n: int, rng: random.Random, style: str) -> int:
    if style == "run":
        return (1 << n) - 1
    if style == "alt":
        return sum(1 << (2 * k + 1) for k in range(n))
    return sum(1 << p for p in rng.sample(range(32), n))


async def burst(b: Board, ws: list[list[int]], mask: int) -> list[int]:
    for k, w in enumerate(ws):
        for r, word in enumerate(pack_win(w)):
            await b.write(WIN + 3 * k + r, word)
    await b.write(MASK, mask)
    await b.write(GO, 1)
    for _ in range(50):
        if await b.read(STATUS) & 1:
            break
    else:
        raise AssertionError("DONE never rose")
    await b.expect(VMASK, mask, f"VMASK: results must appear exactly one clock after the windows (mask {mask:08X})")
    await b.expect(NOUT, len(ws), "NOUT")
    return [await b.read(MED + k) for k in range(len(ws))]


async def check_windows(b: Board, ws, mask: int, what: str) -> None:
    got = await burst(b, ws, mask)
    for k, (w, g) in enumerate(zip(ws, got)):
        assert g == median(w), f"{what}: window {w}: RTL median {g}, expected {median(w)}"


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off, want in ((MASK, 0), (STATUS, 0), (NOUT, 0), (VMASK, 0), (WIN, 0), (WIN + 23, 0), (MED, 0)):
        await b.expect(off, want, f"reset value of {off:#x}")


@cocotb.test()
async def test_all_windows_with_gaps(dut):
    b = Board(dut, {})
    await b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    ws = windows()
    for k in range(0, len(ws), 8):
        chunk = ws[k:k + 8]
        await check_windows(b, chunk, mask_of(len(chunk), rng, ("run", "alt", "rand", "rand")[k // 8 % 4]), f"block {k // 8}")


@cocotb.test()
async def test_every_position_of_the_median(dut):
    """The median sits at each of the nine positions in turn (distinct values), so a network that mis-wires one input cannot hide."""
    b = Board(dut, {})
    await b.start()
    base = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    ws = []
    for pos in range(9):
        w = base[:]
        w[pos], w[4] = w[4], w[pos]          # the median value 50 at position `pos`
        ws.append(w)
    await check_windows(b, ws[:8], 0x000000FF, "median position 0..7")
    await check_windows(b, ws[8:] + [base[::-1]], 0x00000003, "median position 8 and reversed")


@cocotb.test()
async def test_latency_and_no_extra_results(dut):
    b = Board(dut, {})
    await b.start()
    w = [[3, 200, 9, 7, 100, 1, 254, 128, 64]]
    await check_windows(b, w, 0x00000001, "window at clock 0")
    await check_windows(b, w, 0x80000000, "window at clock 31")
    await burst(b, [], 0)
    await b.expect(NOUT, 0, "no window, no result")
    await b.reset()
    for off in (STATUS, NOUT, VMASK, MED, WIN):
        await b.expect(off, 0, f"{off:#x} after reset")
