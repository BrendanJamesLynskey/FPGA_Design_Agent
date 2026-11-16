"""Shared pieces of the network-endpoint tasks' hidden benches (benchmark v2, domain E, brief 82).

Plain helpers and nothing about what a design must do (that is each task's own ``model.py``): the register-window environment
of a task (the shell's board, a model, compare helpers), several copies of one design in a wrapper testbench, a seeded random
generator, and the byte-level pieces of a UDP command packet (the Ethernet CRC-32 and the packet layout of the endpoint's
protocol, ``showcase/udp_endpoint/protocol.md``).
"""

from __future__ import annotations

import random
import zlib

import cocotb
from benchmark.lib.bench import Board, peek


def seeded_rng() -> random.Random:
    """The random generator of a test: seeded from cocotb's seed, so a failing run can be repeated."""
    return random.Random(int(cocotb.RANDOM_SEED))


def crc_le(data: bytes) -> bytes:
    """The Ethernet CRC-32 of ``data`` as the four bytes that follow it on the wire (low byte first)."""
    return zlib.crc32(data).to_bytes(4, "little")


def command(typ: int, seq: int, payload: bytes = b"") -> bytes:
    """A command packet: type, payload length, sequence (big-endian), payload, CRC-32."""
    body = bytes([typ, len(payload), seq >> 8 & 0xFF, seq & 0xFF]) + payload
    return body + crc_le(body)


def response(typ: int, status: int, seq: int, payload: bytes = b"") -> bytes:
    """A reply: type with the top bit set, status, sequence, payload length, payload, CRC-32."""
    body = bytes([typ | 0x80, status, seq >> 8 & 0xFF, seq & 0xFF, len(payload)]) + payload
    return body + crc_le(body)


class Inst:
    """One of several copies of a design in a wrapper testbench, each with its own parameters: the bench's ``Board`` and
    helpers see it as a plain design. A port ``X`` is the wrapper's signal ``X_<suffix>`` (the clock is shared); a parameter
    listed in ``params`` reads as that value."""

    class _Const:
        def __init__(self, v: int) -> None:
            self.value = v

    def __init__(self, dut, suffix: str, **params: int) -> None:
        self._dut, self._sfx, self._params = dut, suffix, params

    def __getattr__(self, name: str):
        if name in self._params:
            return Inst._Const(self._params[name])
        if name == "CLK100MHZ":
            return self._dut.CLK100MHZ
        return getattr(self._dut, f"{name}_{self._sfx}")


class RegEnv:
    """A task's board, its golden model and the register helpers every bench uses. ``self.m`` is the model: its ``read(offset)`` is
    what a register must hold and its ``write`` follows the host."""

    def __init__(self, dut, model, inputs: dict | None = None) -> None:
        self.dut, self.m = dut, model
        self.b = Board(dut, inputs or {})

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def regs(self, offsets, what: str = "") -> None:
        for r in offsets:
            await self.b.expect(r, self.m.read(r), f"{what} reg 0x{r:02X}")

    async def led(self, want: int, what: str = "") -> None:
        got = await peek(self.b.clk, self.dut.LED)
        assert got == want, f"LED {got:04X}, model {want:04X} {what}"

    async def unmapped(self, offsets=(0x40, 0x7F)) -> None:
        for off in offsets:
            await self.b.expect(off, 0, f"unmapped offset 0x{off:02X}")

    async def poke_read_only(self, offsets, value: int = 0x5A5A) -> None:
        """Writes to read-only registers must change nothing (the caller then compares every register with the model)."""
        for off in offsets:
            await self.b.write(off, value)

    async def poke_unmapped(self, offsets=(0x09, 0x20, 0x40, 0x7F), value: int = 0x5A5A5A5A) -> None:
        """Writes to offsets that hold no register must change nothing (the caller then compares every register with the model)."""
        for off in offsets:
            await self.b.write(off, value)
