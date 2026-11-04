"""A generic SPI slave on the Pmod JB pins for t2_spi_master_modes's bench (hidden).

It samples CS_N, SCLK and MOSI on every clock and records every SCLK edge as (clock, level, MOSI) and every CS_N
change as (clock, level). It drives MISO like a real slave of the configured mode: CPHA 0 - the next bit when CS_N
falls and after each trailing edge; CPHA 1 - after each leading edge. ``miso`` is the bit queue (0 when empty)."""

from __future__ import annotations

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge, Timer


class SpiSlave:
    def __init__(self, dut, cs="JB1", sclk="JB4", mosi="JB2", miso="JB3") -> None:
        self.dut = dut
        self.clk = dut.CLK100MHZ
        self.cs, self.sclk, self.mosi, self.miso = (getattr(dut, n) for n in (cs, sclk, mosi, miso))
        self.cpol = self.cpha = 0
        self.queue: list[int] = []
        self.edges: list[tuple[int, int, int]] = []
        self.cs_events: list[tuple[int, int]] = []
        self.idle_bad: list[str] = []
        self.miso.value = 0
        self.n = 0
        self.out_bit: int | None = None
        cocotb.start_soon(self._run())

    def mode(self, cpol: int, cpha: int, queue: list[int] | None = None) -> None:
        self.cpol, self.cpha = cpol, cpha
        self.queue = list(queue or [])
        if cpha == 0 and int(self.cs.value) == 0 and self.queue:
            self.out_bit = self.queue.pop(0)        # CS_N already held low: the next bit is out already
            self.miso.value = self.out_bit
        self.edges.clear()
        self.cs_events.clear()
        self.idle_bad.clear()

    async def _run(self) -> None:
        prev_cs, prev_sclk = 1, None
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()
            self.n += 1
            cs, sclk, mosi = int(self.cs.value), int(self.sclk.value), int(self.mosi.value)
            drive = None
            if cs != prev_cs:
                self.cs_events.append((self.n, cs))
                if cs == 1 and self.out_bit is not None:
                    self.queue.insert(0, self.out_bit)     # put out but never sampled: the slave reloads it
                    self.out_bit = None
                if cs == 0:
                    if sclk != self.cpol:
                        self.idle_bad.append(f"SCLK={sclk} at CS_N fall, CPOL={self.cpol}")
                    if self.cpha == 0:
                        drive = self.queue.pop(0) if self.queue else 0
            if prev_sclk is not None and sclk != prev_sclk:
                self.edges.append((self.n, sclk, mosi))
                if cs == 1:
                    self.idle_bad.append(f"SCLK edge with CS_N high at clock {self.n}")
                leading = sclk != self.cpol
                if leading == bool(self.cpha):
                    drive = self.queue.pop(0) if self.queue else 0
                else:
                    self.out_bit = None                    # the master sampled it
            prev_cs, prev_sclk = cs, sclk
            if drive is not None:
                self.out_bit = drive
                await Timer(1, "ns")          # leave the read-only phase
                self.miso.value = drive
