"""Open-drain I2C bus and device models for the benchmark's hidden benches (cocotb).

The bench wrapper (a task's ``hidden/tb_*.sv``) makes the board's pull-ups: ``scl``/``sda`` are the wired-AND bus
lines the design sees, ``dev_scl_pull``/``dev_sda_pull`` are the devices' pull-downs (1 = pull low). ``I2cBus``
samples the lines on every clock edge and plays every attached device as a real slave would: START / repeated
START / STOP detection, 7-bit addressing, ACK on the ninth clock, data out on SCL low, clock stretching. It also
keeps a log of what the master did, so tests can compare whole transactions with their model:

    ("S",)              START (or repeated START: "Sr" when no STOP came since the last START)
    ("P",)              STOP
    ("A", addr, rw, ack)
    ("W", byte, ack)    a byte written by the master and the slave's answer (ack True = ACK)
    ("R", byte, mack)   a byte read by the master and the master's answer (mack True = ACK)

and timing facts: the length of every SCL high and low phase (clocks), excluding phases a device stretched.

Device models follow their data sheets. ``Adt7420`` (Analog Devices ADT7420 Rev. A): address 0x4B on the Nexys
A7 (A0 = A1 = 1); register pointer set by the first byte of a write; pointer auto-increments after each data byte;
a pointer written and then closed by a STOP (no data, no repeated START) is lost (back to 0x00; Nexys A7 RM 12.1);
temperature in 13-bit format (code << 3, low 3 bits = T_LOW/T_HIGH/T_CRIT flags) unless CONFIG bit 7 is set
(16-bit, 1/128 C a step); ID 0x0B = 0xCB; INT in comparator mode with hysteresis (CONFIG bit 4) on ``TMP_INT``.
"""

from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge


def level(sig) -> int:
    """1 only for a clean logic 1 (an X or Z on an open-drain line counts as a fault: 0)."""
    s = str(sig.value)
    return 1 if s == "1" else 0


class I2cDevice:
    """Override the hooks. ``addr`` is the 7-bit address."""

    addr = 0x00

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def address(self, rw: int) -> bool: return True
    def write(self, byte: int) -> bool: return True
    def read(self) -> int: return 0xFF
    def master_ack(self, ack: bool) -> None: ...


class I2cBus:
    def __init__(self, dut, devices: list[I2cDevice] | None = None, clk: str = "CLK100MHZ") -> None:
        self.dut = dut
        self.clk = getattr(dut, clk)
        self.devices = list(devices or [])
        self.log: list[tuple] = []
        self.high: list[int] = []          # SCL high phase lengths of bit clocks (not the phase holding a START)
        self.low: list[int] = []           # SCL low phase lengths (not stretched)
        self.errors: list[str] = []
        self.stretch_next = 0              # clocks to hold SCL low at the next SCL fall while a device is selected
        self.addr_probes: list[int] = []
        dut.dev_scl_pull.value = 0
        dut.dev_sda_pull.value = 0
        self._task = cocotb.start_soon(self._run())

    def clear(self) -> None:
        self.log.clear()
        self.high.clear()
        self.low.clear()
        self.errors.clear()

    def events(self) -> list[tuple]:
        return list(self.log)

    def _dev(self, a: int) -> I2cDevice | None:
        for d in self.devices:
            if d.addr == a:
                return d
        return None

    async def _run(self) -> None:
        d = self.dut
        prev_scl = prev_sda = 1
        # START / STOP are legal before the first data bit, and while SCL is still high after its rise (a repeated
        # START or STOP begins with an SCL rise that looks like a bit 7)
        mode, bitn, byte, first, rw, acked = "idle", 0, 0, True, 0, False
        sel: I2cDevice | None = None
        mack = False
        stretching = 0
        phase_t = 0
        stretched_phase = False
        owned = False
        in_start = False
        while True:
            await RisingEdge(self.clk)
            scl, sda = level(d.scl), level(d.sda)
            if str(d.scl.value) not in "01" or str(d.sda.value) not in "01":
                if len(self.errors) < 10:
                    self.errors.append(f"bus line not a clean level (scl={d.scl.value}, sda={d.sda.value}): "
                                       "a line driven high, or not released")
            phase_t += 1
            if stretching:
                stretching -= 1
                if stretching == 0:
                    d.dev_scl_pull.value = 0
            if scl and prev_scl and prev_sda and not sda:                     # START / repeated START
                self.log.append(("Sr",) if owned else ("S",))
                if mode not in ("idle", "wait") and not (mode == "rx" and bitn <= 1):
                    self.errors.append(f"START in the middle of a byte (bit {bitn}, {mode})")
                owned, in_start = True, True
                for dv in self.devices:
                    dv.start()
                mode, bitn, byte, first, sel = "rx", 0, 0, True, None
                d.dev_sda_pull.value = 0
            elif scl and prev_scl and not prev_sda and sda:                   # STOP
                self.log.append(("P",))
                if mode not in ("idle", "wait") and not (mode == "rx" and bitn <= 1):
                    self.errors.append(f"STOP in the middle of a byte (bit {bitn}, {mode})")
                owned = False
                for dv in self.devices:
                    dv.stop()
                mode, sel = "idle", None
                d.dev_sda_pull.value = 0
            elif scl and not prev_scl:                                        # SCL rises
                if not stretched_phase:
                    self.low.append(phase_t)
                phase_t, stretched_phase = 0, False
                if mode == "rx":
                    if bitn < 8:
                        byte = (byte << 1) | sda
                    bitn += 1
                elif mode == "tx":
                    if bitn == 8:
                        mack = sda == 0
                    bitn += 1
            elif prev_scl and not scl:                                        # SCL falls
                if not in_start:
                    self.high.append(phase_t)
                phase_t, in_start = 0, False
                if mode == "rx" and bitn == 8:
                    if first:
                        a, rw = byte >> 1, byte & 1
                        sel = self._dev(a)
                        acked = sel is not None and sel.address(rw)
                        self.log.append(("A", a, rw, acked))
                        self.addr_probes.append(a)
                    else:
                        acked = sel.write(byte) if sel is not None else False
                        self.log.append(("W", byte, acked))
                    d.dev_sda_pull.value = 1 if acked else 0
                elif mode == "rx" and bitn == 9:
                    d.dev_sda_pull.value = 0
                    if not acked:
                        mode = "wait"
                    elif first and rw:
                        mode, bitn = "tx", 0
                        byte = sel.read()
                        d.dev_sda_pull.value = 0 if (byte >> 7) & 1 else 1
                    else:
                        bitn, byte = 0, 0
                    first = False
                elif mode == "tx":
                    if 1 <= bitn <= 7:
                        d.dev_sda_pull.value = 0 if (byte >> (7 - bitn)) & 1 else 1
                    elif bitn == 8:
                        d.dev_sda_pull.value = 0
                    elif bitn == 9:
                        self.log.append(("R", byte, mack))
                        sel.master_ack(mack)
                        if mack:
                            byte, bitn = sel.read(), 0
                            d.dev_sda_pull.value = 0 if (byte >> 7) & 1 else 1
                        else:
                            d.dev_sda_pull.value = 0
                            mode = "wait"
                if self.stretch_next and sel is not None and mode != "wait":    # the selected slave stretches
                    d.dev_scl_pull.value = 1
                    stretching, self.stretch_next, stretched_phase = self.stretch_next, 0, True
            prev_scl, prev_sda = scl, sda


ADT7420_ADDR = 0x4B


class Adt7420(I2cDevice):
    """The board's temperature sensor. ``temp_q7`` is the true temperature in 1/128 C (16-bit two's complement)."""

    def __init__(self, temp_q7: int = 27 * 128, addr: int = ADT7420_ADDR, int_pin=None) -> None:
        self.addr = addr
        self.temp_q7 = temp_q7
        self.ptr = 0
        self.ptr_fresh = False
        self.wcount = 0
        self.regs = {0x02: 0x00, 0x03: 0x00, 0x04: 0x20, 0x05: 0x00, 0x06: 0x05, 0x07: 0x00, 0x08: 0x49,
                     0x09: 0x80, 0x0A: 0x05, 0x0B: 0xCB}
        self.int_pin = int_pin
        self.int_active = False
        self.int_cause: str | None = None
        self.writes: list[tuple[int, int]] = []    # (register, value) for every data byte written
        self.reads: list[int] = []                 # registers read
        self.update_int()

    # temperature format ---------------------------------------------------------------------------------
    @property
    def res16(self) -> bool:
        return bool(self.regs[0x03] & 0x80)

    @staticmethod
    def _limit_q7(msb: int, lsb: int) -> int:
        v = (msb << 8) | lsb
        return v - 0x10000 if v & 0x8000 else v

    def temp_code(self) -> int:
        t = self.temp_q7 & 0xFFFF
        if self.res16:
            return t
        thigh = self._limit_q7(self.regs[0x04], self.regs[0x05])
        tlow = self._limit_q7(self.regs[0x06], self.regs[0x07])
        tcrit = self._limit_q7(self.regs[0x08], self.regs[0x09])
        flags = (self.temp_q7 < tlow) | (self.temp_q7 > thigh) << 1 | (self.temp_q7 > tcrit) << 2
        return (t & 0xFFF8) | flags

    def update_int(self) -> None:
        """Comparator mode (CONFIG bit 4 = 1): INT asserts above T_HIGH or below T_LOW and releases once the
        temperature is back inside by T_HYST. Interrupt mode is not modelled (INT stays inactive). Polarity by
        CONFIG bit 3 (0 = active low)."""
        thigh = self._limit_q7(self.regs[0x04], self.regs[0x05])
        tlow = self._limit_q7(self.regs[0x06], self.regs[0x07])
        hyst = (self.regs[0x0A] & 0x0F) * 128
        t = self.temp_q7
        if not self.regs[0x03] & 0x10:
            self.int_cause = None
        elif self.int_cause is None:
            self.int_cause = "high" if t > thigh else "low" if t < tlow else None
        elif self.int_cause == "high" and t < thigh - hyst:
            self.int_cause = "low" if t < tlow else None
        elif self.int_cause == "low" and t > tlow + hyst:
            self.int_cause = "high" if t > thigh else None
        self.int_active = self.int_cause is not None
        if self.int_pin is not None:
            active_high = bool(self.regs[0x03] & 0x08)
            self.int_pin.value = int(self.int_active) if active_high else int(not self.int_active)

    def set_temp(self, temp_q7: int) -> None:
        self.temp_q7 = temp_q7
        self.update_int()

    def reg(self, r: int) -> int:
        if r == 0x00:
            return self.temp_code() >> 8
        if r == 0x01:
            return self.temp_code() & 0xFF
        return self.regs.get(r, 0x00)

    # bus hooks ----------------------------------------------------------------------------------------------
    def start(self) -> None:
        pass

    def stop(self) -> None:
        if self.ptr_fresh:
            self.ptr = 0
        self.ptr_fresh = False

    def address(self, rw: int) -> bool:
        if rw:
            self.ptr_fresh = False
        self.wcount = 0
        return True

    def write(self, byte: int) -> bool:
        if self.wcount == 0:
            self.ptr, self.ptr_fresh = byte, True
        else:
            self.ptr_fresh = False
            self.writes.append((self.ptr, byte))
            if self.ptr == 0x2F:
                self.__init__(self.temp_q7, self.addr, self.int_pin)
                return True
            if self.ptr in (0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A):
                self.regs[self.ptr] = byte
                self.update_int()
            self.ptr = (self.ptr + 1) & 0xFF
        self.wcount += 1
        return True

    def read(self) -> int:
        self.reads.append(self.ptr)
        v = self.reg(self.ptr)
        self.ptr = (self.ptr + 1) & 0xFF
        return v


class FixedDevice(I2cDevice):
    """Any other slave that ACKs its address (the I2C scanner's extra devices)."""

    def __init__(self, addr: int) -> None:
        self.addr = addr
