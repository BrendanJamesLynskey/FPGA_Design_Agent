"""Bench model of the PDM microphone with M_LRSEL low (hidden).

Data bit ``bit(n)`` is for the n-th rising edge of M_CLK seen so far (n = 0, 1, ...). It is on M_DATA from one board
clock after the falling edge before that rising edge (bit 0: from the start) until one board clock after the rising
edge; between that and the next falling edge (plus one clock) the line carries random garbage (floating on the
real board). Also measures the high and low times of M_CLK and watches M_LRSEL."""

from __future__ import annotations

import random

import cocotb
from cocotb.triggers import ClockCycles, Edge
from cocotb.utils import get_sim_time


class Mic:
    def __init__(self, dut, bit, seed: int = 11) -> None:
        self.dut, self.bit = dut, bit
        self.rng = random.Random(seed)
        self.n = 0                              # rising edges seen
        self.highs: list[int] = []
        self.lows: list[int] = []
        self.lrsel_high_seen = False
        dut.M_DATA.value = bit(0)
        cocotb.start_soon(self._run())

    async def _drive(self, value: int) -> None:
        await ClockCycles(self.dut.CLK100MHZ, 1)
        self.dut.M_DATA.value = value

    async def _run(self) -> None:
        d = self.dut
        last_t = None
        while True:
            await Edge(d.M_CLK)
            if str(d.M_CLK.value) not in "01":
                continue                         # X during reset
            level = int(d.M_CLK.value)
            if str(d.M_LRSEL.value) != "0":
                self.lrsel_high_seen = True
            t = int(get_sim_time("ns")) // 10
            if last_t is not None:
                (self.lows if level else self.highs).append(t - last_t)
            last_t = t
            if level:
                self.n += 1
                cocotb.start_soon(self._drive(self.rng.randrange(2)))      # garbage from one clock later
            else:
                cocotb.start_soon(self._drive(self.bit(self.n)))           # the bit for the next rising edge
