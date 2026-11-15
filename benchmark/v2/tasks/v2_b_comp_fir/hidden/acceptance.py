"""Acceptance tests of v2_b_comp_fir against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from model import COEF, CTRL, DESIGN_ID, NEXT, RESULT, SAMPLE, STATUS, Model


class Env_cf:
    def __init__(self, dut) -> None:
        self.b, self.m = Board(dut, {}), Model()

    async def wr_cf(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def feed_cf(self, xs, every: int = 1) -> None:
        """Write the samples; after each ``every`` of them compare_cf and pop all queued results."""
        for i, x in enumerate(xs, 1):
            await self.wr_cf(SAMPLE, x)
            if i % every == 0:
                await self.drain_cf(f"after sample {i} ({x})")

    async def drain_cf(self, what: str) -> None:
        await self.b.expect(STATUS, self.m.read(STATUS), "STATUS " + what)
        while self.m.q_cf:
            await self.b.expect(RESULT, self.m.read(RESULT), "RESULT " + what)
            await self.wr_cf(NEXT, 0)


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env_cf(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, 0, "register at reset")
    await e.feed_cf([30000, -30000, 30000])
    await e.b.reset()
    e.m = Model()
    await e.b.expect(STATUS, 0, "STATUS after reset")
    await e.feed_cf([1000, 0, 0, 0, 0, 0, 0, 0, 0, 0], every=1)


@cocotb.test()
async def test_impulse_gives_the_coefficients(dut):
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([1024] + [0] * 9, every=1)          # y = 2 * C[k]
    e.m = Model()
    assert [e.m.push_cf(1024)] + [e.m.push_cf(0) for _ in range(8)] == [2 * c for c in COEF]


@cocotb.test()
async def test_rounding_is_half_up(dut):
    """Ties: ACC = +-18688 sits exactly on a half_cf; +32 gives 37 and -32 gives -36 (not -37)."""
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([32, 0, 0, 0, 0, 0, 0, 0, 0], every=1)
    await e.feed_cf([-32, 0, 0, 0, 0, 0, 0, 0, 0], every=1)
    await e.feed_cf([33, -33, 31, -31, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0], every=1)


@cocotb.test()
async def test_random_samples(dut):
    e = Env_cf(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.feed_cf([rng.randrange(-20000, 20000) for _ in range(24)], every=1)
    await e.feed_cf([rng.randrange(-32768, 32768) for _ in range(16)], every=4)


@cocotb.test()
async def test_saturation(dut):
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([30000] * 10, every=1)              # DC gain is exactly 1 (the transient peaks at 1.07): no saturation
    await e.b.expect(STATUS, e.m.read(STATUS), "no SAT at DC")
    assert e.m.sat_cf == 0
    big = [32767, -32768] * 6                        # near Nyquist the gain is above 1
    await e.feed_cf(big, every=1)
    assert e.m.sat_cf == 1
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT latched")
    await e.feed_cf([0] * 12, every=3)
    assert e.m.sat_cf == 1
    await e.b.expect(STATUS, e.m.read(STATUS) , "SAT stays latched")


@cocotb.test()
async def test_history_keeps_the_samples_not_the_saturated_results(dut):
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([32767, -32768, 32767, -32768, 32767, -32768, 32767, -32768, 32767], every=1)
    await e.feed_cf([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], every=1)


@cocotb.test()
async def test_queue_keeps_the_newest(dut):
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([100 * i for i in range(1, 12)], every=100)    # 11 results, queue holds the newest 8
    assert e.m.lost_cf == 1 and len(e.m.q_cf) == 8
    await e.b.expect(STATUS, 8 | 1 << 5, "STATUS full and LOST")
    await e.drain_cf("newest 8")
    await e.b.expect(STATUS, 1 << 5, "LOST stays after draining")
    await e.wr_cf(CTRL, 1)
    await e.b.expect(STATUS, 0, "CLEAR clears LOST")
    await e.feed_cf([5000, 0, 0, 0, 0, 0, 0, 0, 0], every=3)


@cocotb.test()
async def test_clear_and_register_rules(dut):
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([7000, -7000, 7000], every=3)
    await e.wr_cf(SAMPLE, 0x1234_8765)                  # only [15:0]
    await e.wr_cf(CTRL, 0xFFFF_FFFE)                    # not a clear
    await e.b.expect(STATUS, e.m.read(STATUS), "CTRL without bit 0")
    await e.b.write(STATUS, 0x3F)
    await e.b.write(RESULT, 9)
    await e.b.expect(RESULT, e.m.read(RESULT), "RO write ignored, read does not pop")
    await e.b.expect(RESULT, e.m.read(RESULT), "RESULT twice")
    for off in (CTRL, SAMPLE, NEXT, 0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "write-only or unmapped reads 0")
    await e.wr_cf(CTRL, 1)                              # history cleared too
    await e.feed_cf([1000, 0], every=1)
    await e.wr_cf(NEXT, 0)
    await e.b.expect(STATUS, 0, "NEXT on empty")


@cocotb.test()
async def test_saturation_is_decided_after_rounding(dut):
    """ACC / 512 is 32767.x before rounding; the rounded result is 32768 and must limit; a smaller ACC rounds to 32767 and must not."""
    e = Env_cf(dut)
    await e.b.start()
    await e.feed_cf([28728, 0, 0, 0, -40], every=1)
    assert e.m.sat_cf == 1
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT at the rounding boundary")
    await e.wr_cf(CTRL, 1)
    await e.feed_cf([28728, 0, 0, 0, -300], every=1)
    assert e.m.sat_cf == 0
    await e.b.expect(STATUS, 0, "no SAT just below the boundary")
