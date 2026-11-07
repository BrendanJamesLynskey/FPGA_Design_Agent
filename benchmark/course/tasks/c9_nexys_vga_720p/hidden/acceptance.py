"""Acceptance tests of c9_nexys_vga_720p against model.py (hidden from the agent).

The bench treats the clock input as the pixel clock (SIM_DIRECT_CLOCK = 1). One whole frame after the button is released is measured with edge triggers and
timed samples (benchmark/lib/vga_sampler.py), not a Python callback on every clock.
"""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from benchmark.lib.vga_sampler import edge_clock, now_clock, rgb, sample
from cocotb.triggers import Edge, First, FallingEdge, RisingEdge, Timer
from model import BAR_W, BARS, DESIGN_ID, FRAME_LINES, H_ACT, H_BP, H_SYNC, LINE, STATUS, V_ACT, V_BP, V_SYNC, colour_at

INPUTS = {"BTNC": 1, "SW": 0}


async def settled(dut, n: int = 4):
    """Wait a few clocks past Board.start (all outputs are defined by then)."""
    for _ in range(n):
        await RisingEdge(dut.CLK100MHZ)


@cocotb.test()
async def test_identity_status_and_blank_while_pressed(dut):
    b = Board(dut, dict(INPUTS))
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    await b.expect(STATUS, 1, "STATUS: video clock locked")
    assert int(dut.LED.value) & 1 == 1, "LED[0] must be lit when the video clock is stable"
    for _ in range(40):                                   # BTNC pressed since before the start
        await RisingEdge(dut.CLK100MHZ)
        assert rgb(dut) == 0, f"colour {rgb(dut):03X} while BTNC is pressed"


@cocotb.test(timeout_time=60_000_000, timeout_unit="ns")
async def test_pressing_the_button_blanks_the_picture(dut):
    """Free-running picture first (BTNC low), then BTNC pressed in the middle of a bar: the colours go to zero."""
    b = Board(dut, {"BTNC": 0, "SW": 0})
    await b.start()
    seen = False
    for _ in range(4000):
        r = await First(Edge(dut.VGA_R), Edge(dut.VGA_G), Edge(dut.VGA_B), Timer(80_000, "ns"))
        if rgb(dut) != 0:
            seen = True
            break
    assert seen, "no picture within a line and a half with BTNC low"
    for _ in range(6):
        await RisingEdge(dut.CLK100MHZ)
    assert rgb(dut) != 0, "the bar ended before the test pressed BTNC"
    dut.BTNC.value = 1
    for _ in range(16):
        await RisingEdge(dut.CLK100MHZ)
    for k in range(40):
        await RisingEdge(dut.CLK100MHZ)
        assert rgb(dut) == 0, f"colour {rgb(dut):03X} {k + 16} clocks after BTNC was pressed"
    dut.BTNC.value = 0


@cocotb.test(timeout_time=200_000_000, timeout_unit="ns")
async def test_one_frame_geometry_and_colours(dut):
    b = Board(dut, dict(INPUTS))
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    assert int(dut.VGA_HS.value) == 0 and int(dut.VGA_VS.value) == 0, "sync outputs must idle low"
    dut.BTNC.value = 0                                    # release: the raster runs
    hr0 = await edge_clock(dut.VGA_HS, rising=True)
    hf0 = await edge_clock(dut.VGA_HS, rising=False)
    hr1 = await edge_clock(dut.VGA_HS, rising=True)
    line = hr1 - hr0
    assert line == LINE, f"line period {line} pixel clocks, expected {LINE}"
    assert hf0 - hr0 == H_SYNC, f"hs width {hf0 - hr0}, expected {H_SYNC}"
    v0 = await edge_clock(dut.VGA_VS, rising=True)
    v1 = await edge_clock(dut.VGA_VS, rising=False)
    assert (v1 - v0) == V_SYNC * LINE, f"vs width {(v1 - v0) / LINE} lines, expected {V_SYNC}"
    assert (v1 - hf0) % LINE in range(0, LINE), "vs edge position"
    # picture line 0 starts 20 lines after the vs pulse ends, and its first pixel is 220 clocks after an hs pulse ended
    w0 = v1 + V_BP * LINE
    assert (w0 - hf0 - H_BP) % LINE == 0, f"first picture pixel {(w0 - hf0) % LINE} clocks after an hs pulse ended, expected {H_BP}"
    want: list[tuple[int, int, str]] = []                 # (clock, colour, what)
    want.append((v1 + (V_BP - 1) * LINE + 80, 0, "line 19 after vs (back porch)"))
    want.append((w0 - 1, 0, "pixel before the first picture pixel"))
    for x in (0, 1, 159, 160, 319, 320, 479, 480, 639, 640, 799, 800, 959, 960, 1119, 1120, 1279):
        want.append((w0 + x, colour_at(x, 0), f"line 0, x {x}"))
    want.append((w0 + H_ACT, 0, "first pixel after the picture on line 0"))
    for k in range(8):
        want.append((w0 + 360 * LINE + BAR_W * k + 80, BARS[k], f"line 360, bar {k} centre"))
        want.append((w0 + 360 * LINE + BAR_W * k, BARS[k], f"line 360, bar {k} first pixel"))
        want.append((w0 + 360 * LINE + BAR_W * (k + 1) - 1, BARS[k], f"line 360, bar {k} last pixel"))
    for dy in (719,):
        want.append((w0 + dy * LINE + 80, colour_at(80, dy), f"last picture line {dy}"))
    want.append((w0 + V_ACT * LINE + 80, 0, "line after the picture"))
    want.append((w0 + (V_ACT + 2) * LINE + 700, 0, "front porch line"))
    want.sort()
    got = await sample(dut, [c for c, _, _ in want], ("rgb",))
    bad = [(w[2], f"{g[0]:03X}", f"{w[1]:03X}") for w, g in zip(want, got) if g[0] != w[1]]
    assert not bad, f"{len(bad)} samples differ (what, RTL, expected): {bad[:6]}"
    v2 = await edge_clock(dut.VGA_VS, rising=True)
    assert v2 - v0 == FRAME_LINES * LINE, f"frame period {(v2 - v0) / LINE} lines, expected {FRAME_LINES}"
    assert int(dut.VGA_HS.value) in (0, 1)
