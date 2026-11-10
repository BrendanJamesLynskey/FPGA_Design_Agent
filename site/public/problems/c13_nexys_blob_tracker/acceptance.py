"""Acceptance tests of c13_nexys_blob_tracker against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import AREA, CX, CY, DATA, DESIGN_ID, GO, PTR, STATUS, bench_pictures, biggest, pack_words


async def report(b: Board, name: str, pic) -> None:
    await b.write(PTR, 0)
    for w in pack_words(pic):
        await b.write(DATA, w)
    await b.write(GO, 1)
    await b.cycles(1300)
    for _ in range(300):
        if not (await b.read(STATUS)) & 1:
            break
    else:
        raise AssertionError(f"{name}: still busy long after the picture")
    st = await b.read(STATUS)
    assert st & 2, f"{name}: no report available after the picture (STATUS 0x{st:X})"
    exp = biggest(pic)
    await b.expect(AREA, exp["area"], f"{name}: area of the biggest object")
    await b.expect(CX, exp["cx"], f"{name}: x of the middle point")
    await b.expect(CY, exp["cy"], f"{name}: y of the middle point")


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (PTR, STATUS, AREA, CX, CY):
        await b.expect(off, 0, f"reset value of {off}")
    await b.write(PTR, 0x25)
    await b.expect(PTR, 0x25, "PTR is a plain register")
    led = await peek(b.clk, dut.LED)
    assert led == 0, f"LED {led:04X}: idle"
    for off in (0x07, 0x41, 0x7F):
        await b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_animation_pictures(dut):
    """The eight pictures of the animation in turn: rectangle, U (one object), diagonal contact (two objects), a stray pixel, and a tie at the third."""
    b = Board(dut, {})
    await b.start()
    for name, pic in bench_pictures()[:8]:
        await report(b, name, pic)


@cocotb.test()
async def test_corner_pixel_comb_ring_and_tie(dut):
    """A single pixel in the last corner (nothing left over from the picture before), a comb and a ring (several merges), and three equal blobs (the top-left one wins)."""
    b = Board(dut, {})
    await b.start()
    await report(b, "first", bench_pictures()[3][1])
    for name, pic in bench_pictures()[8:]:
        await report(b, name, pic)


@cocotb.test()
async def test_reset_forgets_the_report(dut):
    b = Board(dut, {})
    await b.start()
    await report(b, "before reset", bench_pictures()[0][1])
    await b.reset()
    for off in (STATUS, AREA, CX, CY):
        await b.expect(off, 0, f"register {off} after reset")
