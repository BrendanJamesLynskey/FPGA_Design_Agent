"""Acceptance tests of t2_spi_master_modes against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import (BUSY, CPHA, CPOL, CS_ACTIVE, CS_HOLD, CTRL, DESIGN_ID, DIV, DONE, LOOP, LSB, RXDATA, STATUS,
                   TXDATA, W16, Model, nbits, tx_bits)
from spi_slave import SpiSlave


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"JB3": 0})
        self.dut, self.m = dut, Model()

    async def start(self) -> None:
        await self.b.start()
        self.s = SpiSlave(self.dut)

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def regs(self) -> None:
        for off, name in ((CTRL, "CTRL"), (DIV, "DIV"), (TXDATA, "TXDATA"), (RXDATA, "RXDATA"), (STATUS, "STATUS")):
            await self.b.expect(off, self.m.read(off), name)

    async def setup(self, ctrl: int, div: int) -> None:
        await self.wr(CTRL, ctrl)
        await self.wr(DIV, div)

    async def frames(self, values: list[int], miso: list[int] | None = None) -> None:
        """Send frames back to back (CS held between them if CS_HOLD) and check every pin against the model."""
        c, d = self.m.ctrl, self.m.div
        miso = miso or [0] * len(values)
        q: list[int] = []
        for v in miso:
            q += tx_bits(v, c)
        cs_was_low = self.m.cs_low
        self.s.mode(c & CPOL, (c & CPHA) >> 1, q)
        want_mosi: list[int] = []
        for v, r in zip(values, miso):
            await self.b.write(TXDATA, v)
            self.m.write(TXDATA, v)
            await self.b.cycles((2 * nbits(c) + 1) * d + 8)
            want_mosi.append(self.m.finish(tx_bits(r, c)))
        self.check_pins(want_mosi, cs_was_low)
        await self.regs()

    def check_pins(self, want_mosi: list[list[int]], cs_was_low: bool) -> None:
        c, d, s = self.m.ctrl, self.m.div, self.s
        n = nbits(c)
        cpol, cpha = c & CPOL, (c & CPHA) >> 1
        assert not s.idle_bad, s.idle_bad
        edges = s.edges
        assert len(edges) == 2 * n * len(want_mosi), f"{len(edges)} SCLK edges, model {2 * n * len(want_mosi)}"
        falls = [t for t, v in s.cs_events if v == 0]
        rises = [t for t, v in s.cs_events if v == 1]
        nf = len(want_mosi)
        if c & CS_HOLD:
            assert len(falls) == (0 if cs_was_low else 1), f"CS_N fell {len(falls)} times with CS_HOLD"
            assert not rises, "CS_N rose although CS_HOLD is set"
            if falls:
                assert d <= edges[0][0] - falls[0] <= 2 * d, f"first edge {edges[0][0] - falls[0]} clocks after CS_N fell"
        else:
            n_fall = nf - (1 if cs_was_low else 0)
            assert len(falls) == n_fall and len(rises) == nf, f"CS_N fell {len(falls)} / rose {len(rises)} times"
            for f in range(nf):
                first, last = edges[2 * n * f][0], edges[2 * n * f + 2 * n - 1][0]
                if f < len(falls) or not cs_was_low:
                    t_fall = falls[f - (1 if cs_was_low else 0)] if (f > 0 or not cs_was_low) else None
                    if t_fall is not None:
                        assert d <= first - t_fall <= 2 * d, f"frame {f}: first edge {first - t_fall} after CS_N fell"
                assert d <= rises[f] - last <= 2 * d, f"frame {f}: CS_N rose {rises[f] - last} clocks after the last edge"
        for f, want in enumerate(want_mosi):
            fe = edges[2 * n * f:2 * n * (f + 1)]
            gaps = [b[0] - a[0] for a, b in zip(fe, fe[1:])]
            assert set(gaps) == {d}, f"frame {f}: SCLK edge spacing {sorted(set(gaps))}, DIV {d}"
            levels = [lv for _, lv, _ in fe]
            assert levels == [1 - cpol, cpol] * n, f"frame {f}: SCLK levels {levels} (CPOL {cpol})"
            sampled = [mo for k, (_, _, mo) in enumerate(fe) if (k % 2) == cpha]
            assert sampled == want, f"frame {f}: MOSI at the sample edges {sampled}, model {want}"
        for a, b in zip(range(len(want_mosi) - 1), range(1, len(want_mosi))):
            gap = edges[2 * n * b][0] - edges[2 * n * a + 2 * n - 1][0]
            assert gap >= 2 * d, f"frames {a},{b}: only {gap} clocks between them"


@cocotb.test(timeout_time=1219930, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs()
    for off in (0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
    assert [await peek(e.b.clk, getattr(dut, p)) for p in ("JB1", "JB2", "JB4")] == [1, 0, 0], "idle pins"


@cocotb.test(timeout_time=1562740, timeout_unit="ns")
async def test_divisor_rule(dut):
    e = Env(dut)
    await e.start()
    for v in (1, 0, 2, 0x0001_0001, 0x0003_0007, 0xFFFF):
        await e.wr(DIV, v)
        await e.b.expect(DIV, e.m.read(DIV), f"DIV after {v:#x}")
    await e.wr(CTRL, 0xFFFF_FFC0 | LOOP)
    await e.b.expect(CTRL, e.m.read(CTRL), "CTRL")
    await e.setup(LOOP, 2)                     # the fastest SCLK, in loopback
    await e.frames([0xA6, 0x01])


@cocotb.test(timeout_time=1494720, timeout_unit="ns")
async def test_mode0_msb_first(dut):
    e = Env(dut)
    await e.start()
    await e.setup(0, 6)
    await e.frames([0x9C], [0x3A])
    await e.frames([0x00], [0xFF])
    await e.frames([0xFF], [0x81])


@cocotb.test(timeout_time=1371460, timeout_unit="ns")
async def test_mode3_idle_high(dut):
    """Trap: a mode-0-only master (the textbook's accelerometer SPI) fails here: in mode 3 SCLK idles high, MOSI
    changes on falling edges and both sides sample on rising edges."""
    e = Env(dut)
    await e.start()
    await e.setup(CPOL | CPHA, 5)
    assert await peek(e.b.clk, dut.JB4) == 1, "SCLK does not idle high in mode 3"
    await e.frames([0xC5], [0x5C])
    await e.wr(CTRL, CPOL | CPHA | W16)
    await e.frames([0x8001], [0x7FFE])


@cocotb.test(timeout_time=1793040, timeout_unit="ns")
async def test_modes_1_and_2(dut):
    e = Env(dut)
    await e.start()
    for c in (CPHA, CPOL, CPHA | LSB, CPOL | W16):
        await e.setup(c, 7)
        await e.frames([0x5A3C & (0xFFFF if c & W16 else 0xFF)], [0xC3A5 & (0xFFFF if c & W16 else 0xFF)])


@cocotb.test(timeout_time=1995720, timeout_unit="ns")
async def test_lsb_first_16bit(dut):
    e = Env(dut)
    await e.start()
    for mode in range(4):
        await e.setup(mode | LSB | W16, 5 + mode)
        await e.frames([0x1234 + mode], [0xF00D ^ mode])
    await e.setup(LSB, 6)
    await e.frames([0x0180], [0x00C1])         # an 8-bit frame uses bits [7:0] only


@cocotb.test(timeout_time=1692380, timeout_unit="ns")
async def test_cs_hold_across_frames(dut):
    e = Env(dut)
    await e.start()
    await e.setup(CS_HOLD, 5)
    assert await peek(e.b.clk, dut.JB1) == 1, "CS_HOLD alone pulled CS_N low"
    await e.regs()
    await e.frames([0x0B, 0x2D, 0x00], [0x00, 0x00, 0x02])
    assert await peek(e.b.clk, dut.JB1) == 0, "CS_N released while CS_HOLD is set"
    await e.wr(CTRL, CS_HOLD | W16)            # still held; a further 16-bit frame
    await e.frames([0xBEEF], [0x1357])
    await e.wr(CTRL, W16)                      # clear CS_HOLD: CS_N goes high
    await e.b.cycles(4)
    assert await peek(e.b.clk, dut.JB1) == 1, "clearing CS_HOLD did not release CS_N"
    await e.regs()


@cocotb.test(timeout_time=1751280, timeout_unit="ns")
async def test_busy_and_done(dut):
    e = Env(dut)
    await e.start()
    await e.setup(LOOP, 200)                    # a frame lasts 17 * 200 clocks: longer than a shell access
    await e.b.write(TXDATA, 0x6B)
    e.m.write(TXDATA, 0x6B)
    await e.b.expect(STATUS, BUSY | CS_ACTIVE, "STATUS during a frame")
    await e.b.write(TXDATA, 0x11)               # ignored while busy
    await e.b.expect(TXDATA, 0x6B, "TXDATA after a write while busy")
    await e.b.cycles(17 * 200)
    e.m.finish()
    await e.regs()
    await e.regs()                              # reading STATUS does not clear DONE
    await e.wr(STATUS, 0xFFFF_FFFD)             # bit 1 clear: DONE stays
    await e.regs()
    await e.wr(STATUS, DONE)
    await e.regs()


@cocotb.test(timeout_time=1787280, timeout_unit="ns")
async def test_loopback(dut):
    e = Env(dut)
    await e.start()
    for c in (LOOP, LOOP | CPHA | W16, LOOP | CPOL | LSB, LOOP | CPOL | CPHA | W16 | LSB):
        await e.setup(c, 3)
        dut.JB3.value = 1                        # the pin is ignored
        await e.frames([0xD25A & (0xFFFF if c & W16 else 0xFF)])
    dut.JB3.value = 0


@cocotb.test(timeout_time=2853900, timeout_unit="ns")
async def test_random_frames(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(8):
        c = rng.randrange(16) | (CS_HOLD if rng.random() < 0.3 else 0)
        await e.setup(c, rng.randrange(5, 10))
        mask = 0xFFFF if c & W16 else 0xFF
        k = rng.randrange(1, 3)
        dut._log.info(f"random frame ctrl={c:#x} div={e.m.div} k={k}")
        await e.frames([rng.randrange(1 << 16) & mask for _ in range(k)], [rng.randrange(1 << 16) & mask for _ in range(k)])
    await e.wr(CTRL, 0)
    await e.b.cycles(4)
    await e.regs()
