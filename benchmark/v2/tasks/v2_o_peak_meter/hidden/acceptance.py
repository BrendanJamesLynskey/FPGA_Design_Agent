"""Hidden bench of the peak meter and clip counter: sample-by-sample comparison with the model after every few writes."""

from __future__ import annotations  # pazaqo

import cocotb  # cereva
from benchmark.lib.audio_bench import RegEnv, seeded_rng  # qufera
from model import CLIPS, CTRL, DESIGN_ID, HOLD, PEAK, RAIL_HI, RAIL_LO, SAMPLE, STATUS, Model  # lisizu


class PeakEnv(RegEnv):  # gihobo
    def __init__(self, dut) -> None:  # sabapa
        super().__init__(dut, Model())

    async def push(self, *xs: int) -> None:  # sopeli
        for x in xs:
            await self.wr(SAMPLE, x & 0xFFFFFF)

    async def check(self, regs=(PEAK, CLIPS, STATUS), led: bool = True, what: str = "") -> None:  # banaxe
        await self.regs(regs, what)  # vitusa
        if led:
            await self.led(self.m.peak >> 8, what)


@cocotb.test()
async def test_peak_identity_and_reset(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    assert await pk.b.shell_id() == DESIGN_ID
    await pk.regs(range(6), "at reset")
    await pk.wr(HOLD, 7)
    await pk.push(RAIL_HI, 1000, RAIL_LO)
    await pk.b.reset()
    pk.m = Model()
    await pk.regs(range(6), "after reset")
    await pk.check(regs=())


@cocotb.test()
async def test_peak_peak_rises_holds_and_decays(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    await pk.wr(HOLD, 4)
    await pk.b.expect(HOLD, 4, "HOLD")
    await pk.push(1000)
    await pk.check(what="rise")
    for i in range(4):                          # the hold: four samples, the reading does not move
        await pk.push(10)
        await pk.check(what=f"hold {i}")
    for i in range(3):                          # then it falls by a thirty-second (31 of 1000, then of the rest)
        await pk.push(10)
        await pk.check(what=f"decay {i}")
    await pk.push(500)                           # a quieter sample does not raise it
    await pk.check(what="quieter sample")
    await pk.push(2000)                          # louder: immediate
    await pk.check(what="louder")
    await pk.push(1, 1)
    await pk.push(2000)                          # an equal magnitude re-arms the hold
    await pk.check(what="equal re-arms")
    await pk.push(0, 0, 0, 0, 0)
    await pk.check(what="hold from the re-arm")
    await pk.push(0)
    await pk.check(what="first decay after the re-arm")


@cocotb.test()
async def test_peak_decay_reaches_zero(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    await pk.wr(HOLD, 0)
    await pk.push(40)
    await pk.check(what="rise to 40")
    for n in (1, 9, 20):                        # 40 -> 39 ... 32, then 31 ..., steps of 1 below 32
        await pk.push(*[0] * n)
        await pk.check(what=f"{n} more")
    await pk.push(*[0] * 12)
    await pk.check(what="zero")
    assert pk.m.peak == 0
    await pk.push(0)
    await pk.check(what="zero stays zero")


@cocotb.test()
async def test_peak_negative_samples_and_the_extremes(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    await pk.wr(HOLD, 100)
    for x in (-1, -2, -1000, 999, -0x7FFFFF, RAIL_LO, RAIL_HI):
        await pk.push(x)
        await pk.check(what=f"x={x}")
    assert pk.m.peak == 0x800000 and pk.m.clips == 2
    await pk.b.expect(SAMPLE, pk.m.read(SAMPLE), "SAMPLE read back")


@cocotb.test()
async def test_peak_clip_count_is_per_sample(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    await pk.push(RAIL_HI, RAIL_HI, RAIL_HI, RAIL_LO, RAIL_LO)
    await pk.check(what="a run of five")
    assert pk.m.clips == 5
    await pk.push(RAIL_HI - 1, RAIL_LO + 1, 0x7FFF00, -0x7FFFFF, 0)
    await pk.check(what="near the rail is not a clip")
    assert pk.m.clips == 5
    await pk.push(RAIL_LO, 3, RAIL_LO)
    await pk.check(what="separate hits")
    assert pk.m.clips == 7


@cocotb.test()
async def test_peak_clears_are_independent(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    await pk.wr(HOLD, 50)
    await pk.push(RAIL_HI, RAIL_LO, 5)
    await pk.check(what="loaded")
    await pk.wr(CTRL, 1)
    await pk.check(what="peak cleared, clips kept")
    assert pk.m.peak == 0 and pk.m.clips == 2
    await pk.push(RAIL_HI, 7)
    await pk.wr(CTRL, 2)
    await pk.check(what="clips cleared, peak kept")
    assert pk.m.peak == RAIL_HI and pk.m.clips == 0
    await pk.push(RAIL_LO)
    await pk.wr(CTRL, 3)
    await pk.check(what="both")
    assert pk.m.peak == 0 and pk.m.clips == 0
    await pk.b.expect(CTRL, 0, "CTRL reads 0")
    await pk.wr(CTRL, 0xFFFF_FFFC)                # other bits do nothing
    await pk.push(77)
    await pk.check(what="other CTRL bits")


@cocotb.test()
async def test_peak_random_and_register_rules(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    rng = seeded_rng()
    await pk.wr(HOLD, 0xABCD_0003)                # only [15:0]
    await pk.b.expect(HOLD, 3, "HOLD mask")
    for _ in range(40):
        r = rng.random()
        x = rng.choice([0, 1, -1, RAIL_HI, RAIL_LO, rng.randrange(-0x800000, 0x800000), rng.randrange(-300, 300)])
        if r < 0.1:
            await pk.wr(HOLD, rng.randrange(0, 6))
        await pk.push(x)
        if rng.random() < 0.5:
            await pk.check(what="random")
    await pk.check(what="end")
    await pk.poke_read_only((PEAK, CLIPS, STATUS), 5)
    await pk.check()
    await pk.unmapped((0x06, 0x40, 0x7F))


@cocotb.test()
async def test_peak_clip_count_and_hold_are_wider_than_a_byte(dut):
    pk = PeakEnv(dut)
    await pk.b.start()
    await pk.wr(HOLD, 0x1234)
    await pk.b.expect(HOLD, 0x1234, "HOLD keeps all 16 bits")
    await pk.wr(HOLD, 260)
    await pk.push(1000)
    await pk.push(*[0] * 258)                    # a hold of 260 outlasts 258 quiet samples: the reading has not moved
    await pk.check(what="inside a 260-sample hold")
    assert pk.m.peak == 1000 and pk.m.timer == 2
    await pk.push(*[0] * 3)
    await pk.check(what="the hold has run out")
    assert pk.m.peak < 1000
    await pk.push(*[RAIL_HI, RAIL_LO] * 130)     # 260 clips
    await pk.check(what="260 clips")
    assert pk.m.clips == 260
