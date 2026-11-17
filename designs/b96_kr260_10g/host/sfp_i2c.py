"""Bit-banged I2C master for the SFP+ module's EEPROM (brief 96 stage 3), over the design's I2C register (0x080: bit 0 pulls SCL low,
bit 1 pulls SDA low, open drain; reading returns the pin levels in bits 8 and 9), and a Python slave model so the protocol is tested
without hardware. SFF-8472 map as used here: identity at address 0x50 (A0h; vendor name bytes 20-35, part number 40-55, wavelength
60-61), diagnostics at 0x51 (A2h; bytes 96-105: temperature, Vcc, TX bias, TX power, RX power, each a 16-bit big-endian word).
NOT YET RUN ON A BOARD."""

from __future__ import annotations

from typing import Callable


class I2CError(Exception):
    pass


class I2CMaster:
    """`drive(scl_high, sda_high)` sets the two open-drain lines (a 1 releases the line); `sda()` reads the SDA pin level."""

    def __init__(self, drive: Callable[[int, int], None], sda: Callable[[], int]) -> None:
        self.drive, self.sda = drive, sda

    def start(self) -> None:
        self.drive(1, 1); self.drive(1, 0); self.drive(0, 0)

    def stop(self) -> None:
        self.drive(0, 0); self.drive(1, 0); self.drive(1, 1)

    def write_bit(self, b: int) -> None:
        self.drive(0, b); self.drive(1, b); self.drive(0, b)

    def read_bit(self) -> int:
        self.drive(0, 1); self.drive(1, 1)
        v = self.sda()
        self.drive(0, 1)
        return v

    def write_byte(self, v: int) -> bool:
        """Returns True if the slave acknowledged."""
        for i in range(7, -1, -1):
            self.write_bit((v >> i) & 1)
        return self.read_bit() == 0

    def read_byte(self, ack: bool) -> int:
        v = 0
        for _ in range(8):
            v = (v << 1) | self.read_bit()
        self.write_bit(0 if ack else 1)
        return v

    def read(self, dev7: int, addr: int, n: int) -> bytes:
        """Random read of n bytes from `addr` of the device at 7-bit address dev7."""
        self.start()
        if not self.write_byte((dev7 << 1) | 0):
            self.stop(); raise I2CError(f"no acknowledge from {dev7:#x}")
        if not self.write_byte(addr):
            self.stop(); raise I2CError("no acknowledge for the memory address")
        self.start()
        if not self.write_byte((dev7 << 1) | 1):
            self.stop(); raise I2CError(f"no acknowledge from {dev7:#x} on the read")
        out = bytes(self.read_byte(ack=(i < n - 1)) for i in range(n))
        self.stop()
        return out


def ddm(raw: bytes) -> dict:
    """Decode the SFF-8472 diagnostics bytes 96..105 (internally calibrated modules): units from the standard's convention:
    temperature signed 1/256 C, Vcc unsigned 100 uV, bias unsigned 2 uA, TX and RX power unsigned 0.1 uW."""
    import math
    w = [int.from_bytes(raw[2 * i:2 * i + 2], "big") for i in range(5)]
    t = w[0] - 65536 if w[0] >= 32768 else w[0]

    def dbm(p_01uw: int) -> float | None:
        return None if p_01uw == 0 else 10 * math.log10(p_01uw * 1e-4)     # 0.1 uW units -> mW
    return {"temp_c": t / 256.0, "vcc_v": w[1] * 1e-4, "tx_bias_ma": w[2] * 2e-3, "tx_power_dbm": dbm(w[3]), "rx_power_dbm": dbm(w[4]),
            "tx_power_uw": w[3] * 0.1, "rx_power_uw": w[4] * 0.1, "note": "valid for internally calibrated modules only; check A0h byte 92 bit 5"}


class EepromSlave:
    """A model of the module: two 256-byte pages at 0x50 and 0x51, watching the two lines the master drives."""

    def __init__(self, a0: bytes, a2: bytes) -> None:
        self.mem = {0x50: bytearray(a0), 0x51: bytearray(a2)}
        self.scl = 1; self.sda_m = 1; self.sda_s = 1
        self.state = "idle"; self.bits = 0; self.nb = 0; self.dev = None; self.ptr = 0; self.rw = 0; self.first = True; self.out = 0; self.ackn = False

    def line_sda(self) -> int:
        return self.sda_m & self.sda_s

    def drive(self, scl: int, sda: int) -> None:
        old_scl, old_sda = self.scl, self.line_sda()
        self.sda_m = sda
        self.scl = scl
        new_sda = self.line_sda()
        if old_scl and scl and old_sda and not new_sda:                 # start
            self.state, self.bits, self.nb, self.first, self.sda_s = "addr", 0, 0, True, 1
        elif old_scl and scl and not old_sda and new_sda:               # stop
            self.state, self.sda_s = "idle", 1
        elif not old_scl and scl:                                        # SCL rising: sample
            self._rise(new_sda)
        elif old_scl and not scl:                                        # SCL falling: update what the slave drives
            self._fall()

    def _rise(self, sda: int) -> None:
        if self.state in ("addr", "mem", "wr"):
            if self.nb < 8:
                self.bits = (self.bits << 1) | sda; self.nb += 1
        elif self.state == "ackm":
            self.ackn = bool(sda)                                        # master's ack for a byte it read: 0 = ack (continue)

    def _fall(self) -> None:
        if self.state in ("addr", "mem", "wr") and self.nb == 8:
            v = self.bits
            self.nb, self.bits = 9, 0
            if self.state == "addr":
                if (v >> 1) in self.mem:
                    self.dev, self.rw = v >> 1, v & 1; self.sda_s = 0; self.next = "rd" if self.rw else "mem"
                else:
                    self.state = "idle"; self.sda_s = 1; return
            elif self.state == "mem":
                self.ptr = v; self.sda_s = 0; self.next = "addr_again"
            self.state_after = self.state
            self.state = "ack"
        elif self.state == "ack":                                         # the ack bit's clock has ended: release, move on
            self.sda_s = 1; self.nb = 0; self.bits = 0
            if self.next == "rd":
                self.state = "rd"; self.nb = 0; self._load()
            elif self.next == "mem":
                self.state = "mem"
            else:
                self.state = "addr"
        elif self.state == "rd":
            self.nb += 1
            if self.nb < 8:
                self.sda_s = (self.out >> (7 - self.nb)) & 1
            else:
                self.sda_s = 1; self.state = "ackm"
        elif self.state == "ackm":
            self.ptr = (self.ptr + 1) & 0xFF
            if self.ackn:
                self.state = "idle"
            else:
                self.state = "rd"; self.nb = 0; self._load()

    def _load(self) -> None:
        self.out = self.mem[self.dev][self.ptr]
        self.sda_s = (self.out >> 7) & 1
