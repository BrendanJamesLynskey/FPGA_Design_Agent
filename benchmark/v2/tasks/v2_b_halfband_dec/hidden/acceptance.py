"""Acceptance tests of v2_b_halfband_dec against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from model import COEF, CTRL, DESIGN_ID, NEXT, RESULT, SAMPLE, STATUS, Model, convergent_hb


class Env_hb:
    def __init__(self, dut) -> None:
        self.b, self.m = Board(dut, {}), Model()

    async def wr_hb(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def feed_hb(self, xs, every: int = 2) -> None:
        """Write the samples, compare_hb STATUS and pop every result after each ``every`` of them."""
        for i, x in enumerate(xs, 1):
            await self.wr_hb(SAMPLE, x)
            if i % every == 0:
                await self.drain_hb(f"after sample {i} ({x})")

    async def drain_hb(self, what: str) -> None:
        await self.b.expect(STATUS, self.m.read(STATUS), "STATUS " + what)
        while self.m.q_hb:
            await self.b.expect(RESULT, self.m.read(RESULT), "RESULT " + what)
            await self.wr_hb(NEXT, 0)


@cocotb.test()
async def test_model_is_convergent(dut):
    assert [convergent_hb(a) for a in (16, 48, -16, -48, 15, 17, -15, -17, 80, -80)] == [0, 2, 0, -2, 0, 1, 0, -1, 2, -2]
    assert sum(COEF) == 32


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env_hb(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, 0, "register at reset")
    await e.feed_hb([20000, -20000, 5])
    await e.b.reset()
    e.m = Model()
    await e.b.expect(STATUS, 0, "STATUS after reset (parity too)")
    await e.feed_hb([1000, 0, 0, 0], every=2)


@cocotb.test()
async def test_a_result_for_every_second_sample(dut):
    e = Env_hb(dut)
    await e.b.start()
    await e.wr_hb(SAMPLE, 100)
    await e.b.expect(STATUS, 1 << 6, "one sample written: no result, ODD set")
    await e.wr_hb(SAMPLE, 200)
    await e.b.expect(STATUS, 1, "two samples: one result, ODD clear")
    await e.drain_hb("pair")
    await e.feed_hb([300, 400, 500, 600, 700], every=1)      # compare_hb after every sample, odd ones too


@cocotb.test()
async def test_impulse_at_both_phases(dut):
    e = Env_hb(dut)
    await e.b.start()
    await e.feed_hb([4096, 0, 0, 0, 0, 0, 0, 0], every=2)    # impulse on an odd sample
    await e.feed_hb([0, 4096, 0, 0, 0, 0, 0, 0], every=2)    # impulse on an even sample


@cocotb.test()
async def test_ties_go_to_even(dut):
    """The centre tap is 16, so an impulse x on a sample that meets it gives ACC = 16 x: ties for odd x."""
    e = Env_hb(dut)
    await e.b.start()
    for x in (1, 3, -1, -3, 5, -5, 7, -7, 2, 15, -15, 17):
        await e.feed_hb([x, 0, 0, 0, 0, 0, 0, 0], every=2)
        await e.wr_hb(CTRL, 1)


@cocotb.test()
async def test_random_samples(dut):
    e = Env_hb(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.feed_hb([rng.randrange(-30000, 30000) for _ in range(30)], every=2)
    await e.feed_hb([rng.randrange(-32768, 32768) for _ in range(16)], every=8)


@cocotb.test()
async def test_saturation(dut):
    e = Env_hb(dut)
    await e.b.start()
    await e.feed_hb([30000] * 12, every=2)
    assert e.m.sat_hb == 0
    await e.b.expect(STATUS, e.m.read(STATUS), "no SAT at DC (the transient peaks at 1.03)")
    await e.wr_hb(CTRL, 1)
    pos_hb = [0, -32767, 0, 32767, 32767, 32767, 0, -32767]       # every tap sees the sample that makes it add up: 36/32
    await e.feed_hb(pos_hb, every=2)
    assert e.m.sat_hb == 1 and e.m.q_hb == [] and e.m.n == 8
    await e.wr_hb(CTRL, 1)
    await e.feed_hb(pos_hb, every=1000)
    assert e.m.q_hb[-1] == 32767, e.m.q_hb
    await e.drain_hb("positive limit")
    await e.wr_hb(CTRL, 1)
    await e.feed_hb([-x for x in pos_hb], every=1000)
    assert e.m.q_hb[-1] == -32768, e.m.q_hb
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT after the negative limit")
    await e.drain_hb("negative limit")
    await e.feed_hb([0] * 6, every=2)
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT stays")
    assert e.m.sat_hb == 1


@cocotb.test()
async def test_queue_drops_new_results(dut):
    e = Env_hb(dut)
    await e.b.start()
    await e.feed_hb([111 * i for i in range(1, 22)], every=1000)      # 10 results, queue holds the first 8
    assert e.m.ovr_hb == 1 and len(e.m.q_hb) == 8
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS full and OVR")
    await e.drain_hb("oldest kept")
    await e.b.expect(STATUS, e.m.read(STATUS), "OVR after draining")
    await e.wr_hb(CTRL, 1)
    await e.b.expect(STATUS, 0, "CLEAR clears OVR and the parity")


@cocotb.test()
async def test_clear_restarts_the_pairing(dut):
    e = Env_hb(dut)
    await e.b.start()
    await e.feed_hb([500, 600, 700], every=1000)                       # an odd count
    await e.wr_hb(CTRL, 1)
    await e.b.expect(STATUS, 0, "CLEAR drops results, ODD and history")
    await e.feed_hb([800, 900, 1000, 1100], every=2)
    await e.feed_hb([1200, 1300, 1400], every=1000)                    # a result queued and an odd count
    await e.wr_hb(CTRL, 0xFFFF_FFFE)                                   # not a clear
    await e.b.expect(STATUS, e.m.read(STATUS), "CTRL without bit 0")
    assert e.m.read(STATUS) & 0x4F == 1 | 1 << 6


@cocotb.test()
async def test_register_rules(dut):
    e = Env_hb(dut)
    await e.b.start()
    await e.wr_hb(SAMPLE, 0x7777_8000)                                 # only [15:0]: -32768
    await e.wr_hb(SAMPLE, 0x1_0005)
    await e.b.write(STATUS, 0x7F)
    await e.b.write(RESULT, 9)
    await e.b.expect(STATUS, e.m.read(STATUS), "RO write ignored")
    await e.b.expect(RESULT, e.m.read(RESULT), "RESULT read does not pop")
    await e.b.expect(RESULT, e.m.read(RESULT), "RESULT twice")
    for off in (CTRL, SAMPLE, NEXT, 0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "write-only or unmapped reads 0")
    await e.wr_hb(NEXT, 0)
    await e.wr_hb(NEXT, 0)                                             # NEXT on empty
    await e.b.expect(STATUS, e.m.read(STATUS), "NEXT on empty")


@cocotb.test()
async def test_saturation_is_decided_after_rounding(dut):
    """ACC = 1048575 is 32767 and a fraction of 31/32 before rounding: the rounded 32768 must limit; ACC = 1048559 rounds to 32767 and must not."""
    e = Env_hb(dut)
    await e.b.start()
    await e.feed_hb([0, 30000, 30945, 31495, 0, 0], every=2)
    assert e.m.sat_hb == 1
    await e.b.expect(STATUS, e.m.read(STATUS), "SAT at the rounding boundary")
    await e.wr_hb(CTRL, 1)
    await e.feed_hb([0, 30000, 30944, 31495, 0, 0], every=2)
    assert e.m.sat_hb == 0
    await e.b.expect(STATUS, 0, "no SAT just below the boundary")
