"""Shared pieces of the audio tasks' hidden benches (benchmark v2, domain O, brief 78).

Plain helpers for the two things every audio task needs and none of them is about: 24-bit sample arithmetic and the wire
level of an I2S slot. The behaviour under test (what a design does with the bits) is in each task's own ``model.py``.

``i2s_slot`` drives one 32-clock channel slot of an I2S bus the way a codec does it: the word select changes on the falling
edge of the bit clock, the data a little later (``DATA_DELAY`` board clocks after the falling edge, so a receiver that samples
on the wrong edge reads the previous bit), and the bit clock idles high between bursts. It can also sample the design's data
output just before each rising edge. The bit clock is ``2 * HALF`` board clocks long.
"""

from __future__ import annotations

from cocotb.triggers import FallingEdge, Timer

HALF = 6            # board clocks per half bit clock
DATA_DELAY = 4      # board clocks between a falling edge and the codec's data change
SLOT_BITS = 32


def sext24(v: int) -> int:
    """The signed value of the low 24 bits of v."""
    return ((v & 0xFFFFFF) ^ 0x800000) - 0x800000


def slot_bits(sample: int) -> list[int]:
    """The data line over one slot, one value per falling edge F0 .. F31 (F0 is the edge where the word select changes):
    a padding zero, the 24 data bits MSB first, seven padding zeros."""
    u = sample & 0xFFFFFF
    return [0] + [(u >> (23 - i)) & 1 for i in range(24)] + [0] * 7


def slot_value(bits: list[int]) -> int:
    """The sample in a slot's 32 data values (as slot_bits makes them); the padding must be zero."""
    assert len(bits) == SLOT_BITS and bits[0] == 0 and not any(bits[25:]), f"padding bits are not zero: {bits}"
    u = 0
    for b in bits[1:25]:
        u = (u << 1) | b
    return sext24(u)


def set_ratio(ratio: int) -> None:
    """Make the bit clock ``ratio`` board clocks long (an even number from 8 to 100); the codec's data change lands a quarter
    of a bit clock after the falling edge. ``set_ratio(12)`` is the default."""
    global HALF, DATA_DELAY
    HALF = ratio // 2
    DATA_DELAY = max(1, HALF * 2 // 3)


async def i2s_slot(dut, channel: int, data: list[int] | None = None, read_sdo: bool = False, lrck: str = "JA1",
                   bclk: str = "JA2", sdi: str = "JA3", sdo: str = "JA4") -> list[int]:
    """One slot on the bus. ``channel`` is the word-select level (0 left, 1 right); ``data`` the 32 values for the design's
    data input (None: leave it alone); with ``read_sdo`` the design's data output is sampled one nanosecond before each rising
    edge and returned, and again one nanosecond before the next falling edge: the two must agree, because a codec samples on
    the rising edge and the line must not move after it. The caller is aligned to the falling edge of the board clock."""
    seen: list[int] = []
    for k in range(SLOT_BITS):
        getattr(dut, bclk).value = 0
        if k == 0:
            getattr(dut, lrck).value = channel
        await Timer(DATA_DELAY * 10, "ns")
        if data is not None:
            getattr(dut, sdi).value = data[k]
        await Timer((HALF - DATA_DELAY) * 10 - (1 if read_sdo else 0), "ns")
        if read_sdo:
            seen.append(int(getattr(dut, sdo).value))
            await Timer(1, "ns")
        getattr(dut, bclk).value = 1
        if read_sdo:
            await Timer(HALF * 10 - 1, "ns")
            late = int(getattr(dut, sdo).value)
            assert late == seen[-1], f"the data line moved after the rising edge of bit clock {k} of the slot"
            await Timer(1, "ns")
        else:
            await Timer(HALF * 10, "ns")
    return seen


class Inst:
    """One of several copies of a design in a wrapper testbench, each with its own parameters: the bench's ``Board`` and
    helpers see it as a plain design. A port ``X`` is the wrapper's signal ``X_<suffix>`` (the clock is shared); a parameter
    listed in ``params`` reads as that value."""

    class _Const:
        def __init__(self, v: int) -> None:
            self.value = v

    def __init__(self, dut, suffix: str, **params: int) -> None:
        self._dut, self._sfx, self._params = dut, suffix, params

    def __getattr__(self, name: str):
        if name in self._params:
            return Inst._Const(self._params[name])
        if name == "CLK100MHZ":
            return self._dut.CLK100MHZ
        return getattr(self._dut, f"{name}_{self._sfx}")


async def align(clk) -> None:
    """Wait for the falling edge of the board clock, so that the bench's changes land mid-cycle."""
    await FallingEdge(clk)


# ---- register-window helpers shared by the audio benches -------------------------------------------------------------------

import random  # noqa: E402

import cocotb  # noqa: E402
from benchmark.lib.bench import Board, peek  # noqa: E402


def seeded_rng() -> random.Random:
    """The random generator of a test: seeded from cocotb's seed, so a failing run can be repeated."""
    return random.Random(int(cocotb.RANDOM_SEED))


class RegEnv:
    """A task's board, its golden model and the register helpers every audio bench uses. Subclasses add the bus and the task's
    own ``check``. ``self.m`` is the model: its ``read(offset)`` is what a register must hold and its ``write`` follows the host."""

    def __init__(self, dut, model, inputs: dict | None = None) -> None:
        self.dut, self.m = dut, model
        self.b = Board(dut, inputs or {})

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def regs(self, offsets, what: str = "") -> None:
        """Every register in ``offsets`` against the model."""
        for r in offsets:
            await self.b.expect(r, self.m.read(r), f"{what} reg 0x{r:02X}")

    async def led(self, want: int, what: str = "") -> None:
        got = await peek(self.b.clk, self.dut.LED)
        assert got == want, f"LED {got:04X}, model {want:04X} {what}"

    async def unmapped(self, offsets=(0x40, 0x7F)) -> None:
        for off in offsets:
            await self.b.expect(off, 0, f"unmapped offset 0x{off:02X}")

    async def poke_read_only(self, offsets, value: int = 0x5A5A) -> None:
        """Writes to read-only registers must change nothing (the caller then compares every register with the model)."""
        for off in offsets:
            await self.b.write(off, value)
