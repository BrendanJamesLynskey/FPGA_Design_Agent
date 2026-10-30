"""cocotb UART bus functional model: drive the shell's RX line, decode its TX line.

Timing is in clock cycles of the DUT clock, so the same code runs at the real
115200 baud (868 clocks a bit) and at the fast test baud. ``send_byte`` can be
told to send slower or faster than the DUT expects (baud mismatch) and with a
bad stop bit.
"""

from __future__ import annotations

import cocotb
from cocotb.handle import SimHandleBase
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, with_timeout

from shell.host import protocol as p


class UartBfm:
    def __init__(self, clk: SimHandleBase, rx: SimHandleBase, tx: SimHandleBase, clks_per_bit: int) -> None:
        self.clk, self.rx, self.tx, self.cpb = clk, rx, tx, clks_per_bit
        self.rx.value = 1

    async def send_byte(self, b: int, bit_clks: int | None = None, stop: int = 1) -> None:
        n = bit_clks or self.cpb
        for level in [0] + [(b >> i) & 1 for i in range(8)] + [stop]:
            self.rx.value = level
            await ClockCycles(self.clk, n)
        self.rx.value = 1
        if stop == 0:
            await ClockCycles(self.clk, n)   # let the line idle so the receiver recovers

    async def send(self, data: bytes, bit_clks: int | None = None) -> None:
        for b in data:
            await self.send_byte(b, bit_clks)

    async def recv_byte(self, timeout_clks: int, measure: list[int] | None = None) -> int:
        """Wait for a start bit, sample at bit middles, check the stop bit.

        If ``measure`` is given, the clock count between every line transition
        of the byte is appended to it (for the bit-timing test).
        """
        await with_timeout(FallingEdge(self.tx), timeout_clks * 10, "ns")   # 10 ns clock
        if measure is not None:
            await self._measure_edges(measure)
            return self._last
        await ClockCycles(self.clk, self.cpb // 2)
        assert self.tx.value == 0, "start bit not low at its middle"
        v = 0
        for i in range(8):
            await ClockCycles(self.clk, self.cpb)
            v |= int(self.tx.value) << i
        await ClockCycles(self.clk, self.cpb)
        assert self.tx.value == 1, "stop bit not high"
        return v

    async def _measure_edges(self, out: list[int]) -> None:
        # Sample the line every clock for 10 bit times and record run lengths.
        samples = []
        for _ in range(10 * self.cpb):
            await RisingEdge(self.clk)
            samples.append(int(self.tx.value))
        v = 0
        for i in range(8):
            v |= samples[(i + 1) * self.cpb + self.cpb // 2] << i
        assert samples[self.cpb // 2] == 0 and samples[9 * self.cpb + self.cpb // 2] == 1
        self._last = v
        run = 1
        for a, b in zip(samples, samples[1:]):
            if a == b:
                run += 1
            else:
                out.append(run)
                run = 1

    async def recv(self, n: int, timeout_clks: int) -> bytes:
        return bytes([await self.recv_byte(timeout_clks) for _ in range(n)])

    async def transact(self, req: bytes, timeout_clks: int | None = None) -> bytes:
        """Send a request and collect the 7-byte response (raises on no answer)."""
        t = timeout_clks or 40 * self.cpb
        # Listen before sending: the answer starts half a bit after the last
        # stop bit's middle, before ``send`` returns.
        listener = cocotb.start_soon(self.recv(p.RESP_LEN, t + 10 * self.cpb * len(req)))
        await self.send(req)
        return await listener

    async def expect_silence(self, clks: int) -> None:
        """Assert the TX line stays idle for ``clks`` cycles."""
        for _ in range(clks // 16):
            await ClockCycles(self.clk, 16)
            assert self.tx.value == 1, "shell answered when it should have stayed silent"

