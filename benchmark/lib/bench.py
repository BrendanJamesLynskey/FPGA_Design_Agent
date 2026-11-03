"""Shared pieces of the benchmark's hidden acceptance benches (cocotb).

Every benchmark task is a board top for the Nexys A7-100T that embeds the test shell (shell/PROTOCOL.md), so the
benches reach the design's registers through the shell's UART exactly as a host does on the board. Offsets passed
to :meth:`Board.read` / :meth:`Board.write` are window offsets (shell address - 0x80).

Nothing here knows a task's behaviour: the task's own ``model.py`` (written from its hidden ``spec.yaml``) does.
"""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

from shell.host import protocol as p
from shell.tests.uart_bfm import UartBfm


class Board:
    """The DUT's clock, reset and shell. ``inputs`` are set to their idle values before reset is released."""

    def __init__(self, dut, inputs: dict[str, int] | None = None, clk: str = "CLK100MHZ") -> None:
        self.dut = dut
        self.clk = getattr(dut, clk)
        self.cpb = int(dut.CLKS_PER_BIT.value)
        self.inputs = inputs or {}
        self.uart = UartBfm(self.clk, dut.UART_TXD_IN, dut.UART_RXD_OUT, self.cpb)
        self.design_id: int | None = None

    def param(self, name: str) -> int:
        return int(getattr(self.dut, name).value)

    async def start(self) -> None:
        cocotb.start_soon(Clock(self.clk, 10, "ns").start())
        for k, v in self.inputs.items():
            getattr(self.dut, k).value = v
        self.dut.CPU_RESETN.value = 0
        await ClockCycles(self.clk, 8)
        self.dut.CPU_RESETN.value = 1
        await ClockCycles(self.clk, 8)

    async def reset(self) -> None:
        self.dut.CPU_RESETN.value = 0
        await ClockCycles(self.clk, 8)
        self.dut.CPU_RESETN.value = 1
        await ClockCycles(self.clk, 8)

    async def cycles(self, n: int) -> None:
        await ClockCycles(self.clk, n)

    async def access(self, cmd: int, addr: int, data: int = 0) -> p.Response:
        got = await self.uart.transact(p.encode_request(cmd, addr, data))
        return p.decode_response(got)

    async def read(self, off: int) -> int:
        r = await self.access(p.CMD_READ, p.WINDOW_BASE + off)
        assert r.ok, f"read window 0x{off:02X}: status {r.status_name}"
        return r.data

    async def write(self, off: int, value: int) -> None:
        r = await self.access(p.CMD_WRITE, p.WINDOW_BASE + off, value & 0xFFFF_FFFF)
        assert r.ok, f"write window 0x{off:02X}: status {r.status_name}"

    async def shell_id(self) -> int:
        r = await self.access(p.CMD_READ, p.REG_DESIGN_ID)
        assert r.ok
        return r.data

    async def expect(self, off: int, want: int, what: str = "") -> int:
        got = await self.read(off)
        assert got == want, f"{what or 'register'} at window 0x{off:02X}: RTL 0x{got:08X}, model 0x{want:08X}"
        return got


def ascii_id(s: str) -> int:
    """Four ASCII characters, MSB first, as the shell's DESIGN_ID register holds them."""
    assert len(s) == 4
    return int.from_bytes(s.encode(), "big")


async def sample_every(clk, n: int, sig) -> list[int]:
    """``sig`` sampled on each of the next ``n`` rising clock edges (read-only phase)."""
    out = []
    for _ in range(n):
        await RisingEdge(clk)
        await ReadOnly()
        out.append(int(sig.value))
    await FallingEdge(clk)                 # leave the read-only phase so the caller can drive inputs
    return out


SEG_ORDER = "abcdefg"


def seg_pins(dut) -> int:
    """Active-low CA..CG as a 7-bit value, bit 0 = CA."""
    v = 0
    for i, n in enumerate(("CA", "CB", "CC", "CD", "CE", "CF", "CG")):
        v |= int(getattr(dut, n).value) << i
    return v


async def scan_display(dut, clk, slot_clocks: int, n_digits: int = 8, settle: int = 2) -> dict[int, tuple[int, int]]:
    """Watch the multiplexed display for ``n_digits`` slots after the next digit change.

    Returns {digit: (segment pins CA..CG active low, DP)} for every digit seen lit (AN low). A digit whose slot
    passes with every AN high is absent from the result."""
    seen: dict[int, tuple[int, int]] = {}
    total = slot_clocks * (n_digits + 1)
    for _ in range(total):
        await RisingEdge(clk)
        await ReadOnly()
        an = int(dut.AN.value)
        low = [k for k in range(8) if not (an >> k) & 1]
        assert len(low) <= 1, f"more than one digit lit at once: AN=0b{an:08b}"
        if low:
            k = low[0]
            seen[k] = (seg_pins(dut), int(dut.DP.value))
    await FallingEdge(clk)
    return seen


async def peek(clk, sig) -> int:
    """``sig`` at the next rising edge (read-only phase), leaving the caller free to drive inputs after."""
    await RisingEdge(clk)
    await ReadOnly()
    v = int(sig.value)
    await FallingEdge(clk)
    return v
