"""Acceptance tests of t2_pdm_vu against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from mic_model import Mic
from model import BLOCKS, CTRL, DESIGN_ID, LEVEL, ONES, PEAK, Model


def periodic(pattern: list[int]):
    return lambda j: pattern[j % len(pattern)]


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"M_DATA": 0})
        self.dut = dut
        self.half = self.b.param("CLK_HALF")
        self.w = self.b.param("WINDOW")
        self.m = Model(self.w)
        self.block_clocks = self.w * 2 * self.half

    async def start(self, bit=None) -> None:
        self.bits = bit or periodic([0, 1])
        self.mic = Mic(self.dut, lambda j: self.bits(j))      # before reset ends: it must see the first M_CLK rise
        await self.b.start()

    def advance_model(self, upto: int) -> None:
        while len(self.m.history) - 1 < upto:
            k = len(self.m.history) - 1
            self.m.block(sum(self.bits(j) for j in range(k * self.w, (k + 1) * self.w)))

    async def check_reg(self, off: int, name: str) -> None:
        """BLOCKS, the register, BLOCKS: the register must match the model at one block count in between."""
        k0 = await self.b.read(BLOCKS)
        v = await self.b.read(off)
        k1 = await self.b.read(BLOCKS)
        assert k0 <= k1 <= k0 + 3, f"BLOCKS went from {k0} to {k1}"
        self.advance_model(k1)
        ok = [k for k in range(k0, k1 + 1) if self.m.regs(k)[off] == v]
        assert ok, f"{name} = {v}, model {[self.m.regs(k)[off] for k in range(k0, k1 + 1)]} for blocks {k0}..{k1}"

    async def wait_blocks(self, n: int) -> None:
        await self.b.cycles(n * self.block_clocks)


@cocotb.test(timeout_time=1097890, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.expect(CTRL, e.m.ctrl(), "CTRL")
    for off in (0x05, 0x7F):
        await e.b.expect(off, 0, "unmapped")
    assert await peek(e.b.clk, dut.M_LRSEL) == 1


@cocotb.test(timeout_time=1003500, timeout_unit="ns")
async def test_mclk_timing(dut):
    e = Env(dut)
    await e.start()
    await e.b.cycles(40 * e.half)
    highs, lows = e.mic.highs[1:], e.mic.lows[1:]          # the first phase starts at reset
    assert highs and set(highs) == {e.half} and set(lows) == {e.half}, \
        f"M_CLK high {sorted(set(highs))} low {sorted(set(lows))}, model {e.half} each"


@cocotb.test(timeout_time=1228640, timeout_unit="ns")
async def test_lrsel_high_falling_edge(dut):
    """Trap: the textbook drives M_LRSEL low and samples at the rising edge; this spec uses the M_LRSEL = 1 channel,
    whose data is valid in the high half and taken at the falling edge (the other half carries garbage here)."""
    pat = [1, 1, 1, 0] * 4                                  # 75 % ones: ONES = 3/4 WINDOW, LEVEL = WINDOW/4
    e = Env(dut)
    await e.start(periodic(pat))
    await e.wait_blocks(2)
    assert not e.mic.lrsel_low_seen, "M_LRSEL was driven low"
    await e.check_reg(ONES, "ONES")
    await e.check_reg(LEVEL, "LEVEL")


@cocotb.test(timeout_time=2795630, timeout_unit="ns")
async def test_levels_and_leds(dut):
    e = Env(dut)
    await e.start()
    for ones_per_32 in (16, 0, 32, 20, 9):                  # density in 32-bit patterns
        pat = [1] * ones_per_32 + [0] * (32 - ones_per_32)
        start = (await e.b.read(BLOCKS) + 2) * e.w          # from a block boundary well ahead
        old = e.bits
        e.bits = (lambda p, s, o: (lambda j: p[j % 32] if j >= s else o(j)))(pat, start, old)
        await e.wait_blocks(4)
        await e.check_reg(LEVEL, "LEVEL")
        await e.check_reg(ONES, "ONES")
        e.advance_model(await e.b.read(BLOCKS))
        led = await peek(e.b.clk, dut.LED)
        assert led == e.m.history[-1]["led"], f"LED {led:016b}, model {e.m.history[-1]['led']:016b}"


@cocotb.test(timeout_time=2795630, timeout_unit="ns")
async def test_peak_hold_and_decay(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(CTRL, 0x302)                            # HOLD 2 blocks, DECAY 3
    e.m.write_ctrl(0x302)
    await e.b.expect(CTRL, 0x302, "CTRL")
    k = await e.b.read(BLOCKS) + 2
    loud = [1] * 18 + [0] * 14                              # LEVEL = WINDOW/16 (two LEDs), blocks k and k+1 only
    quiet = periodic([0, 1])
    e.bits = (lambda j: loud[j % 32] if k * e.w <= j < (k + 2) * e.w else quiet(j))
    await e.b.cycles((k + 2 - await e.b.read(BLOCKS)) * e.block_clocks)
    for _ in range(10):                                     # hold, then decay to 0
        await e.check_reg(PEAK, "PEAK")
    # a write clears PEAK: with a long hold the peak would otherwise stay
    e.advance_model(await e.b.read(BLOCKS) + 1)             # blocks so far use the old settings
    await e.b.write(CTRL, 0x1C8)                            # HOLD 200 blocks, DECAY 1
    e.m.write_ctrl(0x1C8)
    k = await e.b.read(BLOCKS) + 2
    e.bits = (lambda j: loud[j % 32] if k * e.w - 8 <= j < (k + 1) * e.w + 8 else quiet(j))   # 8 spare samples
    await e.b.cycles((k + 2 - await e.b.read(BLOCKS)) * e.block_clocks)
    await e.check_reg(PEAK, "PEAK held")
    await e.b.write(PEAK, 1)
    await e.b.expect(PEAK, 0, "PEAK after a write")
    await e.b.cycles(2 * e.block_clocks)
    await e.b.expect(PEAK, 0, "PEAK two blocks after the clear (quiet input)")


@cocotb.test(timeout_time=1481320, timeout_unit="ns")
async def test_random_stream(dut):
    rng = random.Random(int(cocotb.RANDOM_SEED))
    dens = [rng.random() for _ in range(64)]
    cache: dict[int, int] = {}

    def bit(j: int) -> int:
        if j not in cache:
            cache[j] = int(random.Random(j * 7919 + 13).random() < dens[(j // 97) % 64])
        return cache[j]

    e = Env(dut)
    await e.start(bit)
    v = rng.randrange(1 << 12)
    e.advance_model(await e.b.read(BLOCKS) + 1)
    await e.b.write(CTRL, v)
    e.m.write_ctrl(v)
    for _ in range(4):
        await e.wait_blocks(1)
        await e.check_reg(rng.choice((LEVEL, ONES, PEAK)), "register")
