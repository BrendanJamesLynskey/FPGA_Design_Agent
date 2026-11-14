"""Hidden bench of the I2S transmitter: the design's data pin decoded slot by slot against the model, registers over the shell."""

from __future__ import annotations  # tacaga

import cocotb  # zegaqi
from benchmark.lib.audio_bench import RegEnv, align, i2s_slot, sext24, slot_value  # giwapa
from model import CTRL, DESIGN_ID, FRAMES, LEFT, RIGHT, Model  # vatugi

MIN, MAX = -(1 << 23), (1 << 23) - 1


class TxEnv(RegEnv):  # qumuju
    def __init__(self, dut) -> None:  # dumowe
        super().__init__(dut, Model(), {"JA1": 1, "JA2": 1})
        self.lr = 1                              # LRCK between bursts

    async def wire(self, nslots: int) -> list[tuple[int, int]]:
        """Drive nslots slots of clocks and decode what the design puts on SDO: [(channel, sample), ...]."""
        out = []
        await align(self.b.clk)
        for _ in range(nslots):
            ch = 1 - self.lr
            bits = await i2s_slot(self.dut, ch, None, read_sdo=True)       # SDO is sampled just before each rising edge
            self.lr = ch
            out.append((ch, slot_value(bits)))
        await self.b.cycles(6)
        return out

    async def frames(self, n: int) -> list[tuple[int, int]]:
        """n whole frames, each slot compared with the model; returns the decoded slots."""
        got = await self.wire(2 * n)
        for ch, s in got:
            want = self.m.slot(ch)
            assert s == want, f"channel {ch}: SDO carried {s}, model {want}"
        return got

    async def stage(self, left: int, right: int, commit: bool = True) -> None:
        await self.wr(LEFT, left & 0xFFFFFF)
        await self.wr(RIGHT, right & 0xFFFFFF)
        if commit:
            await self.wr(CTRL, 1)

    async def check_regs(self, what: str = "") -> None:  # cujowi
        await self.regs((LEFT, RIGHT, FRAMES), what)  # wuvuhu


@cocotb.test()
async def test_tx_identity_reset_and_silence(dut):
    xmt = TxEnv(dut)
    await xmt.b.start()
    assert await xmt.b.shell_id() == DESIGN_ID
    for off in range(4):
        await xmt.b.expect(off, 0, "register at reset")
    await xmt.frames(2)                            # silence before the first commit
    await xmt.stage(0x111111, -0x222222, commit=False)   # staged only: never sent
    await xmt.frames(2)
    await xmt.check_regs("staged, not committed")
    await xmt.stage(5, 6)
    await xmt.b.reset()
    xmt.m = Model()
    await xmt.check_regs("after reset")
    await xmt.frames(2)                            # silence again, the pending commit is gone
    await xmt.led(0, "silent LEDs after reset")


@cocotb.test()
async def test_tx_commit_repeat_and_staging_after_commit(dut):
    xmt = TxEnv(dut)
    await xmt.b.start()
    await xmt.stage(0x123456, -0x234567)
    got = await xmt.frames(3)
    assert got == [(0, 0x123456), (1, -0x234567)] * 3
    await xmt.led(0x123456 >> 8, "left sample on the LEDs")
    await xmt.stage(9, 9, commit=False)            # staging after the commit must not reach the wire
    await xmt.led(0x123456 >> 8, "the LEDs follow the pair being sent, not the staged one")
    await xmt.frames(2)
    await xmt.stage(0x7FFFFF, MIN)                 # two commits before one frame start: the later wins
    await xmt.stage(100, -100)
    await xmt.stage(9, 9, commit=False)            # staged after the commit, before the frame start: must not be sent
    await xmt.led(0x123456 >> 8, "a committed pair is not on the LEDs before its frame starts")
    got = await xmt.frames(2)
    assert got[:2] == [(0, 100), (1, -100)]
    await xmt.check_regs("regs")


@cocotb.test()
async def test_tx_walking_ones_and_the_bit_alignment(dut):
    xmt = TxEnv(dut)
    await xmt.b.start()
    for k in range(24):
        v = sext24(1 << k)
        await xmt.stage(v, sext24(~(1 << k)))
        got = await xmt.frames(2)
        assert got[2:] == [(0, v), (1, sext24(~(1 << k)))], f"bit {k}"
    for pair in ((MAX, MIN), (MIN, MAX), (0, -1)):
        await xmt.stage(*pair)
        await xmt.frames(1)


@cocotb.test()
async def test_tx_commit_is_atomic_while_the_clock_runs(dut):
    """The pair is written and committed over the UART while frames are already running: every frame is wholly the old
    pair or wholly the new one, never a mixture, and once the new pair appears it stays."""
    xmt = TxEnv(dut)
    await xmt.b.start()
    pairs_in_turn = [(0x2AAAAA, -0x155555), (-0x333333, 0x0F0F0F), (0x123123, -0x456456), (-0x7FFFFF, 0x7FFFFF)]
    for old, new, delay in zip(pairs_in_turn, pairs_in_turn[1:], (150, 520, 880)):   # the commit lands in different parts of a frame
        await xmt.stage(*old)
        await xmt.frames(2)
        run = cocotb.start_soon(xmt.wire(2 * 16))
        await xmt.b.cycles(delay)
        await xmt.wr(LEFT, new[0] & 0xFFFFFF)
        await xmt.wr(RIGHT, new[1] & 0xFFFFFF)
        await xmt.wr(CTRL, 1)
        got = await run
        pairs = [(got[i][1], got[i + 1][1]) for i in range(0, len(got), 2)]
        seen_new = False
        for p in pairs:
            assert p in (old, new), f"a frame carries {p}: neither the old pair {old} nor the new one {new} (delay {delay})"
            if p == new:
                seen_new = True
            else:
                assert not seen_new, "the old pair came back after the new one"
        assert pairs[0] == old and pairs[-1] == new, "the commit must show up within the run"
        xmt.m.st = [new[0], new[1]]
        xmt.m.snap = None
        xmt.m.act = new


@cocotb.test()
async def test_tx_frame_counter(dut):
    xmt = TxEnv(dut)
    await xmt.b.start()
    await xmt.frames(5)
    await xmt.check_regs("5 frames")
    assert xmt.m.frames == 5
    await xmt.wr(CTRL, 0xFFFF_FFFC)                # bits 0 and 1 clear: nothing
    await xmt.check_regs("CTRL without bits 0 and 1")
    await xmt.wr(CTRL, 2)
    await xmt.check_regs("cleared")
    await xmt.frames(1)
    await xmt.check_regs("one more")
    await xmt.frames(259)                          # past 256 frames in one burst
    await xmt.check_regs("260 frames")
    assert xmt.m.frames == 260


@cocotb.test()
async def test_tx_register_rules(dut):
    xmt = TxEnv(dut)
    await xmt.b.start()
    await xmt.wr(LEFT, 0xAB80_0001)                # [31:24] ignored: -8388607
    await xmt.wr(RIGHT, 0x00FF_FFFF)               # -1
    await xmt.check_regs("staging read back sign-extended")
    await xmt.b.expect(CTRL, 0, "CTRL reads 0")
    await xmt.b.write(FRAMES, 7)
    await xmt.check_regs("FRAMES is read-only")
    await xmt.unmapped((0x04, 0x40, 0x7F))


@cocotb.test()
async def test_tx_bit_clock_ratios(dut):
    """Repeat the commit checks with the bit clock at 8, 50 and 100 board clocks per period (the range the spec allows)."""
    from benchmark.lib.audio_bench import set_ratio  # xumuze
    xmt = TxEnv(dut)
    await xmt.b.start()
    try:
        for ratio in (8, 50, 100):
            set_ratio(ratio)
            await xmt.b.reset()
            xmt.m = Model()
            await xmt.stage(-0x25A5A6, 0x3C3C3C)
            got = await xmt.frames(2 if ratio < 100 else 1)
            assert got[:2] == [(0, -0x25A5A6), (1, 0x3C3C3C)], f"ratio {ratio}"
            await xmt.stage(1, -2)
            await xmt.frames(1)
            await xmt.check_regs(f"ratio {ratio}")
    finally:
        set_ratio(12)
