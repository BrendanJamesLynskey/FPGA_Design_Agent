"""Acceptance tests of v2_b_pdm_chain against model.py (hidden from the agent)."""

from __future__ import annotations

import math
import random

import cocotb
from benchmark.lib.bench import Board, peek
from mic import PdmMic
from model import CAP0, COUNT, CTRL, DESIGN_ID, FS_PDM, LAT_BITS, STATUS, first_audio, run

NBITS = LAT_BITS + 64 * 64 + 64                  # enough PDM samples for 64 audio samples
LEN = NBITS + 6000                               # the bench keeps the stream_pc going until it stops the run


def delta_sigma_pc(f: float, amp: float, n: int) -> list[int]:
    """A second-order delta-sigma bit stream_pc of a sine at f Hz (3.125 MHz sample rate)."""
    i1 = i2 = 0.0
    q_pc = -1.0
    out = []
    for k in range(n):
        x = amp * math.sin(2 * math.pi * f * k / FS_PDM)
        i1 += x - q_pc
        i2 += i1 - q_pc
        q_pc = 1.0 if i2 >= 0 else -1.0
        out.append(1 if q_pc > 0 else 0)
    return out


class Env_pc:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"M_DATA": 0})
        self.bits: list[int] = [0] * LEN
        self.base_pc = 0

    async def start(self) -> None:
        await self.b.start()
        self.mic = PdmMic(self.dut, lambda n: self.bit_at_pc(n - self.base_pc))

    def bit_at_pc(self, i: int) -> int:
        return self.bits[i] if 0 <= i < len(self.bits) else 0

    async def begin_pc(self, ctrl: int) -> None:
        """Write CTRL with RUN = 1 (and maybe ARM) from RUN = 0; the stream_pc starts at bit 0."""
        self.base_pc = self.mic.n
        self.dut.M_DATA.value = self.bit_at_pc(0)
        await self.b.write(CTRL, ctrl)

    async def wait_done_pc(self, limit: int = 40) -> None:
        for _ in range(limit):
            if (await self.b.read(STATUS)) & 1:
                return
            await self.b.cycles(2000)
        raise AssertionError("capture_pc never completed")

    async def capture_pc(self) -> list[int]:
        await self.wait_done_pc()
        await self.b.write(CTRL, 0)
        got = []
        for i in range(64):
            v = await self.b.read(CAP0 + i)
            got.append(v - (1 << 32) if v & 0x8000_0000 else v)
        return got

    async def check_capture_pc(self, what: str, bits: list[int]) -> None:
        self.bits = bits
        await self.begin_pc(3)
        got = await self.capture_pc()
        want = first_audio(bits)
        assert got == want, f"{what}: first mismatch at sample {next(i for i, (g, w) in enumerate(zip(got, want)) if g != w)}: " \
                            f"RTL {got[:6]}..., model {want[:6]}..."


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env_pc(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in (CTRL, STATUS, COUNT, 0x03, 0x3F, CAP0, CAP0 + 63):
        await e.b.expect(off, 0, "register at reset")
    await e.begin_pc(3)
    await e.b.cycles(3000)
    await e.b.reset()
    for off in (CTRL, STATUS, COUNT, CAP0):
        await e.b.expect(off, 0, "register after reset")
    assert int(dut.M_CLK.value) == 0
    assert await peek(e.b.clk, dut.LED) == 0


@cocotb.test()
async def test_clock_and_channel_select(dut):
    e = Env_pc(dut)
    await e.start()
    half_pc = e.b.param("CLK_HALF")
    await e.begin_pc(1)
    await e.b.cycles(12 * 2 * half_pc)
    assert await peek(e.b.clk, dut.LED) & 1 == 1, "LED[0] shows RUN"
    await e.b.write(CTRL, 0)
    assert set(e.mic.highs[1:-1]) == {half_pc} and set(e.mic.lows[1:]) == {half_pc}
    assert not e.mic.lrsel_high_seen
    n = e.mic.n
    for _ in range(6 * half_pc):
        assert await peek(e.b.clk, dut.M_CLK) == 0
    assert e.mic.n == n


@cocotb.test()
async def test_capture_of_a_tone(dut):
    e = Env_pc(dut)
    await e.start()
    await e.check_capture_pc("1 kHz tone", delta_sigma_pc(1000.0, 0.5, LEN))
    assert await peek(e.b.clk, dut.LED) & 2, "LED[1] shows DONE"


@cocotb.test()
async def test_capture_of_random_bits(dut):
    e = Env_pc(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.check_capture_pc("random bits", [rng.randrange(2) for _ in range(LEN)])


@cocotb.test()
async def test_digital_full_scale_saturates(dut):
    e = Env_pc(dut)
    await e.start()
    await e.check_capture_pc("all ones", [1] * LEN)
    assert (await e.b.read(STATUS)) & 4, "SAT after full scale"
    await e.check_capture_pc("all zeros", [0] * LEN)           # RUN start clears SAT, then it is set again
    assert (await e.b.read(STATUS)) & 4
    assert await peek(e.b.clk, dut.LED) & 4, "LED[2] shows SAT"


@cocotb.test()
async def test_small_signal_does_not_set_sat(dut):
    e = Env_pc(dut)
    await e.start()
    await e.check_capture_pc("quiet tone", delta_sigma_pc(2000.0, 0.1, LEN))
    assert (await e.b.read(STATUS)) & 4 == 0, "no limit acted: SAT must stay 0"
    assert run(e.bits[:LAT_BITS + 64 * 63]).sat_pc == 0


@cocotb.test()
async def test_run_start_clears_the_chain_and_count(dut):
    e = Env_pc(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 5)
    await e.check_capture_pc("first run", [1] * LEN)           # leaves the integrators full of state, SAT and COUNT set
    c1 = await e.b.read(COUNT)
    assert c1 >= 64
    await e.check_capture_pc("second run from empty", [rng.randrange(2) for _ in range(LEN)])
    s = e.mic.n - e.base_pc
    c2 = await e.b.read(COUNT)
    expect = (s - LAT_BITS) // 64 + 1
    assert abs(c2 - expect) <= 1, f"COUNT {c2}, about {expect} audio samples since the RUN start"
    assert (await e.b.read(STATUS)) & 4 == 0, "SAT cleared by the RUN start, and a random stream_pc never limits"


@cocotb.test()
async def test_arm_and_capture_rules(dut):
    e = Env_pc(dut)
    await e.start()
    e.bits = delta_sigma_pc(1500.0, 0.4, LEN)
    await e.b.expect(CAP0, 0, "CAP reads 0 before any capture_pc")
    await e.b.write(CTRL, 2)                                    # ARM while idle, RUN afterwards
    assert await e.b.read(STATUS) & 3 == 2, "ARMED, not DONE"
    await e.begin_pc(1)
    await e.b.expect(CTRL, 1, "RUN reads 1, ARM reads 0")
    got = await e.capture_pc()
    assert got == first_audio(e.bits)
    assert await e.b.read(STATUS) & 3 == 1, "DONE after the capture_pc, ARMED back to 0"
    assert await e.b.read(CAP0 + 5) == got[5] & 0xFFFF_FFFF, "CAP stays after RUN goes 0"
    await e.begin_pc(1)                                            # a RUN start without ARM keeps DONE and CAP
    assert await e.b.read(STATUS) & 1 == 1, "DONE survives a RUN start"
    assert await e.b.read(CAP0 + 5) == got[5] & 0xFFFF_FFFF, "CAP survives a RUN start"
    await e.b.write(CTRL, 0)
    await e.b.write(CTRL, 2)                                    # a new ARM clears DONE
    assert await e.b.read(STATUS) & 3 == 2, "re-armed: DONE cleared"
    await e.b.expect(CAP0 + 5, 0, "CAP reads 0 while DONE = 0")
    await e.b.reset()                                           # reset disarms
    assert await e.b.read(STATUS) & 3 == 0
    await e.begin_pc(1)                                            # RUN without ARM
    await e.b.write(CTRL, 3)                                    # ARM while RUN = 1: ignored
    await e.b.cycles(45000)
    assert await e.b.read(STATUS) & 3 == 0, "ARM while running must be ignored"
    await e.b.expect(CAP0, 0, "nothing captured")
    assert await e.b.read(COUNT) >= 64


@cocotb.test()
async def test_partial_capture_restarts_at_the_next_run(dut):
    e = Env_pc(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED) + 9)
    e.bits = [rng.randrange(2) for _ in range(LEN)]
    await e.begin_pc(3)
    await e.b.cycles(12000)                                     # some samples stored, capture_pc not done
    st = await e.b.read(STATUS)
    assert st & 1 == 0, "this test needs a capture_pc that is still running"
    await e.b.write(CTRL, 0)
    e.bits = [rng.randrange(2) for _ in range(LEN)]
    await e.begin_pc(1)                                            # the armed capture_pc starts again at CAP[0]
    got = await e.capture_pc()
    assert got == first_audio(e.bits), "a partial capture_pc restarts at CAP[0] when RUN starts again"


@cocotb.test()
async def test_register_rules(dut):
    e = Env_pc(dut)
    await e.start()
    await e.b.write(CTRL, 0xFFFF_FFFC)                          # bits above 1 ignored
    await e.b.expect(CTRL, 0, "CTRL masks")
    await e.b.write(STATUS, 0x7)
    await e.b.write(COUNT, 5)
    await e.b.write(CAP0, 5)
    for off in (STATUS, COUNT, CAP0, 0x03, 0x20, 0x3F, 0x7F):
        await e.b.expect(off, 0, "RO write ignored, unmapped reads 0")


@cocotb.test()
async def test_product_numbers_of_the_model(dut):
    """Passband, alias rejection and SNR of the model the design is tied to (spec product_numbers)."""
    import numpy as np
    fo = FS_PDM / 64

    def level(f: float, amp: float, n: int) -> float:
        out = np.array(run(delta_sigma_pc(f, amp, n)).out[8:], dtype=float)
        k = np.arange(len(out))
        fa = f % fo
        fa = min(fa, fo - fa)
        return float(np.abs(np.sum(out * np.exp(-2j * np.pi * fa / fo * k))) * 2 / len(out)) / (amp * 32768)

    n = int(FS_PDM * 0.04)
    ref = level(1000.0, 0.5, n)
    for f in (200, 500, 2000, 5000, 8000, 12000, 15000):
        db = 20 * math.log10(level(f, 0.5, n) / ref)
        assert abs(db) <= 1.0, f"passband {f} Hz: {db:.2f} dB"
    for f in (40e3, 45e3, 52e3, 58e3, 62e3, 63.8e3, 100e3, 150e3, 190e3, 195.3125e3 + 5e3, 300e3, 1e6):
        db = 20 * math.log10(level(f, 0.5, n) / ref)
        assert db <= -35.0, f"alias of {f / 1e3:.1f} kHz: {db:.1f} dB"
    npts = 2048
    fb = round(1000 / (fo / npts))
    f0 = fb * fo / npts
    out = np.array(run(delta_sigma_pc(f0, 0.5, (npts + 1000) * 64)).out[900:900 + npts], dtype=float)
    w = np.hanning(npts)
    x = np.abs(np.fft.rfft(out * w)) ** 2
    fr = np.arange(len(x)) * fo / npts
    sig = x[fb - 3:fb + 4].sum()
    noise = x[(fr >= 100) & (fr <= 15000)].sum() - sig
    snr = 10 * math.log10(sig / noise)
    assert snr >= 70.0, f"SNR {snr:.1f} dB"
