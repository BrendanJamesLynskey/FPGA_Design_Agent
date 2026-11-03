"""VGA output sampling for the benchmark's hidden benches (cocotb), without a Python callback on every clock.

Times are clock indices (10 ns clock started at t = 0 by bench.Board): "the value during clock c" is read just
after the rising edge of clock c, so a registered output that changes at edge c is seen at c. Sync edges are found
with edge triggers, pixels are sampled at computed clocks with timers, so a whole frame (1.4 M clocks) costs only
the simulator's time plus a few thousand Python wake-ups.
"""

from __future__ import annotations

from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer
from cocotb.utils import get_sim_time

PERIOD_NS = 10


def now_clock() -> int:
    return int(get_sim_time("ns")) // PERIOD_NS


def rgb(dut) -> int:
    """12-bit colour from VGA_R/G/B (R in [11:8])."""
    return int(dut.VGA_R.value) << 8 | int(dut.VGA_G.value) << 4 | int(dut.VGA_B.value)


async def edge_clock(sig, rising: bool = True) -> int:
    """Wait for the next rising (or falling) edge of ``sig``; returns its clock index."""
    await (RisingEdge(sig) if rising else FallingEdge(sig))
    return now_clock()


async def at_clock(c: int) -> None:
    """Advance to just after the rising edge of clock ``c`` (read-only phase). ``c`` must be in the future."""
    t = c * PERIOD_NS + 1
    now = int(get_sim_time("ns"))
    assert t > now, f"sampling clock {c} is in the past (now {now} ns)"
    await Timer(t - now, "ns")
    await ReadOnly()


async def sample(dut, clocks: list[int], sigs=("rgb",)) -> list[tuple]:
    """For each clock index (increasing), the tuple of the named signals ("rgb" = the 12-bit colour)."""
    out = []
    for c in clocks:
        await at_clock(c)
        out.append(tuple(rgb(dut) if s == "rgb" else int(getattr(dut, s).value) for s in sigs))
    await Timer(1, "ns")                     # leave the read-only phase
    return out
