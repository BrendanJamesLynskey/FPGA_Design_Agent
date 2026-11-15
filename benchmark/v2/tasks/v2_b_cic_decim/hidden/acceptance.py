"""Acceptance tests of v2_b_cic_decim against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from model import BITS, CTRL, DESIGN_ID, NEXT, RESULT, STATUS, Model


class Env_cd:
    def __init__(self, dut) -> None:
        self.b, self.m = Board(dut, {}), Model()

    async def wr_cd(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def words(self, ws) -> None:
        for w in ws:
            await self.wr_cd(BITS, w)

    async def drain_cd(self, what: str) -> None:
        """Compare STATUS, then pop every queued result against the model."""
        await self.b.expect(STATUS, self.m.read(STATUS), "STATUS " + what)
        while self.m.q_cd:
            await self.b.expect(RESULT, self.m.read(RESULT), "RESULT " + what)
            await self.wr_cd(NEXT, 0)
        await self.b.expect(RESULT, 0, "RESULT of an empty queue " + what)


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env_cd(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, 0, "register at reset")
    await e.words([0xFFFF_FFFF] * 4)
    await e.wr_cd(CTRL, 1)
    await e.words([0xFFFF_FFFF] * 3)
    await e.b.reset()
    e.m = Model()
    await e.b.expect(STATUS, 0, "STATUS after reset")
    await e.words([0x0] * 2)                    # 4 outputs of the empty start state: 2 results of -4096-ish ramp
    await e.drain_cd("after reset")


@cocotb.test()
async def test_full_scale_exact(dut):
    """All ones then all zeros: the steady-state output is exactly +4096 and -4096, and the ramp to it is exact."""
    e = Env_cd(dut)
    await e.b.start()
    await e.words([0xFFFF_FFFF] * 6)             # 12 outputs, 10 results
    await e.drain_cd("all ones")
    await e.words([0x0000_0000] * 6)
    await e.drain_cd("all zeros")
    assert e.m.read(RESULT) == 0


@cocotb.test()
async def test_fill_outputs_are_not_results(dut):
    e = Env_cd(dut)
    await e.b.start()
    await e.wr_cd(BITS, 0xFFFF_FFFF)                # outputs 0 and 1 only
    await e.b.expect(STATUS, 0, "two outputs are both fills")
    await e.wr_cd(BITS, 0xFFFF_FFFF)                # outputs 2 and 3
    await e.b.expect(STATUS, 2, "outputs 2 and 3 are results")
    await e.drain_cd("fill")


@cocotb.test()
async def test_random_bits(dut):
    e = Env_cd(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        await e.words([rng.getrandbits(32) for _ in range(5)])
        await e.drain_cd("random")
    dens = [0xFFFE_FFFE, 0x0001_0001, 0x5555_5555, 0xAAAA_AAAA, 0xF0F0_F0F0, 0x8000_0001]   # tones and edges
    await e.words(dens * 2)
    await e.drain_cd("patterns")


@cocotb.test()
async def test_queue_overflow(dut):
    e = Env_cd(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 1)
    await e.words([rng.getrandbits(32) for _ in range(11)])     # 22 outputs, 20 results, only 16 fit
    assert len(e.m.q_cd) == 16 and e.m.ovr_cd == 1
    await e.b.expect(STATUS, 16 | 1 << 8, "STATUS full and OVR")
    await e.b.expect(RESULT, e.m.read(RESULT), "oldest kept")
    await e.wr_cd(NEXT, 0)
    await e.b.expect(STATUS, 15 | 1 << 8, "OVR stays set after a pop")
    await e.drain_cd("the rest of the full queue")
    await e.wr_cd(CTRL, 1)
    await e.b.expect(STATUS, 0, "CLEAR empties the queue and OVR")


@cocotb.test()
async def test_clear_restarts_the_filter(dut):
    e = Env_cd(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 2)
    await e.words([rng.getrandbits(32) for _ in range(3)])      # mid-phase: 3 words = 6 outputs
    await e.drain_cd("before clear")
    await e.words([0xFFFF_FFFF, 0x0000_0001])
    await e.wr_cd(CTRL, 1)                                          # clear in the middle of everything
    await e.words([rng.getrandbits(32) for _ in range(4)])
    await e.drain_cd("after clear")


@cocotb.test()
async def test_register_rules(dut):
    e = Env_cd(dut)
    await e.b.start()
    await e.wr_cd(CTRL, 0xFFFF_FFFE)                # bit 0 clear: not a clear
    await e.words([0xFFFF_FFFF] * 3)
    await e.wr_cd(CTRL, 0xFFFF_FFFE)
    await e.b.expect(STATUS, e.m.read(STATUS), "CTRL without bit 0 does nothing")
    await e.b.write(STATUS, 0x1FF)               # RO: ignored
    await e.b.write(RESULT, 5)
    await e.b.expect(STATUS, e.m.read(STATUS), "RO write ignored")
    await e.b.expect(RESULT, e.m.read(RESULT), "RESULT read does not pop")
    await e.b.expect(RESULT, e.m.read(RESULT), "RESULT read twice")
    for off in (CTRL, BITS, NEXT, 0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "write-only or unmapped reads 0")
    await e.wr_cd(NEXT, 0)
    await e.drain_cd("rules")
    await e.wr_cd(NEXT, 0)                          # NEXT on an empty queue
    await e.b.expect(STATUS, 0, "NEXT on empty")
