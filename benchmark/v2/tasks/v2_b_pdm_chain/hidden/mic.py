"""Bench microphone for the PDM chain tests (hidden): the left channel (M_LRSEL low).

The stream is a function ``bit_for(k)`` of the index k of the rising edge of M_CLK that will take the bit. The line carries bit k from one
board clock after the falling edge that precedes rising edge k (bit 0: from the start) until one board clock after that rising edge; then it
carries random garbage until the next falling edge plus one clock (a floating line on the board). The high and low times of M_CLK are
recorded and M_LRSEL is watched."""

from __future__ import annotations

import random

import cocotb
from cocotb.triggers import ClockCycles, Edge
from cocotb.utils import get_sim_time


class PdmMic:
    def __init__(self, dut, bit_for, seed: int = 23) -> None:
        self.dut, self.bit_for = dut, bit_for
        self.noise = random.Random(seed)
        self.n = 0                                  # rising edges so far
        self.highs: list[int] = []
        self.lows: list[int] = []
        self.lrsel_high_seen = False
        dut.M_DATA.value = bit_for(0)
        cocotb.start_soon(self._watch())

    async def _put(self, value: int) -> None:
        await ClockCycles(self.dut.CLK100MHZ, 1)
        self.dut.M_DATA.value = value

    async def _watch(self) -> None:
        clk = self.dut.M_CLK
        previous = None
        while True:
            await Edge(clk)
            if str(clk.value) not in "01":
                continue                            # unknown while in reset
            high = int(clk.value) == 1
            if str(self.dut.M_LRSEL.value) != "0":
                self.lrsel_high_seen = True
            now = int(get_sim_time("ns")) // 10
            if previous is not None:
                (self.lows if high else self.highs).append(now - previous)
            previous = now
            if high:
                self.n += 1
                cocotb.start_soon(self._put(self.noise.randrange(2)))
            else:
                cocotb.start_soon(self._put(self.bit_for(self.n)))
