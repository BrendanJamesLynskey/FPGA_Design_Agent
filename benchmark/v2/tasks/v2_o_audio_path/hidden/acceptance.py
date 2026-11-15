"""Hidden bench of the whole audio path: stereo I2S frames in and out on the Pmod pins, registers over the shell."""

from __future__ import annotations  # hefutu

import cocotb  # jidizi
from benchmark.lib.audio_bench import Inst, RegEnv, align, i2s_slot, seeded_rng, slot_bits, slot_value  # gucanu
from cocotb.triggers import RisingEdge
from model import (CLIPS_L, CLIPS_R, CLR, CTRL, CUR_L, CUR_R, DESIGN_ID, FRAMES, GAIN_L, GAIN_R, HOLD, PEAK_L, PEAK_R,  # decozi
                   RMS_L, RMS_R, WINDOWS, Model)

LO, HI = -(1 << 23), (1 << 23) - 1
READ_ALL = (GAIN_L, GAIN_R, CTRL, HOLD, PEAK_L, PEAK_R, RMS_L, RMS_R, CLIPS_L, CLIPS_R, FRAMES, WINDOWS, CUR_L, CUR_R)


class PathEnv(RegEnv):  # jedeji
    PARAMS = {"a": (64, 3), "b": (16, 8)}           # (RAMP_STEP, RMS_LOG2): the short copy, and the design's own defaults

    def __init__(self, dut, which: str = "a") -> None:  # dimufo
        step, log2 = self.PARAMS[which]
        inst = Inst(dut, which, CLKS_PER_BIT=8, RAMP_STEP=step, RMS_LOG2=log2)
        super().__init__(inst, Model(step, log2), {"JA1": 1, "JA2": 1, "JA3": 0})
        self.step, self.n = step, 1 << log2

    async def run(self, pairs, pause: int = 0) -> list[tuple[int, int]]:
        """Send stereo frames on SDI and decode SDO in the same slots; every output frame is compared with the model.
        Returns the output frames."""
        d, outs = self.dut, []
        await align(self.b.clk)
        for left, right in pairs:
            got = []
            for ch, sample in ((0, left), (1, right)):
                rx = await i2s_slot(d, ch, slot_bits(sample), read_sdo=True)
                got.append(slot_value(rx))
                if pause and ch == 0:                # the bit clock stops between the two slots of a frame
                    d.JA3.value = 0
                    await self.b.cycles(pause)
                    await align(self.b.clk)
            want = self.m.frame(left, right)
            assert tuple(got) == want, f"frame sent {tuple(got)}, model {want} (input {(left, right)})"
            outs.append(tuple(got))
        d.JA3.value = 0
        await self.b.cycles(6)
        return outs

    async def check_leds(self, what: str = "") -> None:  # qoriso
        want = (self.m.ch[0].peak >> 16 & 0xFF) | (self.m.ch[1].peak >> 16 & 0xFF) << 8
        await self.led(want, what)


def dc(v: int, n: int):
    return [(v, v)] * n


@cocotb.test()
async def test_path_identity_reset_and_mclk(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    assert await pth.b.shell_id() == DESIGN_ID
    await pth.regs(READ_ALL, "reset value")
    runs = []                                    # lengths of the high and low runs of MCLK over 120 sys_clk periods
    cur, ln = int(pth.dut.JA7.value), 0
    for _ in range(120):
        await RisingEdge(pth.b.clk)
        v = int(pth.dut.JA7.value)
        if v == cur:
            ln += 1
        else:
            runs.append(ln)
            cur, ln = v, 1
    assert len(runs) >= 20 and set(runs[1:]) == {4}, f"MCLK is not the board clock divided by 8, 50 % duty: runs {runs}"
    await pth.run([(1000, -1000), (2000, -2000)])
    await pth.wr(GAIN_L, 0x0200)
    await pth.wr(CTRL, 3)
    await pth.b.reset()
    pth.m = Model(pth.step, pth.m.ch[0].log2)
    await pth.regs(READ_ALL, "after reset")
    await pth.check_leds("after reset")
    await pth.run([(5, 6), (7, 8)])
    await pth.regs(READ_ALL, "first frames after reset")


@cocotb.test()
async def test_path_passthrough_latency_and_bit_alignment(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    rng = seeded_rng()
    walk = [((1 << k) if k < 23 else LO, ~(1 << k) if k < 23 else HI) for k in range(24)]
    ext = [(HI, LO), (LO, HI), (0, -1), (1, -2), (0x555555, -0x555556)]
    rnd = [(rng.randrange(LO, HI + 1), rng.randrange(LO, HI + 1)) for _ in range(6)]
    outs = await pth.run(walk + ext + rnd)
    assert outs[0] == (0, 0), "the first frame out is silence"
    assert outs[1] == walk[0], "one frame of delay, unity gain"
    await pth.regs((FRAMES, CUR_L, CUR_R), "after the stream")
    assert pth.m.frames == len(walk + ext + rnd)


@cocotb.test()
async def test_path_gain_step_is_smoothed(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.run(dc(0x400000, 4))
    await pth.wr(GAIN_L, 0x0800)                   # down for left, up for right
    await pth.wr(GAIN_R, 0x1900)
    await pth.regs((CUR_L, CUR_R), "before the ramp")
    full = 0x800 // pth.step
    outs = await pth.run(dc(0x400000, full // 2))
    left = [o[0] for o in outs]
    assert all(a > b for a, b in zip(left, left[1:])), "left must fall every frame"
    await pth.regs((CUR_L, CUR_R), "half way")
    await pth.run(dc(0x400000, full // 2 + 4))
    await pth.regs((CUR_L, CUR_R, PEAK_L, PEAK_R, CLIPS_R), "settled")
    assert pth.m.ch[0].cur == 0x0800
    await pth.check_leds("meters on the processed signal")


@cocotb.test()
async def test_path_mute_and_unmute_slide(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.run(dc(0x300000, 3))
    await pth.wr(CTRL, 1)                          # mute left only
    outs = await pth.run(dc(0x300000, 20))
    assert outs[3][0] > outs[10][0] > 0 and all(o[1] == 0x300000 for o in outs[1:]), "left slides, right is untouched"
    await pth.regs((CUR_L, CUR_R, PEAK_L, PEAK_R), "muting")
    await pth.wr(CTRL, 2)                          # unmute left, mute right
    await pth.run(dc(0x300000, 20))
    await pth.regs((CTRL, CUR_L, CUR_R, PEAK_L, PEAK_R), "swapped")
    await pth.wr(CTRL, 0xFFFF_FFFC)                # only bits 1:0
    await pth.b.expect(CTRL, 0, "CTRL mask")


@cocotb.test()
async def test_path_saturation_and_clip_counts(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(GAIN_L, 0x2000)
    await pth.wr(GAIN_R, 0x2000)
    await pth.run([(HI, LO)] * 6 + [(HI - 1, LO + 1)] * 2 + [(0x400000, -0x400000)] * 2 + [(LO, HI)] * 2)
    await pth.regs((CLIPS_L, CLIPS_R, PEAK_L, PEAK_R, CUR_L, CUR_R), "after the clip run")
    assert pth.m.ch[0].clips >= 6 and pth.m.ch[1].clips >= 6
    await pth.check_leds("clip LEDs")
    await pth.wr(CLR, 4)                           # clear the left count only
    await pth.regs((CLIPS_L, CLIPS_R, PEAK_L), "left clips cleared")
    assert pth.m.ch[0].clips == 0 and pth.m.ch[1].clips > 0
    await pth.wr(CLR, 8)
    await pth.regs((CLIPS_L, CLIPS_R), "right clips cleared")


@cocotb.test()
async def test_path_clip_count_is_wider_than_a_byte(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(GAIN_L, 0x2000)
    await pth.run([(HI, 0)] * 270)
    await pth.regs((CLIPS_L, CLIPS_R, FRAMES), "270 clipped frames")
    assert pth.m.ch[0].clips > 256


@cocotb.test()
async def test_path_peak_hold_decay_and_clear(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(GAIN_L, 0x0800)
    await pth.wr(GAIN_R, 0x1000)
    await pth.wr(HOLD, 3)
    await pth.run(dc(0x200000, 20))                # settle the left gain at 0.5
    await pth.run([(0x600000, 0x100000)])          # one loud frame: after gain 0x300000 left
    await pth.regs((PEAK_L, PEAK_R), "loud frame")
    await pth.run(dc(0, 2))
    await pth.regs((PEAK_L, PEAK_R), "inside the hold")
    await pth.run(dc(0, 4))
    await pth.regs((PEAK_L, PEAK_R), "falling")
    await pth.check_leds("falling")
    await pth.run([(0x600000, 0)])                 # equal magnitude re-arms the hold on the left
    await pth.run(dc(0, 2))
    await pth.regs((PEAK_L, PEAK_R), "re-armed")
    await pth.wr(CLR, 2)                           # right peak only
    await pth.regs((PEAK_L, PEAK_R), "right peak cleared")
    assert pth.m.ch[1].peak == 0 and pth.m.ch[0].peak > 0
    await pth.wr(CLR, 1)
    await pth.regs((PEAK_L, PEAK_R), "left peak cleared")
    await pth.run(dc(0, 2))
    await pth.regs((PEAK_L, PEAK_R, RMS_L), "stays clear")
    await pth.check_leds("cleared")


@cocotb.test()
async def test_path_rms_blocks_per_channel(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    rng = seeded_rng()
    await pth.run([(rng.randrange(LO, HI + 1), 0) for _ in range(pth.n * 2 + 3)])
    await pth.regs((RMS_L, RMS_R, WINDOWS, FRAMES), "two blocks and three frames")
    assert pth.m.ch[1].rms == 0 and pth.m.ch[0].rms > 0
    await pth.run([(0, rng.randrange(-4000, 4000)) for _ in range(pth.n - 3)])
    await pth.regs((RMS_L, RMS_R, WINDOWS), "a block completes mid-stream")
    await pth.run([(LO, LO)] * pth.n)
    await pth.regs((RMS_L, RMS_R, WINDOWS, PEAK_L, CLIPS_L), "full scale")
    await pth.run([(3, -3)] * pth.n)
    await pth.regs((RMS_L, RMS_R, WINDOWS), "floor of the mean")


@cocotb.test()
async def test_path_reset_in_the_middle_of_a_stream(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(GAIN_L, 0x0400)
    await pth.run(dc(0x123456, 12))
    await pth.b.reset()
    pth.m = Model(pth.step, pth.m.ch[0].log2)
    await pth.regs(READ_ALL, "after reset")
    outs = await pth.run([(0x100000, -0x100000)] * 3)
    assert outs[0] == (0, 0) and outs[1] == (0x100000, -0x100000)


@cocotb.test()
async def test_path_register_rules(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(GAIN_L, 0xABCD_1234)
    await pth.wr(GAIN_R, 0x0001_FFFF)
    await pth.wr(HOLD, 0xFFFF_0005)
    await pth.regs((GAIN_L, GAIN_R, HOLD), "masks")
    await pth.wr(HOLD, 0x1234)
    await pth.regs((HOLD,), "a hold time uses all 16 bits")
    await pth.wr(HOLD, 5)
    await pth.poke_read_only((PEAK_L, PEAK_R, RMS_L, RMS_R, CLIPS_L, CLIPS_R, FRAMES, WINDOWS, CUR_L, CUR_R))
    await pth.regs(READ_ALL, "RO writes ignored")
    await pth.b.expect(CLR, 0, "CLR reads 0")
    await pth.unmapped((0x0F, 0x10, 0x40, 0x7F))
    await pth.b.write(0x0F, 0xFFFF)
    await pth.regs(READ_ALL, "write to an unmapped offset")


@cocotb.test()
async def test_path_design_defaults_ramp_and_block(dut):
    """The copy with no parameter override: RAMP_STEP 16 (1.0 to 0.5 in 128 frames) and RMS blocks of 256 frames."""
    pth = PathEnv(dut, "b")
    await pth.b.start()
    assert pth.step == 16 and pth.n == 256
    await pth.wr(GAIN_L, 0x0800)
    await pth.run(dc(0x300000, 64))
    await pth.regs((CUR_L, CUR_R, PEAK_L, PEAK_R), "half way down the default ramp")
    rng = seeded_rng()
    await pth.run([(rng.randrange(LO, HI + 1), rng.randrange(LO, HI + 1)) for _ in range(256)])
    await pth.regs((CUR_L, RMS_L, RMS_R, WINDOWS, CLIPS_L, PEAK_L), "one 256-frame block, ramp settled")
    assert pth.m.ch[0].cur == 0x0800 and pth.m.ch[0].windows == 1


@cocotb.test()
async def test_path_bit_clock_ratios(dut):
    """The whole path at the fastest, a middle and the slowest bit clock the spec allows (8, 50 and 100 board clocks long)."""
    from benchmark.lib.audio_bench import set_ratio  # kebiso
    pth = PathEnv(dut)
    await pth.b.start()
    try:
        for ratio in (8, 50, 100):
            set_ratio(ratio)
            await pth.b.reset()
            pth.m = Model(pth.step, 3)
            await pth.run([(0x123456, -0x234567), (-0x3FFFFF, 0x2AAAAA), (7, -7)][: 3 if ratio < 100 else 2])
            await pth.regs((FRAMES, PEAK_L, PEAK_R, CUR_L), f"ratio {ratio}")
    finally:
        set_ratio(12)


@cocotb.test()
async def test_path_bit_clock_stops_in_the_middle_of_a_frame(dut):
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(GAIN_R, 0x0C00)
    await pth.run([(0x100000, 0x200000), (-0x100000, -0x200000), (5, 6), (0, 0)], pause=700)
    await pth.regs((FRAMES, PEAK_L, PEAK_R, CUR_R, CLIPS_L), "after frames with a stop between the slots")


@cocotb.test()
async def test_path_peak_returns_to_zero(dut):
    """Small readings fall by one a sample, so a quiet tail brings both meters to exactly zero."""
    pth = PathEnv(dut)
    await pth.b.start()
    await pth.wr(HOLD, 0)
    await pth.run([(40, 25)] + [(0, 0)] * 60)
    await pth.regs((PEAK_L, PEAK_R), "after a quiet tail")
    assert pth.m.ch[0].peak == 0 and pth.m.ch[1].peak == 0
