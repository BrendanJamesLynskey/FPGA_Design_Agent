"""S25FL-S flash model on the QSPI pins for t2_qspi_sfdp's bench (hidden).

Single-bit SPI mode 0 (S25FL128S / S25FL127S data sheets): SI (DQ0) sampled on SCK rising edges, SO (DQ1) changed
after falling edges, bytes MSB first. Opcodes served: RDID 9Fh (ID-CFI bytes from ``ident``) and RSFDP 5Ah (3
address bytes, 8 dummy cycles, then bytes of ``sfdp`` from the address, wrapping at its length). Any other opcode is
recorded in ``bad_opcodes`` (the test fails on it): the design must never write, erase, program or reset the
configuration flash. SCK is the bench wrapper's ``sck`` (CCLK through the STARTUPE2 stub).

It also records each transaction's MOSI bytes, SCK half-period lengths while selected, SCK cycles with CS high, and
whether WP# / HOLD# ever left 0 / 1."""

from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge

# a JESD216 header: "SFDP", minor 6, major 1, 1 parameter header (NPH = 0), access protocol FF; parameter header 0:
# ID 00, minor 6, major 1, length 16 dwords, table pointer 0x000080, ID MSB FF
SFDP_TABLE = bytes([0x53, 0x46, 0x44, 0x50, 0x06, 0x01, 0x00, 0xFF,
                    0x00, 0x06, 0x01, 0x10, 0x80, 0x00, 0x00, 0xFF]) + bytes(range(0x10, 0x40))
IDENT = bytes([0x01, 0x20, 0x18, 0x4D, 0x01, 0x80, 0x30, 0x30])
ALLOWED = (0x9F, 0x5A)


class Flash:
    def __init__(self, dut, ident: bytes = IDENT, sfdp: bytes = SFDP_TABLE) -> None:
        self.dut, self.ident, self.sfdp = dut, ident, sfdp
        self.transactions: list[list[int]] = []
        self.bad_opcodes: list[int] = []
        self.halves: list[int] = []
        self.idle_cycles = 0
        self.wp_hold_bad = False
        self.cs_edges_before_first = None
        dut.QSPI_DQ1.value = 0
        cocotb.start_soon(self._run())

    async def _run(self) -> None:
        d = self.dut
        prev_cs, prev_sck, n, last = 1, 0, 0, 0
        bits, byte, rx, out, op, addr, nout = 0, 0, [], 0, None, 0, 0
        while True:
            await RisingEdge(d.CLK100MHZ)
            n += 1
            cs, sck, si = int(d.QSPI_CSN.value), int(d.sck.value), int(d.QSPI_DQ0.value)
            if int(d.QSPI_DQ2.value) != 0 or int(d.QSPI_DQ3.value) != 1:
                self.wp_hold_bad = True
            if prev_cs and not cs:
                bits, byte, rx, op, nout = 0, 0, [], None, 0
                d.QSPI_DQ1.value = 0
                last = n
            elif not prev_cs and cs:
                self.transactions.append(rx)
            elif cs and sck and not prev_sck:
                self.idle_cycles += 1
            elif not cs and sck != prev_sck:
                self.halves.append(n - last)
                last = n
                if sck:                                         # rising: sample SI
                    byte = (byte << 1) | si
                    bits += 1
                    if bits == 8:
                        rx.append(byte)
                        if len(rx) == 1:
                            op = byte
                            if op not in ALLOWED:
                                self.bad_opcodes.append(op)
                        elif op == 0x5A and 2 <= len(rx) <= 4:
                            addr = (addr << 8 | byte) if len(rx) > 2 else byte
                        bits, byte = 0, 0
                else:                                           # falling: next SO bit
                    sending = (op == 0x9F and len(rx) >= 1) or (op == 0x5A and len(rx) >= 5)
                    if sending and bits == 0:
                        if op == 0x9F:
                            out = self.ident[nout % len(self.ident)]
                        else:
                            out = self.sfdp[(addr + nout) % len(self.sfdp)]
                        nout += 1
                    d.QSPI_DQ1.value = (out >> (7 - bits)) & 1 if sending else 0
            prev_cs, prev_sck = cs, sck
