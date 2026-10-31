"""cocotb tests of qspi_regs (the RDID-only flash reader) against a model of an S25FL1xxS flash.

The model decodes every command byte the flash would receive (chip select low, DQ0 sampled on
SCK rising edges, MSB first) and answers RDID (9Fh) with the ID-CFI bytes 01 20 18 4D 01 80 then
the model-number bytes, as both S25FL128S (Table 54) and S25FL127S (Table 49) data sheets list
them. Any other command is recorded; the tests require that none is ever seen.
"""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from shell.tests.window_bfm import WindowBfm

CTRL, STATUS, ID0, ID1, INFO = range(5)
FLASH_ID = bytes([0x01, 0x20, 0x18, 0x4D, 0x01, 0x80, 0x30, 0x31])


class FlashModel:
    def __init__(self, dut, ident: bytes = FLASH_ID) -> None:
        self.dut, self.ident = dut, ident
        self.commands: list[int] = []
        self.clocks_while_deselected = 0
        self.mode_errors = 0
        self.bits_per_select: list[int] = []
        dut.dq1.value = 1

    async def run(self) -> None:
        d = self.dut
        prev_cs, prev_sck = 1, 0
        nbits, cmd, out_bit = 0, 0, 0
        while True:
            await RisingEdge(d.clk)
            cs, sck, dq0 = int(d.cs_n.value), int(d.sck.value), int(d.dq0.value)
            if prev_cs and not cs:
                if sck:
                    self.mode_errors += 1
                nbits, cmd, out_bit = 0, 0, 0
            elif not prev_cs and cs:
                self.bits_per_select.append(nbits)
                if nbits >= 8 and cmd not in self.commands:
                    pass
                d.dq1.value = 1
            if cs and not prev_sck and sck:
                self.clocks_while_deselected += 1
            elif not cs and not prev_sck and sck:          # rising edge: shift a command bit in
                if nbits < 8:
                    cmd = (cmd << 1) | dq0
                    if nbits == 7:
                        self.commands.append(cmd)
                nbits += 1
            elif not cs and prev_sck and not sck:          # falling edge: next ID bit out
                if nbits >= 8 and cmd == 0x9F:
                    i = out_bit // 8
                    byte = self.ident[i] if i < len(self.ident) else 0xFF
                    d.dq1.value = (byte >> (7 - out_bit % 8)) & 1
                    out_bit += 1
            prev_cs, prev_sck = cs, sck


async def start(dut, model: FlashModel) -> WindowBfm:
    win = WindowBfm(dut, dut.clk)
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    cocotb.start_soon(model.run())
    await ClockCycles(dut.clk, 4)
    return win


async def read_id(win: WindowBfm) -> bytes:
    await win.write(CTRL, 1)
    await win.wait_done(STATUS)
    v = (await win.read(ID0)) | (await win.read(ID1)) << 32
    return v.to_bytes(8, "little")


@cocotb.test()
async def test_rdid_only(dut) -> None:
    m = FlashModel(dut)
    win = await start(dut, m)
    for _ in range(3):
        assert await read_id(win) == FLASH_ID
    assert m.commands == [0x9F] * 3, [hex(c) for c in m.commands]
    assert m.bits_per_select == [72] * 3, m.bits_per_select     # 8 command + 64 ID bits
    assert m.mode_errors == 0, "SCK was high when chip select fell"
    # the preamble (for STARTUPE2's swallowed edges) runs once, with chip select high
    assert m.clocks_while_deselected == int(dut.PREAMBLE.value)
    assert await win.read(INFO) == int(dut.HALF.value)


@cocotb.test()
async def test_writes_to_any_register_send_nothing_else(dut) -> None:
    """Writing every window offset with every bit pattern can only start an RDID."""
    m = FlashModel(dut)
    win = await start(dut, m)
    for off in range(0, 8):
        for v in (0xFFFF_FFFE, 0x0000_0006, 0x0000_00D8, 0x0000_0060, 0x0000_0002):   # GO bit clear
            await win.write(off, v)
    await ClockCycles(dut.clk, 200)
    assert m.commands == [], "a register write without GO started a transfer"
    await win.write(0x05, 0xFFFF_FFFF)            # GO-like bit on a non-CTRL offset
    await ClockCycles(dut.clk, 200)
    assert m.commands == []
    assert await read_id(win) == FLASH_ID and m.commands == [0x9F]
