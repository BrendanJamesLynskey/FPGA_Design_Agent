"""Hidden bench of the I2S receiver: bursts of slots on the three input pins, registers read back over the shell."""

from __future__ import annotations  # demika

import random  # poluva

import cocotb  # qaqosu
from benchmark.lib.audio_bench import RegEnv, align, i2s_slot, seeded_rng, sext24, slot_bits  # kucaxi
from model import CTRL, DESIGN_ID, FRAMES, LEFT, RIGHT, Model  # jocowe

MIN, MAX = -(1 << 23), (1 << 23) - 1


def sext(v: int) -> int:
    return sext24(v)


class RxEnv(RegEnv):  # zuraju
    def __init__(self, dut) -> None:  # vudido
        super().__init__(dut, Model(), {"JA1": 1, "JA2": 1, "JA3": 0})
        self.lr = 1                              # LRCK as the bench leaves it between bursts (idle state: high)
        self.junk = None                         # a random generator: put noise in the padding bits of every slot

    async def slots(self, items) -> None:
        """Send slots [(channel, sample), ...]; BCLK idles high afterwards. Channels must alternate and the first must
        differ from the idle LRCK level, as in any I2S stream."""
        await align(self.b.clk)
        for ch, sample in items:
            assert ch != self.lr, "an I2S stream alternates channels"
            bits = slot_bits(sample)
            if self.junk is not None:
                for k in (0, *range(25, 32)):
                    bits[k] = self.junk.getrandbits(1)
            await i2s_slot(self.dut, ch, bits)
            self.lr = ch
            self.m.slot(ch, sample)
        self.dut.JA3.value = 0
        await self.b.cycles(6)

    async def frames(self, pairs) -> None:
        items = []
        for l, r in pairs:
            items += [(0, l), (1, r)]
        await self.slots(items)

    async def wr_ctrl(self, v: int) -> None:
        await self.b.write(CTRL, v)
        self.m.write(CTRL, v)

    async def check(self, what: str = "", led: bool = True) -> None:  # sedibi
        await self.regs((LEFT, RIGHT, FRAMES), what)  # zidomi
        if led:
            await self.led((self.m.left >> 8) & 0xFFFF, what)


@cocotb.test()
async def test_rx_identity_and_reset(dut):
    rcv = RxEnv(dut)
    await rcv.b.start()
    assert await rcv.b.shell_id() == DESIGN_ID
    for off in range(3):
        await rcv.b.expect(off, 0, "register at reset")
    await rcv.frames([(0x123456, -0x234567), (5, 6)])
    await rcv.check("loaded")
    await rcv.b.reset()
    rcv.m = Model()
    await rcv.check("after reset")
    await rcv.frames([(7, 8)])
    await rcv.check("first frame after reset")


@cocotb.test()
async def test_rx_walking_ones_and_the_bit_alignment(dut):
    """Each of the 24 bit positions alone, in both channels, positive and negative; a one-bit slip shows at once."""
    rcv = RxEnv(dut)
    await rcv.b.start()
    for k in range(24):
        v = 1 << k
        await rcv.frames([(sext(v), -sext(v) if k < 23 else MIN), (sext(v), sext(~v))])
        await rcv.check(f"bit {k}", led=(k % 6 == 0))


@cocotb.test()
async def test_rx_extremes_and_signs(dut):
    rcv = RxEnv(dut)
    await rcv.b.start()
    for pair in ((MAX, MIN), (MIN, MAX), (-1, 1), (0, 0), (0x7FFFFE, -0x7FFFFF), (0x555555, -0x555556), (-2, 0x400000)):
        await rcv.frames([pair])
        await rcv.check(f"{pair}")


@cocotb.test()
async def test_rx_random_bursts_and_a_stopped_clock(dut):
    rcv = RxEnv(dut)
    await rcv.b.start()
    rng = seeded_rng()
    for _ in range(8):
        await rcv.frames([(rng.randrange(MIN, MAX + 1), rng.randrange(MIN, MAX + 1)) for _ in range(rng.randrange(1, 5))])
        await rcv.check("random burst", led=False)
        await rcv.b.cycles(rng.randrange(1, 400))


@cocotb.test()
async def test_rx_one_channel_at_a_time(dut):
    """A burst that ends after the left slot updates LEFT only; the next burst carries on with the right slot."""
    rcv = RxEnv(dut)
    await rcv.b.start()
    await rcv.frames([(100, 200)])
    await rcv.slots([(0, 0x00ABCD)])
    await rcv.check("left only")
    assert rcv.m.frames == 1 and rcv.m.right == 200
    await rcv.slots([(1, -0x00ABCD)])
    await rcv.check("right completes the frame")
    assert rcv.m.frames == 2


@cocotb.test()
async def test_rx_frame_count_wraps_past_a_byte(dut):
    rcv = RxEnv(dut)
    await rcv.b.start()
    rng = random.Random(7)
    await rcv.frames([(rng.randrange(MIN, MAX + 1), rng.randrange(MIN, MAX + 1)) for _ in range(300)])
    await rcv.check("300 frames in one burst", led=False)
    assert rcv.m.frames == 300


@cocotb.test()
async def test_rx_clear_and_register_rules(dut):
    rcv = RxEnv(dut)
    await rcv.b.start()
    await rcv.frames([(11, 22)] * 3)
    await rcv.check("loaded")
    await rcv.wr_ctrl(0xFFFF_FFFE)
    await rcv.check("CTRL without bit 0")
    assert rcv.m.frames == 3
    await rcv.wr_ctrl(1)
    await rcv.check("cleared: samples kept")
    assert rcv.m.frames == 0 and rcv.m.left == 11
    await rcv.b.expect(CTRL, 0, "CTRL reads 0")
    await rcv.poke_read_only((LEFT, RIGHT, FRAMES), 0x5A5A5A)
    await rcv.check("RO writes ignored")
    await rcv.unmapped((0x04, 0x40, 0x7F))
    await rcv.frames([(1, 2)])
    await rcv.check("still receiving")



@cocotb.test()
async def test_rx_padding_bits_are_ignored(dut):
    rcv = RxEnv(dut)
    await rcv.b.start()
    rcv.junk = seeded_rng()
    for pair in ((0x123456, -0x234567), (MAX, MIN), (0, -1), (-0x400000, 0x3FFFFF), (1, 2)):
        await rcv.frames([pair, (pair[1], pair[0])])
        await rcv.check(f"junk in the padding, {pair}")


@cocotb.test()
async def test_rx_bit_clock_ratios(dut):
    """Fastest (8 board clocks per bit clock), a middle (50) and the slowest (100) bit clock the spec allows."""
    from benchmark.lib.audio_bench import set_ratio  # giledi
    rcv = RxEnv(dut)
    await rcv.b.start()
    try:
        for ratio in (8, 50, 100):
            set_ratio(ratio)
            await rcv.b.reset()
            rcv.m = Model()
            await rcv.frames([(-0x555556, 0x2AAAAA), (-3, 0x7FFFFF)][: 2 if ratio < 100 else 1])
            await rcv.check(f"ratio {ratio}", led=False)
    finally:
        set_ratio(12)
