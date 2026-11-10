"""Acceptance tests of c13_nexys_harris_vga against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board, peek
from model import COUNT, CORNER, DATA, DESIGN_ID, GO, PTR, SEL, STATUS, bench_pictures, check_corners, corners, pack_words


async def run_picture(b: Board, dut, name: str, img) -> None:
    exp = corners(img)
    await b.write(PTR, 0)
    for w in pack_words(img):
        await b.write(DATA, w)
    await b.write(GO, 1)
    await b.cycles(4800)
    for _ in range(600):
        if not (await b.read(STATUS)) & 1:
            break
    else:
        raise AssertionError(f"{name}: still busy long after the picture")
    st = await b.read(STATUS)
    assert st & 2, f"{name}: no list available after the picture (STATUS 0x{st:X})"
    n = await b.read(COUNT)
    got = []
    for i in range(min(n, 64)):
        await b.write(SEL, i)
        v = await b.read(CORNER)
        got.append((v & 0x7F, (v >> 8) & 0x7F))
    why = check_corners(got, exp)
    assert not why, f"{name}: " + "; ".join(why) + f" (reported {got}, true {[tuple(c) for c in exp]})"
    assert n == len(got), f"{name}: the count is {n} but {len(got)} corners were readable"
    led = await peek(b.clk, dut.LED)
    assert led == n, f"{name}: LEDs show {led}, the count is {n}"


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off in (PTR, STATUS, COUNT, SEL, CORNER):
        await b.expect(off, 0, f"reset value of {off}")
    await b.write(PTR, 0x4AF)
    await b.expect(PTR, 0x4AF, "PTR is a plain register")
    led = await peek(b.clk, dut.LED)
    assert led == 0, f"LED {led:04X}: no corners yet"
    for off in (0x07, 0x41, 0x7F):
        await b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_course_picture_then_mixed_picture(dut):
    """The two bright rectangles of the course picture: eight corners, one detection each; then a different picture with strong, weak and edge-touching rectangles (the weak one has none)."""
    b = Board(dut, {})
    await b.start()
    for name, img in bench_pictures():
        await run_picture(b, dut, name, img)


@cocotb.test()
async def test_reset_forgets_the_list(dut):
    b = Board(dut, {})
    await b.start()
    await run_picture(b, dut, "before reset", bench_pictures()[0][1])
    await b.reset()
    for off in (STATUS, COUNT, SEL, CORNER):
        await b.expect(off, 0, f"register {off} after reset")
    led = await peek(b.clk, dut.LED)
    assert led == 0, f"LED {led:04X} after reset"
