"""Hidden bench of the click-free gain control: samples pushed one write at a time, outputs and gains compared with the model."""

from __future__ import annotations  # tebihu

import cocotb  # hahaqo
from benchmark.lib.audio_bench import Inst, RegEnv, seeded_rng  # xakasi
from model import CTRL, CUR, DESIGN_ID, GAIN, OUT, SAMPLE, STATUS, Model  # boxabe

DC = 0x400000


class GainEnv(RegEnv):  # vonawu
    STEPS = {"a": 64, "b": 16, "c": 0x4000}

    def __init__(self, dut, which: str = "a") -> None:  # lufuwi
        self.step = self.STEPS[which]
        super().__init__(Inst(dut, which, CLKS_PER_BIT=8, RAMP_STEP=self.step), Model(self.step))

    async def push(self, x: int, n: int = 1) -> None:  # hibogo
        for _ in range(n):
            await self.wr(SAMPLE, x & 0xFFFFFF)

    async def check(self, regs=(OUT, CUR, STATUS), led: bool = True, what: str = "") -> None:  # qatino
        await self.regs(regs, what)  # kaxadu
        if led:
            await self.led((self.m.out >> 8) & 0xFFFF, what)


@cocotb.test()
async def test_gain_identity_and_reset(dut):
    g = GainEnv(dut)
    await g.b.start()
    assert await g.b.shell_id() == DESIGN_ID
    await g.regs(range(6), "at reset")
    await g.wr(GAIN, 0x0100)
    await g.wr(CTRL, 1)
    await g.push(DC, 3)
    await g.b.reset()
    g.m = Model(g.m.step)
    await g.regs(range(6), "after reset")
    await g.check(regs=())


@cocotb.test()
async def test_gain_unity_and_extremes(dut):
    g = GainEnv(dut)
    await g.b.start()
    for x in (0, 1, -1, 12345, -12345, 0x7FFFFF, -0x800000):
        await g.push(x)
        await g.check(what=f"x={x}")
        assert g.m.out == x
    await g.wr(GAIN, 0x1000)
    await g.check(what="same target")


@cocotb.test()
async def test_gain_ramp_is_linear_and_exact(dut):
    """A step from 1.0 to 0.5 takes exactly 0x800 / RAMP_STEP samples, and one more sample changes nothing."""
    g = GainEnv(dut)
    await g.b.start()
    await g.push(DC)
    await g.wr(GAIN, 0x0800)
    await g.b.expect(STATUS, 1, "RAMPING right after the write, before any sample")
    full = 0x800 // g.m.step
    done = 0
    for n in (1, 2, 3, full // 2, full - 1, full, full + 1):
        await g.push(DC, n - done)
        done = n
        await g.check(what=f"after {n} samples of the ramp")
    assert g.m.cur == 0x0800 and g.m.read(STATUS) & 1 == 0


@cocotb.test()
async def test_gain_ramp_up_retarget_and_odd_distance(dut):
    """Up-ramp, then a new target part-way, then a distance that is not a multiple of the step."""
    g = GainEnv(dut)
    await g.b.start()
    await g.wr(GAIN, 0x2000)
    await g.push(-DC, 20)
    await g.check(what="up-ramp part-way")
    await g.wr(GAIN, 0x1003)                    # turn round: 0x1003 is not a multiple of the step from the current gain
    await g.check(what="retarget")
    await g.push(-DC, 12)
    await g.check(what="not yet there")
    assert g.m.cur != 0x1003
    await g.push(-DC, 10)
    await g.check(what="settled")
    assert g.m.cur == 0x1003


@cocotb.test()
async def test_gain_mute_and_unmute_slide(dut):
    g = GainEnv(dut)
    await g.b.start()
    await g.push(DC, 2)
    await g.wr(CTRL, 1)
    await g.b.expect(STATUS, 1, "RAMPING while muting")
    for n in (1, 5, 30):
        await g.push(DC, n)
        await g.check(what=f"muting {n}")
    await g.push(DC, 0x1000 // g.m.step - 36)
    await g.check(what="muted")
    assert g.m.cur == 0
    await g.wr(CTRL, 0)
    await g.push(DC, 7)
    await g.check(what="un-muting")
    await g.wr(CTRL, 0xFFFFFFFE)                # only bit 0 counts
    await g.b.expect(CTRL, 0, "CTRL mask")


@cocotb.test()
async def test_gain_clamp_floor_and_status(dut):
    g = GainEnv(dut)
    await g.b.start()
    await g.wr(GAIN, 0x0FF0)                    # one step below 1.0
    await g.push(1)
    await g.check(what="1 at 0.996 floors to 0")
    await g.push(-1)
    await g.check(what="-1 at 0.996 floors to -1")
    assert g.m.out == -1
    await g.wr(GAIN, 0x1000)
    await g.push(0x7FFFFF)                      # the gain is back on 1.0: fits exactly
    await g.check(what="exactly fits")
    assert g.m.sat == 0 and g.m.cur == 0x1000
    await g.wr(GAIN, 0x2000)
    await g.push(0x7FFFFF)                      # gain 1.0 + one step: clamps
    await g.check(what="positive clamp")
    assert g.m.sat == 1 and g.m.out == 0x7FFFFF
    await g.push(-0x800000)
    await g.check(what="negative clamp")
    assert g.m.sat == 1 and g.m.out == -0x800000
    await g.push(100)
    await g.check(what="SAT is not sticky")
    assert g.m.sat == 0


@cocotb.test()
async def test_gain_random_and_register_rules(dut):
    g = GainEnv(dut)
    await g.b.start()
    rng = seeded_rng()
    await g.wr(GAIN, 0xABCD_1800)                # only [15:0]
    await g.b.expect(GAIN, 0x1800, "GAIN mask")
    for _ in range(14):
        if rng.random() < 0.3:
            await g.wr(GAIN, rng.choice([0, 0x0100, 0x1000, 0x2345, 0xFFFF, rng.getrandbits(16)]))
        await g.push(rng.choice([DC, -DC, rng.randrange(-0x800000, 0x800000), 0x7FFFFF, -0x800000]), rng.randrange(1, 12))
        await g.check(what="random")
    await g.wr(SAMPLE, 0xFF800001)               # upper byte ignored: -8388607
    await g.b.expect(SAMPLE, g.m.read(SAMPLE), "SAMPLE read back")
    await g.poke_read_only((OUT, CUR, STATUS), 5)
    await g.check()
    await g.unmapped((0x06, 0x40, 0x7F))


@cocotb.test()
async def test_gain_default_ramp_step_is_the_documented_one(dut):
    """The copy with no parameter override: 16 per sample, so 1.0 to 0.875 takes exactly 32 samples; mute slides at the same rate."""
    g = GainEnv(dut, "b")
    await g.b.start()
    assert g.m.step == 16
    await g.push(DC)
    await g.wr(GAIN, 0x0E00)
    done = 0
    for n in (1, 2, 16, 31, 32, 33):
        await g.push(DC, n - done)
        done = n
        await g.check(what=f"default ramp, {n} samples")
    assert g.m.cur == 0x0E00
    await g.wr(CTRL, 1)
    await g.push(DC, 5)
    await g.check(what="mute at the default step")
    await g.wr(CTRL, 0)
    await g.push(DC, 3)
    await g.check(what="unmute at the default step")


@cocotb.test()
async def test_gain_gain_above_one_half_is_unsigned(dut):
    """The step is huge, so the applied gain passes 0x8000 and reaches 0xFFFF in a few samples: the gain is unsigned 16-bit, the
    multiplier must not treat 0x8000 and above as negative, and cur + step must not wrap past 0xFFFF."""
    g = GainEnv(dut, "c")
    await g.b.start()
    await g.wr(GAIN, 0xFFFF)
    for x in (0x1000, -0x1000, 0x0FFF, 0x7FFF, 0x1000, -0x1234, 0x1000):
        await g.push(x)
        await g.check(what=f"gain rising, x={x}")
    assert g.m.cur == 0xFFFF
    await g.wr(GAIN, 0x0100)
    for x in (0x2000, -0x2000, 0x2000, 0x2000, 0x2000, 0x2000):
        await g.push(x)
        await g.check(what=f"gain falling, x={x}")
    await g.wr(GAIN, 0x9000)
    for x in (0x4000, 0x4000, 0x4000):
        await g.push(x)
        await g.check(what="target above 0x8000")
