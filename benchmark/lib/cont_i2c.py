"""I2C bus-level slave model and two devices for the contamination-probe benches (cocotb).

The testbench wrapper (a SystemVerilog file in the task's hidden/) joins the design's open-drain pins with two pull
signals ``dev_scl_pull`` / ``dev_sda_pull`` that this model drives (1 = pull the line low) and exposes the resolved
lines as ``scl`` / ``sda``. The model samples both lines on every clock edge of ``clk``, decodes START / STOP / bytes,
and calls the device hooks. It never drives SDA while the master owns the bus.
"""

from __future__ import annotations

from cocotb.triggers import ClockCycles, RisingEdge


def _bit(sig) -> int:
    """A line level; an unresolved (X/Z) level reads as the pulled-up 1."""
    try:
        return int(sig.value)
    except ValueError:
        return 1


class I2cSlave:
    def __init__(self, dut, addr: int, clk=None) -> None:
        self.dut, self.addr = dut, addr
        self.clk = clk if clk is not None else dut.CLK100MHZ
        self.events: list[str] = []           # "S", "P", "A<addr7><r/w>" per address byte seen, in order
        self.acks_given = 0
        self.scl_rise_clocks: list[int] = []
        self.in_txn = False                   # between a START and the next STOP
        self.txn_starts: list[int] = []       # clock numbers of the first START of each transaction
        self.clk_no = 0
        dut.dev_scl_pull.value = 0
        dut.dev_sda_pull.value = 0

    # ----- hooks -----
    def matches(self, addr7: int) -> bool:
        return addr7 == self.addr

    def write_byte(self, n: int, value: int) -> bool:
        """The master wrote data byte ``n`` (0 = first after the address). Return True to ACK."""
        return True

    def read_byte(self) -> int:
        return 0xFF

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    # ----- engine -----
    def _drive(self, bit: int) -> None:
        self.dut.dev_sda_pull.value = 0 if bit else 1

    def _release(self) -> None:
        self.dut.dev_sda_pull.value = 0

    async def run(self) -> None:
        d = self.dut
        prev_scl, prev_sda = 1, 1
        state, nbits, byte, nwr, out, rw, master_ack = "idle", 0, 0, 0, 0, 0, 0
        last_rise = None
        while True:
            await RisingEdge(self.clk)
            self.clk_no += 1
            clk_no = self.clk_no
            scl, sda = _bit(d.scl), _bit(d.sda)
            if prev_scl and scl and prev_sda and not sda:                       # START (or repeated START)
                self.events.append("S")
                if not self.in_txn:
                    self.txn_starts.append(clk_no)
                self.in_txn = True
                state, nbits, byte, nwr = "addr", 0, 0, 0
                self._release()
                self.on_start()
            elif prev_scl and scl and not prev_sda and sda:                     # STOP
                self.events.append("P")
                self.in_txn = False
                state = "idle"
                self._release()
                self.on_stop()
            elif not prev_scl and scl:                                          # SCL rises: sample
                if last_rise is not None:
                    self.scl_rise_clocks.append(clk_no - last_rise)
                last_rise = clk_no
                if state in ("addr", "wdata"):
                    byte = ((byte << 1) | sda) & 0xFF
                    nbits += 1
                elif state == "rdata_ack":
                    master_ack = 1 if sda == 0 else 0
            elif prev_scl and not scl:                                          # SCL falls: drive
                if state in ("addr", "wdata") and nbits == 8:
                    if state == "addr":
                        rw = byte & 1
                        self.events.append(f"A{byte >> 1:02X}{'R' if rw else 'W'}")
                        if self.matches(byte >> 1):
                            self._drive(0)
                            self.acks_given += 1
                            state = "ack_r" if rw else "ack_w"
                        else:
                            state = "idle"
                    else:
                        ok = self.write_byte(nwr, byte)
                        nwr += 1
                        if ok:
                            self._drive(0)
                            self.acks_given += 1
                        state = "ack_w"
                    nbits, byte = 0, 0
                elif state == "ack_w":
                    self._release()
                    state = "wdata"
                elif state == "ack_r":
                    out, nbits, state = self.read_byte(), 1, "rdata"
                    self._drive((out >> 7) & 1)
                elif state == "rdata":
                    if nbits == 8:
                        self._release()
                        state = "rdata_ack"
                    else:
                        self._drive((out >> (7 - nbits)) & 1)
                        nbits += 1
                elif state == "rdata_ack":
                    if master_ack:
                        out, nbits, state = self.read_byte(), 1, "rdata"
                        self._drive((out >> 7) & 1)
                    else:
                        self._release()
                        state = "idle"
            prev_scl, prev_sda = scl, sda


class Adt7420(I2cSlave):
    """ADT7420 as wired on the Nexys A7: address 0x4B, register pointer, auto-increment on reads, ID 0xCB.

    A pointer write closed by STOP (no repeated START) is lost (pointer back to 0)."""

    def __init__(self, dut, temp_raw16: int = 0x0D80) -> None:
        super().__init__(dut, 0x4B)
        self.regs = {0x00: temp_raw16 >> 8, 0x01: temp_raw16 & 0xFF, 0x02: 0, 0x03: 0, 0x0B: 0xCB}
        self.ptr = 0
        self.ptr_fresh = False
        self.data_writes: list[int] = []
        self.ptr_writes: list[int] = []
        self.reads = 0

    def set_temp(self, raw16: int) -> None:
        self.regs[0x00], self.regs[0x01] = (raw16 >> 8) & 0xFF, raw16 & 0xFF

    async def set_temp_when_idle(self, raw16: int) -> None:
        """Change the temperature registers only between transactions, so no read is torn."""
        while self.in_txn:
            await ClockCycles(self.clk, 1)
        self.set_temp(raw16)

    def write_byte(self, n: int, value: int) -> bool:
        if n == 0:
            self.ptr, self.ptr_fresh = value, True
            self.ptr_writes.append(value)
        else:
            self.data_writes.append(value)
        return True

    def read_byte(self) -> int:
        self.ptr_fresh = False
        v = self.regs.get(self.ptr, 0)
        self.ptr = (self.ptr + 1) & 0xFF
        self.reads += 1
        return v

    def on_stop(self) -> None:
        if self.ptr_fresh:
            self.ptr = 0
        self.ptr_fresh = False


class Eeprom24(I2cSlave):
    """24C02-style EEPROM: 256 bytes, 8-byte pages, address 0x50. Random and current-address reads; page writes.

    After the STOP that ends a write, the device NACKs its address for ``write_clocks`` clocks (write cycle)."""

    def __init__(self, dut, addr: int = 0x50, write_clocks: int = 200, contents: dict[int, int] | None = None) -> None:
        super().__init__(dut, addr)
        self.mem = [0xFF] * 256
        for a, v in (contents or {}).items():
            self.mem[a] = v
        self.ptr = 0
        self.write_clocks = write_clocks
        self.busy_until = 0
        self.writes: list[tuple[int, int]] = []     # (address, value) of each byte committed
        self.pending: list[tuple[int, int]] = []
        self.wrote = False
        self.nacked_busy = 0
        self.reads = 0                      # data bytes sent to the master
        self.ignore_writes = False          # a worn-out part: writes are acknowledged but not stored

    def matches(self, addr7: int) -> bool:
        if addr7 != self.addr:
            return False
        if self.dut_clk_count() < self.busy_until:
            self.nacked_busy += 1
            return False
        return True

    def dut_clk_count(self) -> int:
        return self.clk_no

    def write_byte(self, n: int, value: int) -> bool:
        if n == 0:
            self.ptr = value
            self.wrote = False
        else:
            self.pending.append((self.ptr, value))
            self.ptr = (self.ptr & ~7) | ((self.ptr + 1) & 7)       # page wrap
            self.wrote = True
        return True

    def read_byte(self) -> int:
        v = self.mem[self.ptr]
        self.ptr = (self.ptr + 1) & 0xFF
        self.reads += 1
        return v

    def on_stop(self) -> None:
        if self.pending and self.ignore_writes:
            self.pending = []
            self.busy_until = self.dut_clk_count() + self.write_clocks
        elif self.pending:
            for a, v in self.pending:
                self.mem[a] = v
                self.writes.append((a, v))
            self.pending = []
            self.busy_until = self.dut_clk_count() + self.write_clocks
