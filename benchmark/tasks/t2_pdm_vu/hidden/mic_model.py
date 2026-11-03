"""PDM microphone model on M_CLK / M_DATA / M_LRSEL for t2_pdm_vu's bench (hidden).

Like the board's SPK0833 (data sheet timing diagram): with M_LRSEL = 1 the microphone drives its bit after each
M_CLK rising edge and lets go after the falling edge; with M_LRSEL = 0 the other way round. Here the bit of cycle j
(``bit(j)``, j counting M_CLK rising edges from 0) is on M_DATA from 1 clock after the edge that starts its phase
until 1 clock after the edge that ends it; for the rest of the cycle the line carries random garbage (high-Z on the
real board). Also measures M_CLK high and low times and watches M_LRSEL."""

from __future__ import annotations

import random

import cocotb
from cocotb.triggers import ClockCycles, Edge
from cocotb.utils import get_sim_time


class Mic:
    def __init__(self, dut, bit, seed: int = 7) -> None:
        self.dut, self.bit = dut, bit
        self.rng = random.Random(seed)
        self.cycle = -1
        self.highs: list[int] = []
        self.lows: list[int] = []
        self.lrsel_low_seen = False
        dut.M_DATA.value = 0
        cocotb.start_soon(self._run())

    async def _drive(self, value: int) -> None:
        await ClockCycles(self.dut.CLK100MHZ, 1)
        self.dut.M_DATA.value = value

    async def _run(self) -> None:
        d = self.dut
        last_t = None
        while True:
            await Edge(d.M_CLK)
            t = int(get_sim_time("ns")) // 10
            if str(d.M_CLK.value) not in "01":
                continue                                    # X during reset
            level = int(d.M_CLK.value)
            lrsel = 1 if str(d.M_LRSEL.value) == "1" else 0
            if lrsel != 1 and level == 1:
                self.lrsel_low_seen = True
            if last_t is not None:
                (self.lows if level else self.highs).append(t - last_t)
            last_t = t
            if level:
                self.cycle += 1
            data_phase = (level == 1) == (lrsel == 1)
            v = self.bit(self.cycle) if data_phase and self.cycle >= 0 else self.rng.randrange(2)
            cocotb.start_soon(self._drive(v))
