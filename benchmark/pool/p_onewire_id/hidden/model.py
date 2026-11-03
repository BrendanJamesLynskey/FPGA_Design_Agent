"""Golden model of p_onewire_id, written from spec.yaml alone."""

from __future__ import annotations

CTRL, STATUS, ID, CRC, FAILS = range(5)
DESIGN_ID = 0x31574944
COMMAND = 0x33


def crc8_maxim(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc


class Model:
    def __init__(self) -> None:
        self.status = 0
        self.id = 0
        self.crc = 0
        self.fails = 0

    def read_done(self, present: bool, id16: int, crc_wire: int | None = None) -> None:
        """The result of one complete read against a device (crc_wire: the CRC the device sends, default the right one)."""
        if not present:
            self.fails = min(255, self.fails + 1)
            self.status = 0b0010
            return
        good = crc8_maxim(bytes([id16 & 0xFF, id16 >> 8]))
        sent = good if crc_wire is None else crc_wire
        self.id, self.crc = id16, sent
        ok = sent == good
        if not ok:
            self.fails = min(255, self.fails + 1)
        self.status = 0b0110 | int(ok) << 3

    def read(self, off: int) -> int:
        return {STATUS: self.status, ID: self.id, CRC: self.crc, FAILS: self.fails}.get(off, 0)

    def leds(self) -> int:
        return self.id

    @staticmethod
    def wire_bits(id16: int, crc: int) -> list[int]:
        return [(id16 >> i) & 1 for i in range(16)] + [(crc >> i) & 1 for i in range(8)]
