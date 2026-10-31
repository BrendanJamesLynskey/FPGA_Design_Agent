"""cocotb tests of acl_regs (SPI mode-0 burst master) against a model of the ADXL362.

The model follows the ADXL362 data sheet (Rev. G): commands 0x0A write register, 0x0B read
register (then an address byte; the address auto-increments), ID registers 0x00-0x03 =
AD 1D F2 01, data 0x0E-0x13 (X, Y, Z, low byte first, 12-bit sign-extended), POWER_CTL 0x2D.
It samples on every clock: MOSI on SCLK rising edges, drives MISO after falling edges
(and the first bit as chip select falls), and checks SCLK is low when chip select falls (mode 0).
"""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from shell.tests.window_bfm import WindowBfm

CTRL, STATUS, TX0, TX1, RX0, RX1, INFO = range(7)


def adxl362_regs() -> dict[int, int]:
    r = {0x00: 0xAD, 0x01: 0x1D, 0x02: 0xF2, 0x03: 0x01, 0x2D: 0x00}
    for a, v in zip(range(0x0E, 0x14), (0x12, 0x00, 0xF0, 0xFF, 0xE8, 0x03)):   # X 18, Y -16, Z 1000 mg
        r[a] = v
    return r


class Adxl362Model:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.regs = adxl362_regs()
        self.transfers: list[list[int]] = []
        self.mode_errors = 0
        self.sclk_rises: list[int] = []
        dut.miso.value = 0

    async def run(self) -> None:
        d = self.dut
        prev_cs, prev_sclk, n = 1, 0, 0
        bits, byte, rx, out, addr, cmd = 0, 0, [], 0, 0, 0
        last_rise = None
        while True:
            await RisingEdge(d.clk)
            n += 1
            cs, sclk, mosi = int(d.cs_n.value), int(d.sclk.value), int(d.mosi.value)
            if prev_cs and not cs:                         # chip select falls
                if sclk:
                    self.mode_errors += 1
                bits, byte, rx, out = 0, 0, [], 0
                d.miso.value = 0
            elif not prev_cs and cs:                       # chip select rises: transfer over
                self.transfers.append(rx)
                d.miso.value = 0
            elif not cs and not prev_sclk and sclk:        # rising: sample MOSI
                if last_rise is not None:
                    self.sclk_rises.append(n - last_rise)
                last_rise = n
                byte = (byte << 1) | mosi
                bits += 1
                if bits == 8:
                    rx.append(byte)
                    if len(rx) == 1:
                        cmd = byte
                    elif len(rx) == 2:
                        addr = byte
                    elif cmd == 0x0A:
                        self.regs[addr] = byte
                        addr = (addr + 1) & 0x3F
                    bits, byte = 0, 0
            elif not cs and prev_sclk and not sclk:        # falling: next MISO bit
                if bits == 0 and len(rx) >= 2 and cmd == 0x0B:
                    out = self.regs.get(addr, 0)
                    addr = (addr + 1) & 0x3F
                d.miso.value = (out >> (7 - bits)) & 1 if (len(rx) >= 2 and cmd == 0x0B) else 0
            prev_cs, prev_sclk = cs, sclk


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.win = WindowBfm(dut, dut.clk)
        self.model = Adxl362Model(dut)

    async def start(self) -> None:
        cocotb.start_soon(Clock(self.dut.clk, 10, "ns").start())
        self.dut.rst.value = 1
        await ClockCycles(self.dut.clk, 4)
        self.dut.rst.value = 0
        cocotb.start_soon(self.model.run())
        await ClockCycles(self.dut.clk, 4)

    async def transfer(self, tx: bytes) -> bytes:
        padded = tx.ljust(8, b"\0")
        await self.win.write(TX0, int.from_bytes(padded[:4], "little"))
        await self.win.write(TX1, int.from_bytes(padded[4:], "little"))
        await self.win.write(CTRL, (len(tx) << 8) | 1)
        await self.win.wait_done(STATUS)
        rx = (await self.win.read(RX0)) | (await self.win.read(RX1)) << 32
        return rx.to_bytes(8, "little")[:len(tx)]


@cocotb.test()
async def test_ids_measure_sample_standby(dut) -> None:
    e = Env(dut)
    await e.start()
    assert (await e.transfer(bytes([0x0B, 0x00, 0, 0, 0, 0])))[2:] == bytes([0xAD, 0x1D, 0xF2, 0x01])
    await e.transfer(bytes([0x0A, 0x2D, 0x02]))
    assert e.model.regs[0x2D] == 0x02, "POWER_CTL not written"
    s = await e.transfer(bytes([0x0B, 0x0E] + [0] * 6))
    xyz = [int.from_bytes(s[2 + 2 * i: 4 + 2 * i], "little", signed=True) for i in range(3)]
    assert xyz == [18, -16, 1000], xyz
    await e.transfer(bytes([0x0A, 0x2D, 0x00]))
    assert e.model.regs[0x2D] == 0x00
    assert e.model.mode_errors == 0, "SCLK was high when chip select fell"
    assert e.model.transfers[0] == [0x0B, 0x00, 0, 0, 0, 0]
    assert set(e.model.sclk_rises[1:8]) == {2 * int(dut.HALF.value)}


@cocotb.test()
async def test_lengths_one_to_eight(dut) -> None:
    e = Env(dut)
    await e.start()
    for n in range(1, 9):
        tx = bytes([0x0B, 0x00] + list(range(0x10, 0x10 + 6)))[:n]
        rx = await e.transfer(tx)
        assert e.model.transfers[-1] == list(tx), (n, e.model.transfers[-1])
        want = bytes([0, 0, 0xAD, 0x1D, 0xF2, 0x01, 0, 0])[:n]
        assert rx == want, (n, rx.hex(), want.hex())
    assert await e.win.read(INFO) == int(dut.HALF.value)
