"""Shared helpers of the pool's hidden acceptance benches (cocotb). Nothing here knows a spec's behaviour."""

from __future__ import annotations

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
from cocotb.utils import get_sim_time

#: standard hexadecimal glyphs on a 7-segment digit (segments lit); pins are active low, bit 0 = CA = segment a
HEX_GLYPHS = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg",
              "7": "abc", "8": "abcdefg", "9": "abcdfg", "A": "abcefg", "b": "cdefg", "C": "adef", "d": "bcdeg",
              "E": "adefg", "F": "aefg", "-": "g", " ": "", "P": "abefg", "r": "eg", "n": "ceg", "o": "cdeg",
              "L": "def", "H": "bcefg", "U": "bcdef", "t": "defg", "J": "bcde", "S": "acdfg"}


def seg_pins_of(ch: str) -> int:
    """Active-low CA..CG for a glyph character of HEX_GLYPHS (bit 0 = CA)."""
    lit = HEX_GLYPHS[ch]
    return sum(0 if s in lit else 1 << i for i, s in enumerate("abcdefg"))


def now_clk() -> int:
    """Simulation time in 10 ns clocks."""
    return int(get_sim_time("ns")) // 10


def val(sig) -> int:
    try:
        return int(sig.value)
    except ValueError:
        return -1                   # X or Z


class Monitor:
    """Records the named signals on every rising clock edge (values as settled after the edge)."""

    def __init__(self, clk, **sigs) -> None:
        self.clk, self.sigs = clk, sigs
        self.t: list[int] = []
        self.v: dict[str, list[int]] = {k: [] for k in sigs}
        cocotb.start_soon(self._run())

    async def _run(self) -> None:
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()
            self.t.append(now_clk())
            for k, s in self.sigs.items():
                try:
                    self.v[k].append(s() if callable(s) else val(s))
                except ValueError:                       # X or Z on a lambda-read signal
                    self.v[k].append(-1)

    def mark(self) -> int:
        return len(self.t)

    def since(self, name: str, mark: int = 0) -> list[int]:
        return self.v[name][mark:]


def runs(seq: list[int]) -> list[tuple[int, int, int]]:
    """Run-length encoding: [(value, start index, length)]."""
    out: list[tuple[int, int, int]] = []
    for i, x in enumerate(seq):
        if out and out[-1][0] == x:
            v, s, n = out[-1]
            out[-1] = (v, s, n + 1)
        else:
            out.append((x, i, 1))
    return out


def high_runs(seq: list[int]) -> list[tuple[int, int]]:
    """[(start, length)] of every run of 1s that starts and ends inside the sequence."""
    r = runs(seq)
    return [(s, n) for (v, s, n) in r[1:-1] if v == 1] if len(r) > 2 else []


def rising(seq: list[int]) -> list[int]:
    return [i for i in range(1, len(seq)) if seq[i] == 1 and seq[i - 1] == 0]


def falling(seq: list[int]) -> list[int]:
    return [i for i in range(1, len(seq)) if seq[i] == 0 and seq[i - 1] == 1]


async def idle(clk, n: int) -> None:
    for _ in range(n):
        await RisingEdge(clk)
    await FallingEdge(clk)


def same(got, want, what: str) -> None:
    assert got == want, f"{what}: RTL {got!r}, model {want!r}"


async def wait_rise(clk, mon: Monitor, name: str, limit: int = 100000) -> None:
    """Wait (as seen by the monitor, to within a clock) for the next 0 -> 1 on a monitored signal."""
    for _ in range(limit):
        await RisingEdge(clk)
        if mon.v[name][-2:] == [0, 1]:
            await FallingEdge(clk)
            return
    raise AssertionError(f"no rising edge on {name} within {limit} clocks")


def align(rtl: list[int], model: list[int], max_shift: int = 4, what: str = "output") -> int:
    """Smallest shift s in 0..max_shift with rtl[i + s] == model[i] for every i (the RTL may lag a cycle model by
    a few output-register clocks, no more). Raises AssertionError describing the first mismatch at the best shift."""
    best = None
    for s in range(max_shift + 1):
        n = min(len(model), len(rtl) - s)
        bad = next((i for i in range(n) if rtl[i + s] != model[i]), None)
        lead = next((i for i in range(s) if rtl[i] != model[0]), None)
        if bad is None and lead is None:
            return s
        if best is None or (bad if bad is not None else n) > best[1]:
            best = (s, bad if bad is not None else n, bad)
    s, _, bad = best
    where = f"at sample {bad}: RTL {rtl[bad + s]!r}, model {model[bad]!r}" if bad is not None else "in the lead-in"
    raise AssertionError(f"{what} differs from the model {where} (best shift {s}); RTL {rtl[max(0, (bad or 0) + s - 3):(bad or 0) + s + 4]} model {model[max(0, (bad or 0) - 3):(bad or 0) + 4]}")


async def script(dut, name: str, steps, clk) -> None:
    """Drive dut.<name> through (value, clocks) steps."""
    for v, n in steps:
        getattr(dut, name).value = v
        for _ in range(n):
            await RisingEdge(clk)
    await FallingEdge(clk)
