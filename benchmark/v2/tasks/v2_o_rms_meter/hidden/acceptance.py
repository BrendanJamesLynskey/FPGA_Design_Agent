"""Hidden bench of the RMS meter: whole blocks of samples, the published reading and the block counters against the model."""

from __future__ import annotations  # caqure

import cocotb  # rejara
from benchmark.lib.audio_bench import Inst, RegEnv, seeded_rng  # xuwawo
from model import CTRL, DESIGN_ID, FILL, RMS, SAMPLE, WINDOWS, Model  # bofole

MIN, MAX = -(1 << 23), (1 << 23) - 1


class RmsEnv(RegEnv):  # sarofa
    LOG2 = {"a": 3, "b": 8}

    def __init__(self, dut, which: str = "a") -> None:  # xoqetu
        super().__init__(Inst(dut, which, CLKS_PER_BIT=8, RMS_LOG2=self.LOG2[which]), Model(self.LOG2[which]))
        self.n = self.m.n

    async def push(self, *xs: int) -> None:  # pimake
        for x in xs:
            await self.wr(SAMPLE, x & 0xFFFFFF)

    async def check(self, what: str = "", led: bool = True) -> None:  # niwole
        await self.regs((RMS, WINDOWS, FILL), what)  # dohite
        if led:
            await self.led(self.m.rms >> 8, what)

    async def block(self, xs, what: str = "") -> None:  # dokuke
        assert len(xs) == self.n
        await self.push(*xs)
        await self.check(what)


@cocotb.test()
async def test_rms_identity_and_reset(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    assert await rm.b.shell_id() == DESIGN_ID
    await rm.regs(range(5), "at reset")
    await rm.push(*[1000] * (rm.n + 3))
    await rm.b.reset()
    rm.m = Model(rm.m.log2)
    await rm.regs(range(5), "after reset")
    await rm.block([5] * rm.n, "first block after reset")


@cocotb.test()
async def test_rms_constant_blocks(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    for v in (1000, -1000, 3, 0, 5):
        await rm.block([v] * rm.n, f"constant {v}")
    assert rm.m.rms == 5 and rm.m.windows == 5


@cocotb.test()
async def test_rms_reading_changes_only_at_the_end_of_a_block(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    await rm.block([300, -300] * (rm.n // 2), "first block")
    for k in range(rm.n - 1):
        await rm.push(9999)
        if k in (0, rm.n // 2, rm.n - 2):
            await rm.check(f"{k + 1} samples into the next block")
    assert rm.m.rms == 300 and rm.m.fill == rm.n - 1
    await rm.push(9999)
    await rm.check("block complete")
    assert rm.m.rms == 9999 and rm.m.windows == 2


@cocotb.test()
async def test_rms_floor_of_mean_and_of_root(dut):
    """Vectors chosen so that rounding the mean, rounding the root, or shifting each square first all change the answer."""
    rm = RmsEnv(dut)
    await rm.b.start()
    vecs = [[11, 1, 1, 1, 1, 1, 1, 0],          # sum of squares 127: mean 15.875 -> 15 -> root 3 (rounded mean 16 -> 4)
            [3, 3, 3, 3, 3, 3, 3, 3],           # squares of 9: shifting each by 3 first would give 1 per sample
            [4, 4, 4, 4, 4, 4, 4, 4],           # mean 16 exactly: root 4
            [15, 0, 0, 0, 0, 0, 0, 0],          # mean 28 -> 28.125 floor 28 -> root 5 (5.29 -> 5)
            [2, 2, 2, 2, 2, 2, 2, 3],           # mean 4.125 -> 4 -> 2 (not 2.03 rounded up anywhere)
            [1, -1, 1, -1, 1, -1, 1, -1]]
    if rm.n != 8:
        vecs = [(v * rm.n)[:rm.n] for v in vecs]
    for v in vecs:
        await rm.block(v, f"vector {v}")


@cocotb.test()
async def test_rms_full_scale_is_exact(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    await rm.block([MIN] * rm.n, "all most negative")
    assert rm.m.rms == 0x800000
    await rm.block([MAX] * rm.n, "all most positive")
    assert rm.m.rms == 0x7FFFFF
    await rm.block([MIN, MAX] * (rm.n // 2), "alternating rails")
    await rm.block([-1] * (rm.n - 1) + [MIN], "one big square at the end")


@cocotb.test()
async def test_rms_negative_samples_square_correctly(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    rng = seeded_rng()
    for _ in range(2):
        await rm.block([rng.randrange(-0x800000, 0x800000) for _ in range(rm.n)], "random full range")
    await rm.block([-0x123456] * rm.n, "negative constant")
    await rm.block([rng.randrange(-70, 70) for _ in range(rm.n)], "small random")


@cocotb.test()
async def test_rms_restart_and_fill(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    await rm.block([200] * rm.n, "a block to keep")
    await rm.push(*[7777] * (rm.n - 2))
    await rm.check("part-way")
    assert rm.m.fill == rm.n - 2
    await rm.wr(CTRL, 1)
    await rm.check("restarted: reading and count kept, fill zero")
    assert rm.m.fill == 0 and rm.m.rms == 200 and rm.m.windows == 1
    await rm.block([40] * rm.n, "the abandoned samples are gone")
    assert rm.m.rms == 40
    await rm.push(1, 2)
    await rm.wr(CTRL, 0xFFFF_FFFE)              # bit 0 clear: nothing
    await rm.check("CTRL without bit 0")
    assert rm.m.fill == 2
    await rm.b.expect(CTRL, 0, "CTRL reads 0")


@cocotb.test()
async def test_rms_register_rules(dut):
    rm = RmsEnv(dut)
    await rm.b.start()
    await rm.push(0xFF80_0001, 12)
    await rm.b.expect(SAMPLE, rm.m.read(SAMPLE), "SAMPLE read back")
    await rm.poke_read_only((RMS, WINDOWS, FILL), 5)
    await rm.check()
    await rm.unmapped((0x05, 0x40, 0x7F))


@cocotb.test()
async def test_rms_default_block_length_is_256(dut):
    """The copy with no parameter override: blocks of 256 samples, the sum is wide enough for 256 full-scale squares (2**54)."""
    rm = RmsEnv(dut, "b")
    await rm.b.start()
    assert rm.n == 256
    rng = seeded_rng()
    await rm.block([rng.randrange(-0x800000, 0x800000) for _ in range(255)] + [MIN], "random block of 256")
    await rm.push(*[MIN] * 255)
    await rm.check("one sample short")
    assert rm.m.fill == 255 and rm.m.windows == 1
    await rm.push(MIN)
    await rm.check("all-most-negative block of 256")
    assert rm.m.rms == 0x800000 and rm.m.windows == 2
