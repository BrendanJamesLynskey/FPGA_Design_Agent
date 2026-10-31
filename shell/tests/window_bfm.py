"""cocotb driver for the shell's register window (win_addr/win_wr/win_rd/win_wdata/win_rdata).

Tests of a design's register block can drive the window directly, without the UART,
when the shell itself is tested elsewhere (shell/tests/test_shell_rtl.py). Offsets are
window offsets (shell address - 0x80). win_rdata is read one cycle after win_rd, as
PROTOCOL.md requires of a design.
"""

from __future__ import annotations

from cocotb.handle import SimHandleBase
from cocotb.triggers import ReadOnly, RisingEdge


class WindowBfm:
    def __init__(self, dut: SimHandleBase, clk: SimHandleBase) -> None:
        self.dut, self.clk = dut, clk
        dut.win_addr.value = 0
        dut.win_wr.value = 0
        dut.win_rd.value = 0
        dut.win_wdata.value = 0

    async def write(self, off: int, value: int) -> None:
        await RisingEdge(self.clk)
        self.dut.win_addr.value = off
        self.dut.win_wdata.value = value & 0xFFFF_FFFF
        self.dut.win_wr.value = 1
        await RisingEdge(self.clk)
        self.dut.win_wr.value = 0

    async def read(self, off: int) -> int:
        await RisingEdge(self.clk)
        self.dut.win_addr.value = off
        self.dut.win_rd.value = 1
        await RisingEdge(self.clk)
        self.dut.win_rd.value = 0
        await RisingEdge(self.clk)
        await ReadOnly()
        return int(self.dut.win_rdata.value)

    async def wait_done(self, status_off: int, timeout_reads: int = 100_000) -> int:
        """Poll a STATUS register until busy (bit 0) is clear and done (bit 1) is set."""
        for _ in range(timeout_reads):
            s = await self.read(status_off)
            if not (s & 1) and (s & 2):
                return s
        raise AssertionError(f"window offset {status_off:#x}: no done after {timeout_reads} reads")
