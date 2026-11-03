"""SPI slave models (mode 0) for the contamination-probe benches (cocotb).

The model samples SCLK, CS_N and MOSI on every clock edge of ``clk``, shifts MOSI in on SCLK rising edges and changes
MISO on SCLK falling edges (and when CS_N falls, for the first bit), as a mode-0 device does. ``transactions`` lists the
bytes of each chip-select frame; ``bit_counts`` the number of SCLK rising edges in it; ``mode_errors`` counts frames
that began with SCLK high or whose SCLK moved while CS_N was high.
"""

from __future__ import annotations

from cocotb.triggers import RisingEdge


class SpiSlave:
    def __init__(self, dut, clk, sclk, cs_n, mosi, miso) -> None:
        self.dut, self.clk = dut, clk
        self.sclk, self.cs_n, self.mosi, self.miso = sclk, cs_n, mosi, miso
        self.transactions: list[list[int]] = []
        self.bit_counts: list[int] = []
        self.mode_errors = 0
        self.sclk_periods: list[int] = []
        self.cs_to_first_rise: list[int] = []
        self.cs_fall_clocks: list[int] = []        # clock number of each chip-select fall
        self.rise_to_cs_high: list[int] = []
        self.miso.value = 0

    # hooks: overridden by devices
    def begin(self) -> None:
        pass

    def end(self, rx: list[int]) -> None:
        pass

    def byte_received(self, rx: list[int]) -> None:
        """A whole byte has been shifted in (rx includes it)."""

    def next_out_byte(self, rx: list[int]) -> int:
        """The byte to shift out next, given the bytes received so far."""
        return 0

    async def run(self) -> None:
        prev_cs, prev_sclk, n = 1, 0, 0
        bits, byte, rx, out, nout = 0, 0, [], 0, 0
        t, t_cs, t_rise, t_fall = 0, 0, 0, 0
        first_rise = True
        while True:
            await RisingEdge(self.clk)
            t += 1
            try:
                cs, sclk, mosi = int(self.cs_n.value), int(self.sclk.value), int(self.mosi.value)
            except ValueError:
                continue
            if prev_cs and not cs:                                 # CS falls: a frame begins
                if sclk:
                    self.mode_errors += 1
                bits, byte, rx, nout = 0, 0, [], 0
                first_rise = True
                t_cs = t
                self.cs_fall_clocks.append(t)
                self.begin()
                out = self.next_out_byte(rx)
                self.miso.value = (out >> 7) & 1
            elif not prev_cs and cs:                               # CS rises: frame over
                self.transactions.append(rx)
                self.bit_counts.append(n_bits_total(rx, bits))
                self.rise_to_cs_high.append(t - t_fall)
                self.miso.value = 0
                self.end(rx)
            elif not cs and not prev_sclk and sclk:                # rising edge: sample MOSI
                if first_rise:
                    self.cs_to_first_rise.append(t - t_cs)
                    first_rise = False
                else:
                    self.sclk_periods.append(t - t_rise)
                t_rise = t
                byte = (byte << 1) | mosi
                bits += 1
                if bits == 8:
                    rx.append(byte)
                    self.byte_received(rx)
                    bits, byte = 0, 0
                    out = self.next_out_byte(rx)
                    nout = 0
                else:
                    nout = bits
            elif not cs and prev_sclk and not sclk:                # falling edge: next MISO bit
                t_fall = t
                self.miso.value = (out >> (7 - nout)) & 1 if nout < 8 else 0
            elif cs and (sclk != prev_sclk):
                self.mode_errors += 1
            prev_cs, prev_sclk = cs, sclk


def n_bits_total(rx: list[int], partial: int) -> int:
    return 8 * len(rx) + partial


class Adxl362(SpiSlave):
    """ADXL362 register file as wired on the Nexys A7. Commands 0x0A (write) and 0x0B (read), address auto-increment.

    ID registers 0x00-0x03 are AD 1D F2 01. XDATA/YDATA/ZDATA (0x08-0x0A) hold the 8-bit values and XDATA_L/H.. (0x0E-0x13)
    the 12-bit ones; both read 0 until POWER_CTL (0x2D) has measurement mode (bits [1:0] = 10) set."""

    def __init__(self, dut, x: int = 18, y: int = -16, z: int = 250) -> None:
        super().__init__(dut, dut.CLK100MHZ, dut.ACL_SCLK, dut.ACL_CSN, dut.ACL_MOSI, dut.ACL_MISO)
        self.regs: dict[int, int] = {0x00: 0xAD, 0x01: 0x1D, 0x02: 0xF2, 0x03: 0x01, 0x2C: 0x13, 0x2D: 0x00}
        self.writes: list[tuple[int, int]] = []        # (register, value) of every register write, in order
        self.set_xyz(x, y, z)
        self.cmd = 0
        self.addr = 0

    def set_xyz(self, x: int, y: int, z: int) -> None:
        """8-bit values (signed); the 12-bit registers hold them shifted up four bits."""
        self.xyz = [x & 0xFF, y & 0xFF, z & 0xFF]

    @property
    def measuring(self) -> bool:
        return (self.regs[0x2D] & 3) == 2

    def read_reg(self, a: int) -> int:
        if a in (0x08, 0x09, 0x0A):
            return self.xyz[a - 8] if self.measuring else 0
        if 0x0E <= a <= 0x13:
            i, hi = divmod(a - 0x0E, 2)
            v = (self.xyz[i] << 4) if self.measuring else 0
            sign = 0xF0 if self.xyz[i] & 0x80 and self.measuring else 0
            return (v & 0xFF) if not hi else (((v >> 8) & 0x0F) | sign)
        return self.regs.get(a, 0)

    def byte_received(self, rx: list[int]) -> None:
        if len(rx) == 1:
            self.cmd = rx[0]
        elif len(rx) == 2:
            self.addr = rx[1]
        elif self.cmd == 0x0A:
            self.regs[self.addr] = rx[-1]
            self.writes.append((self.addr, rx[-1]))
            self.addr = (self.addr + 1) & 0x7F

    def next_out_byte(self, rx: list[int]) -> int:
        if len(rx) >= 2 and self.cmd == 0x0B:
            v = self.read_reg(self.addr)
            self.addr = (self.addr + 1) & 0x7F
            return v
        return 0


class SpiAdc12(SpiSlave):
    """A 12-bit SPI ADC: 16 SCLK per frame, MISO = 0 0 0 0 D11 .. D0 (MSB first), changing on SCLK falling edges.

    ``value`` is the conversion result returned by the next frame; ``corrupt_next`` makes the next frame's four leading bits 1."""

    def __init__(self, dut, clk, sclk, cs_n, mosi_dummy, miso) -> None:
        super().__init__(dut, clk, sclk, cs_n, mosi_dummy, miso)
        self.value = 0
        self.corrupt_next = False
        self.frames_served = 0
        self._word = 0

    def begin(self) -> None:
        lead = 0xF if self.corrupt_next else 0
        self.corrupt_next = False
        self._word = (lead << 12) | (self.value & 0xFFF)
        self.frames_served += 1

    def next_out_byte(self, rx: list[int]) -> int:
        if len(rx) == 0:
            return (self._word >> 8) & 0xFF
        if len(rx) == 1:
            return self._word & 0xFF
        return 0
