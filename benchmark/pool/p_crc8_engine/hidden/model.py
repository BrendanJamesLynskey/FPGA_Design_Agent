"""Golden model of p_crc8_engine, written from spec.yaml alone."""

from __future__ import annotations

DATA, CRC, COUNT, STATUS, CTRL = 0, 1, 2, 3, 4
DESIGN_ID = 0x43523845
POLY, INIT, XOROUT = 0x1D, 0xFF, 0xFF


def crc8(data: bytes) -> int:
    """Post-XOR CRC-8 (poly 0x1D, init 0xFF, MSB first, xorout 0xFF)."""
    r = INIT
    for byte in data:
        r ^= byte
        for _ in range(8):
            r = ((r << 1) ^ POLY) & 0xFF if r & 0x80 else (r << 1) & 0xFF
    return r ^ XOROUT


class Model:
    def __init__(self) -> None:
        self.data = b""
        self.last = 0
        self.pending: int | None = None
        self.count = 0
        self.dropped = 0

    @property
    def busy(self) -> bool:
        return self.pending is not None

    def finish(self) -> None:
        """The byte time has elapsed."""
        if self.pending is not None:
            self.data += bytes([self.pending])
            self.count = (self.count + 1) & 0xFFFF
            self.pending = None

    def read(self, off: int) -> int:
        if off == DATA:
            return self.last
        if off == CRC:
            return crc8(self.data)
        if off == COUNT:
            return self.count
        if off == STATUS:
            return int(self.busy) | self.dropped << 8
        return 0

    def write(self, off: int, v: int) -> None:
        if off == DATA:
            if self.busy:
                self.dropped = min(255, self.dropped + 1)
            else:
                self.pending, self.last = v & 0xFF, v & 0xFF
        elif off == CTRL and not self.busy:
            if v & 1:
                self.data, self.count, self.last = b"", 0, 0
            if v & 2:
                self.dropped = 0

    def leds(self) -> int:
        return crc8(self.data) | int(self.busy) << 15
