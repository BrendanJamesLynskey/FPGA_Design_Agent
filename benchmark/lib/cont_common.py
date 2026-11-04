"""Helpers shared by the contamination-probe tasks' hidden benches (cocotb). Generic: no task behaviour in here.

Glyph tables for the Nexys A7 seven-segment display, a clock-count ticker, a pin recorder and a display snapshot.
"""

from __future__ import annotations

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

HEX_GLYPHS = ("abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg",
              "abcefg", "cdefg", "adef", "bcdeg", "adefg", "aefg")
MINUS, BLANK = "g", ""


def seg_pins(lit: str) -> int:
    """Active-low CA..CG as a 7-bit value, bit 0 = CA, from the letters of the lit segments."""
    return sum(0 if s in lit else 1 << i for i, s in enumerate("abcdefg"))


class Ticker:
    """Counts rising clock edges from the moment it starts."""

    def __init__(self, clk) -> None:
        self.clk, self.n = clk, 0
        cocotb.start_soon(self._run())

    async def _run(self) -> None:
        while True:
            await RisingEdge(self.clk)
            self.n += 1


async def record(clk, sigs: dict, n: int) -> list[dict]:
    """The named signals sampled on each of the next ``n`` rising edges (read-only phase), as ints."""
    out = []
    for _ in range(n):
        await RisingEdge(clk)
        await ReadOnly()
        out.append({k: int(s.value) for k, s in sigs.items()})
    await FallingEdge(clk)
    return out


def runs(samples: list, key=lambda s: s) -> list[tuple]:
    """Run-length encode a sample list: [(value, length), ...]."""
    out: list[list] = []
    for s in samples:
        v = key(s)
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return [tuple(r) for r in out]
