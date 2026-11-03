"""Acceptance tests of t2_vga_sprite against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.lib.vga_sampler import edge_clock, now_clock, sample
from model import (BG_COLOR, BOUNCE, CPP, CTRL, DESIGN_ID, DX_NEG, DY_NEG, EN, FRAME, FRAME_CLOCKS, HS_START, HSW,
                   HT, LINE, SPRITE_COLOR, VS_START, VSW, VT, X, Y, Model)

ARROW = [0x8000, 0xC000, 0xE000, 0xF000, 0xF800, 0xFC00, 0xFE00, 0xFF00, 0xFF80, 0xFC00, 0xEC00, 0xC600, 0x8600,
         0x0300, 0x0300, 0x0181]


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut)
        self.dut, self.m = dut, Model()

    async def start(self) -> None:
        await self.b.start()
        self.t_release = now_clock() - 8               # Board.start waits 8 clocks after releasing reset
        self.t0 = await edge_clock(self.dut.VGA_HS, rising=False)   # HS fall (sync start) of line 0
        self.line0 = self.t0 - CPP * HS_START

    def clock_of(self, x: int, y: int, frame: int = 0) -> int:
        return self.line0 + frame * FRAME_CLOCKS + y * LINE + CPP * x

    def next_line(self, margin: int = 50) -> tuple[int, int]:
        k = (now_clock() + margin - self.line0 + LINE - 1) // LINE
        return k // VT, k % VT

    def ahead(self, k: int) -> int:
        """A line of the current frame at least ``k`` lines ahead (the tests stay in the top of the frame)."""
        _, y = self.next_line()
        assert y + k + 20 < 470, f"test ran too far down the frame (line {y})"
        return y + k

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def load(self, rows: list[int]) -> None:
        for i, r in enumerate(rows):
            await self.wr(i, r)

    async def regs(self, offs=(X, Y, CTRL, FRAME)) -> None:
        for off in offs:
            await self.b.expect(off, self.m.read(off), f"window 0x{off:02X}")

    async def check_line(self, frame: int, y: int, xs) -> None:
        xs = list(xs)
        got = await sample(self.dut, [self.clock_of(x, y, frame) + 2 for x in xs], ("rgb", "VGA_HS", "VGA_VS"))
        want = [(self.m.pixel(x, y), self.m.hs(x), self.m.vs(y)) for x in xs]
        bad = [(x, g, w) for x, g, w in zip(xs, got, want) if g != w]
        assert not bad, f"line {y}: {len(bad)} pixels differ, first (x, rtl (rgb, hs, vs), model) = {bad[:4]}"

    async def check_lines(self, ys, xs) -> None:
        """Lines ``ys`` of the next frame whose line min(ys) is still ahead."""
        f, y = self.next_line()
        frame = f if y <= min(ys) else f + 1
        for yy in ys:
            await self.check_line(frame, yy, xs)

    async def wait_frame_wrap(self) -> int:
        """Wait until just after the next frame wrap (the model's bounce update); returns the new frame index."""
        f = (now_clock() - self.line0) // FRAME_CLOCKS
        target = self.clock_of(0, 0, f + 1) + 8
        await self.b.cycles(target - now_clock())
        self.m.frame_wrap()
        return f + 1


@cocotb.test(timeout_time=1662700, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs(list(range(0x16)) + [0x16, 0x7F])
    assert 0 <= e.line0 - e.t_release <= 16, f"pixel (0, 0) starts {e.line0 - e.t_release} clocks after reset"


@cocotb.test(timeout_time=1256164, timeout_unit="ns")
async def test_sync_timing(dut):
    e = Env(dut)
    await e.start()
    t_rise = await edge_clock(dut.VGA_HS)
    assert t_rise - e.t0 == CPP * HSW, f"HS low for {t_rise - e.t0} clocks, model {CPP * HSW}"
    t1 = await edge_clock(dut.VGA_HS, rising=False)
    assert t1 - e.t0 == LINE, f"line period {t1 - e.t0} clocks, model {LINE}"
    await e.check_line(0, 3, range(600, HT, 2))


@cocotb.test(timeout_time=30000000, timeout_unit="ns")
async def test_sprite_bitmap(dut):
    e = Env(dut)
    await e.start()
    await e.load(ARROW)
    await e.wr(SPRITE_COLOR, 0xF80)
    await e.wr(BG_COLOR, 0x123)
    await e.wr(X, 37)
    y0 = e.ahead(6)
    await e.wr(Y, y0)
    await e.check_lines(range(y0 - 2, y0 + 18), range(30, 60))
    await e.check_lines([y0 + 1], range(0, 640, 3))


@cocotb.test(timeout_time=4418220, timeout_unit="ns")
async def test_clipping_and_enable(dut):
    e = Env(dut)
    await e.start()
    await e.load([0xFFFF] * 16)
    await e.wr(BG_COLOR, 0x0A0)
    await e.wr(X, 632)                               # half off the right edge
    y0 = e.ahead(3)
    await e.wr(Y, y0)
    await e.check_lines([y0, y0 + 7, y0 + 15, y0 + 16], range(620, 660))
    await e.wr(X, 1016)                              # completely off screen (no wrap to the left edge)
    await e.check_lines([e.ahead(1)], list(range(0, 16)) + list(range(16, 800, 4)))
    await e.wr(X, 0)                                 # at the left edge
    y0 = e.ahead(3)
    await e.wr(Y, y0)
    await e.check_lines([y0, y0 + 15, y0 + 16], range(0, 20))
    await e.wr(CTRL, 0)                              # sprite off
    await e.check_lines([max(y0 + 3, e.ahead(1))], range(0, 20))
    await e.regs((CTRL,))


@cocotb.test(timeout_time=22000000, timeout_unit="ns")
async def test_bounce_and_vertical_timing(dut):
    """One frame wrap: the bounce turns at the right limit (X >= 624) and at the top (Y = 0); on the way, the bottom
    lines (background, then black) and VS timing. (A frame is 1.68 M clocks: one wrap keeps the test short.)"""
    e = Env(dut)
    await e.start()
    await e.load(ARROW)
    await e.wr(X, 624)
    await e.wr(Y, 0)
    await e.wr(CTRL, EN | BOUNCE | DY_NEG)
    await e.check_line(0, 479, range(600, 660, 3))
    await e.check_line(0, 480, range(0, HT, 9))
    t_vs = await edge_clock(dut.VGA_VS, rising=False)
    assert t_vs == e.clock_of(0, VS_START), f"VS fell at clock {t_vs - e.line0} of the frame, model {VS_START * LINE}"
    t_end = await edge_clock(dut.VGA_VS)
    assert t_end - t_vs == VSW * LINE, f"VS low for {t_end - t_vs} clocks, model {VSW * LINE}"
    await e.check_line(0, 500, range(0, HT, 9))
    for _ in range(1):                                  # both turn: (623, 1), moving left and down
        f = await e.wait_frame_wrap()
        await e.regs()
        await e.check_line(f, e.m.y + 1, range(616, 642))
    assert e.m.x == 623 and e.m.y == 1 and e.m.ctrl == EN | BOUNCE | DX_NEG


@cocotb.test(timeout_time=24000000, timeout_unit="ns")
async def test_offscreen_and_disabled_inside_sprite_span(dut):
    """v1.1: lines that the sprite would cover (Y .. Y + 15), with it far off to the right (X = 1016 and 1023: no wrap
    to the left edge) and with CTRL.EN = 0. The v1 tests looked at a line after the sprite's span, where nothing is
    drawn whatever the design does."""
    e = Env(dut)
    await e.start()
    await e.load([0xFFFF] * 16)
    await e.wr(SPRITE_COLOR, 0xF00)
    await e.wr(BG_COLOR, 0x0A0)
    y0 = e.ahead(3)
    await e.wr(Y, y0)
    await e.wr(X, 1016)
    await e.check_lines([y0 + 3], list(range(0, 24)) + list(range(600, 640, 5)))
    await e.wr(X, 1023)
    await e.check_lines([y0 + 6], list(range(0, 24)) + list(range(600, 640, 5)))
    await e.wr(X, 100)
    await e.check_lines([y0 + 8], range(96, 120))                 # on screen and enabled: the sprite is there
    await e.wr(CTRL, 0)                                          # sprite off: background only
    await e.check_lines([y0 + 10], range(96, 120))
    await e.check_lines([y0 + 13], range(96, 120))
    await e.regs((CTRL, X, Y))


@cocotb.test(timeout_time=24000000, timeout_unit="ns")
async def test_bounce_turns_at_left_and_bottom(dut):
    """v1.1: one frame wrap at X = 0 moving left and Y = 464 moving down: both turn (X to 1, Y to 463). With no turn at
    X = 0 the position would wrap to 1023."""
    e = Env(dut)
    await e.start()
    await e.load(ARROW)
    await e.wr(X, 0)
    await e.wr(Y, 464)
    await e.wr(CTRL, EN | BOUNCE | DX_NEG)
    await e.regs((X, Y, CTRL))
    await e.wait_frame_wrap()
    await e.regs()
    assert e.m.x == 1 and e.m.y == 463 and e.m.ctrl == EN | BOUNCE | DY_NEG


@cocotb.test(timeout_time=24000000, timeout_unit="ns")
async def test_blank_lines_are_black_over_a_background(dut):
    """v1.1: with a non-zero background colour, every pixel of lines 480-524 and every pixel right of column 639 is
    black (the v1 tests ran with the reset background colour, black, so a background leaking into the blanking could
    not show)."""
    e = Env(dut)
    await e.start()
    await e.wr(BG_COLOR, 0x321)
    await e.check_lines([479], range(0, HT, 37))
    await e.check_lines([480, 497, 524], sorted(set(range(0, HT, 37)) | {0, 1, 639, 640, 799}))


@cocotb.test(timeout_time=7267580, timeout_unit="ns")
async def test_random_sprites(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.load([rng.randrange(1 << 16) for _ in range(16)])
    for _ in range(4):
        await e.wr(X, rng.choice([rng.randrange(0, 640), rng.randrange(620, 650)]))
        await e.wr(SPRITE_COLOR, rng.randrange(1 << 12))
        await e.wr(BG_COLOR, rng.randrange(1 << 12))
        await e.wr(rng.randrange(16), rng.randrange(1 << 16))
        await e.wr(Y, e.ahead(3) + rng.randrange(0, 8))
        ys = sorted(rng.sample(range(e.m.y, e.m.y + 16), 3))
        await e.check_lines(ys, range(max(0, e.m.x - 4), min(HT, e.m.x + 20)))
    await e.regs((ROW for ROW in range(16)))
