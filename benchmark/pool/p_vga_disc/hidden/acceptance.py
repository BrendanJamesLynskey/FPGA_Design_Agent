"""Acceptance tests of p_vga_disc against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, falling, rising
from model import COLOR, DESIGN_ID, FRAMES, Geometry, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0x0F0})
        p = self.b.param
        self.g = Geometry(p("H_ACTIVE"), p("H_FP"), p("H_SYNC"), p("H_BP"), p("V_ACTIVE"), p("V_FP"), p("V_SYNC"), p("V_BP"), p("PIX_DIV"), p("BORDER"))
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        d = self.dut
        self.mon = Monitor(self.b.clk, hs=lambda: int(d.VGA_HS.value), vs=lambda: int(d.VGA_VS.value),
                           rgb=lambda: int(d.VGA_R.value) << 8 | int(d.VGA_G.value) << 4 | int(d.VGA_B.value))

    def frame_starts(self, mark: int = 0) -> list[int]:
        hs, vs = self.mon.since("hs", mark), self.mon.since("vs", mark)
        return [i for i in falling(vs) if hs[i] == 0 and hs[i - 1] == 1]

    def check_structure(self, mark: int = 0) -> None:
        g = self.g
        hs, vs = self.mon.since("hs", mark), self.mon.since("vs", mark)
        hf = falling(hs)
        assert {b - a for a, b in zip(hf, hf[1:])} == {g.h_total * g.div}, "line length"
        hr = rising(hs)
        low = [next(r for r in hr if r > f) - f for f in hf if any(r > f for r in hr)]
        assert set(low) == {g.hs * g.div}, f"HS low time {set(low)}, want {g.hs * g.div}"
        vf = falling(vs)
        assert len(vf) >= 2, "fewer than two frames seen"
        assert {b - a for a, b in zip(vf, vf[1:])} == {g.frame_clocks}, "frame length"
        assert len(self.frame_starts(mark)) == len(vf), "VS must fall on the clock HS falls"
        vr = rising(vs)
        vlow = [next(r for r in vr if r > f) - f for f in vf if any(r > f for r in vr)]
        assert set(vlow) == {g.vs * g.h_total * g.div}, f"VS low time {set(vlow)}"

    def check_picture(self, start: int, color: int, mark: int = 0) -> None:
        g = self.g
        rgb = self.mon.since("rgb", mark)
        bad = []
        for y in range(g.va):
            for x in range(g.ha):
                t = start + g.clock_of(x, y) + g.div // 2
                if rgb[t] != g.pixel(x, y, color):
                    bad.append((x, y, rgb[t], g.pixel(x, y, color)))
        assert not bad, f"{len(bad)} wrong pixels, first (x, y, got, want): {bad[:3]}"
        # blanking: the pixel centres outside the visible area
        for ln in range(g.v_total):
            for px in range(g.h_total):
                vis = g.vs + g.vbp <= ln < g.vs + g.vbp + g.va and g.hs + g.hbp <= px < g.hs + g.hbp + g.ha
                if not vis:
                    t = start + (ln * g.h_total + px) * g.div + g.div // 2
                    assert rgb[t] == 0, f"colour {rgb[t]:03X} in the blanking at line {ln}, pixel {px}"


@cocotb.test()
async def test_identity_and_registers(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(e.g.frame_clocks)
    await e.b.expect(COLOR, 0x0F0, "COLOR")
    assert (await e.b.read(FRAMES)) >= 1


@cocotb.test()
async def test_sync_structure(dut):
    e = Env(dut)
    await e.start()
    await e.b.cycles(3 * e.g.frame_clocks + 200)
    e.check_structure()


@cocotb.test()
async def test_picture_and_blanking(dut):
    e = Env(dut)
    await e.start()
    await e.b.cycles(e.g.frame_clocks)
    mark = e.mon.mark()
    await e.b.cycles(3 * e.g.frame_clocks)
    starts = e.frame_starts(mark)
    assert starts, "no frame start seen"
    seq_len = len(e.mon.since("rgb", mark))
    s = next(s for s in starts if s + e.g.frame_clocks <= seq_len)
    e.check_picture(s, 0x0F0, mark)
    led = int(dut.LED.value)
    assert led == 0x0F0, f"LED {led:04X}"


@cocotb.test()
async def test_colour_changes_only_at_a_frame_start(dut):
    e = Env(dut)
    await e.start()
    await e.b.cycles(2 * e.g.frame_clocks)
    mark = e.mon.mark()
    dut.SW.value = 0xA5C                              # not synchronised with the frame: lands mid-frame
    await e.b.cycles(4 * e.g.frame_clocks)
    starts = [s for s in e.frame_starts(mark) if s + e.g.frame_clocks <= len(e.mon.since("rgb", mark))]
    assert len(starts) >= 2
    colours = []
    for s in starts:
        rgb = e.mon.since("rgb", mark)
        seen = {rgb[s + e.g.clock_of(32, 24) + e.g.div // 2]}
        for (x, y) in ((32 + 8, 24), (32 - 8, 24), (32, 24 + 8), (32, 24 - 8)):
            seen.add(rgb[s + e.g.clock_of(x, y) + e.g.div // 2])
        assert len(seen) == 1, f"a split-colour disc in the frame starting at {s}: {seen}"
        colours.append(seen.pop())
    assert colours[-1] == 0xA5C and colours[0] in (0x0F0, 0xA5C) and colours == sorted(colours, key=lambda c: c == 0xA5C), colours
    for s in starts:
        e.check_picture(s, colours[starts.index(s)], mark)


@cocotb.test()
async def test_random_colours(dut):
    import random
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(2):
        c = rng.randrange(1, 4096)
        dut.SW.value = c
        await e.b.cycles(2 * e.g.frame_clocks + rng.randrange(1000))
        mark = e.mon.mark()
        await e.b.cycles(2 * e.g.frame_clocks)
        n = len(e.mon.since("rgb", mark))
        s = next(s for s in e.frame_starts(mark) if s + e.g.frame_clocks <= n)
        e.check_picture(s, c, mark)
