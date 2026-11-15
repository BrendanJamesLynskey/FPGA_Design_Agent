"""Acceptance tests of v2_b_dc_block against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from model import CTRL, DESIGN_ID, NEXT, RESULT, SAMPLE, STATUS, Model


class Env_db:
    def __init__(self, dut) -> None:
        self.b, self.m = Board(dut, {}), Model()

    async def wr_db(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def feed_db(self, xs, every: int = 1) -> None:
        """Write the samples; after each ``every`` of them compare_db STATUS and pop all the results."""
        for i, x in enumerate(xs, 1):
            await self.wr_db(SAMPLE, x)
            if i % every == 0:
                await self.drain_db(f"after sample {i} ({x})")

    async def drain_db(self, what: str) -> None:
        await self.b.expect(STATUS, self.m.read(STATUS), "STATUS " + what)
        while self.m.q_db:
            await self.b.expect(RESULT, self.m.read(RESULT), "RESULT " + what)
            await self.wr_db(NEXT, 0)


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env_db(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, 0, "register at reset")
    await e.feed_db([9000, 9000, -9000])
    await e.b.reset()
    e.m = Model()
    await e.b.expect(STATUS, 0, "STATUS after reset")
    await e.feed_db([100, 100, 100])                    # starts from zero history again


@cocotb.test()
async def test_step_follows_the_equation(dut):
    """A positive step: the first result is the step, then it decays by yp >> 7 each sample (floor)."""
    e = Env_db(dut)
    await e.b.start()
    await e.feed_db([10000] * 24, every=4)
    await e.wr_db(CTRL, 1)
    await e.feed_db([-10000] * 24, every=4)


@cocotb.test()
async def test_small_positive_offsets_stay(dut):
    """The floor shift leaves a positive Y below 128 unchanged and lets a negative one fade to zero."""
    e = Env_db(dut)
    await e.b.start()
    await e.feed_db([100] + [100] * 12, every=1)        # 100 stays: the step of 100 never decays
    await e.wr_db(CTRL, 1)
    await e.feed_db([-100] * 12, every=1)               # -100 fades toward 0 (steps of one)
    await e.wr_db(CTRL, 1)
    await e.feed_db([127, 127, 127, 128, 128, 128, 129, 129], every=1)


@cocotb.test()
async def test_random_samples(dut):
    e = Env_db(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.feed_db([rng.randrange(-20000, 20000) for _ in range(24)], every=1)
    await e.feed_db([rng.randrange(-32768, 32768) for _ in range(20)], every=4)


@cocotb.test()
async def test_saturation_and_limited_feedback(dut):
    e = Env_db(dut)
    await e.b.start()
    await e.feed_db([20000, 20000, -32768, 32767, -32768, 32767, -32768, 0, 0, 0], every=1)
    assert e.m.sat_db == 1
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT latched")
    await e.feed_db([0] * 6, every=3)
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT stays")
    await e.wr_db(CTRL, 1)
    await e.b.expect(STATUS, 0, "CLEAR clears SAT")
    await e.feed_db([-32768, 32767, 32767, 32767, -32768, -32768, -32768, 0, 0], every=1)
    assert e.m.sat_db == 1


@cocotb.test()
async def test_queue_keeps_the_newest(dut):
    e = Env_db(dut)
    await e.b.start()
    await e.feed_db([1000 * i for i in range(1, 8)], every=100)
    assert e.m.lost_db == 1 and len(e.m.q_db) == 4
    await e.b.expect(STATUS, 4 | 1 << 4, "STATUS full and LOST")
    await e.drain_db("newest 4")
    await e.b.expect(STATUS, 1 << 4, "LOST stays")
    await e.wr_db(CTRL, 1)
    await e.b.expect(STATUS, 0, "CLEAR clears LOST")


@cocotb.test()
async def test_clear_and_register_rules(dut):
    e = Env_db(dut)
    await e.b.start()
    await e.feed_db([7000, 7000, 7000], every=3)
    await e.wr_db(SAMPLE, 0x1234_8765)                  # only [15:0]
    await e.wr_db(CTRL, 0xFFFF_FFFE)                    # not a clear
    await e.b.expect(STATUS, e.m.read(STATUS), "CTRL without bit 0")
    await e.b.write(STATUS, 0x1F)
    await e.b.write(RESULT, 9)
    await e.b.expect(RESULT, e.m.read(RESULT), "a write to a read-only register does nothing and a read does not pop the queue")
    await e.b.expect(RESULT, e.m.read(RESULT), "RESULT twice")
    for off in (CTRL, SAMPLE, NEXT, 0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "write-only or unmapped reads 0")
    await e.wr_db(CTRL, 1)                              # history cleared too: x - 0 again
    await e.feed_db([5000, 5000], every=1)
    await e.wr_db(NEXT, 0)
    await e.b.expect(STATUS, e.m.read(STATUS), "NEXT")


@cocotb.test()
async def test_limits_at_the_exact_boundaries(dut):
    """W = 32768 and W = -32769 limit; W = 32767 and W = -32768 do not."""
    e = Env_db(dut)
    await e.b.start()
    for pair, sat_db in (([-5000, 32728], 1), ([-5000, 32727], 0), ([5000, -32730], 1), ([5000, -32729], 0)):
        await e.wr_db(CTRL, 1)
        await e.feed_db(pair, every=1)
        assert e.m.sat_db == sat_db, pair
        await e.b.expect(STATUS, e.m.read(STATUS), f"SAT after {pair}")
