"""Golden model of p_adler32, written from spec.yaml alone."""

from __future__ import annotations

BYTE, WORD, ADLER, COUNT, CTRL = range(5)
DESIGN_ID = 0x41444C52
MOD = 65521


def adler32(data: bytes) -> int:
    a, b = 1, 0
    for x in data:
        a = (a + x) % MOD
        b = (b + a) % MOD
    return b << 16 | a


class Model:
    def __init__(self) -> None:
        self.data = b""
        self.count = 0

    def write(self, off: int, v: int) -> None:
        if off == BYTE:
            self.data += bytes([v & 0xFF])
            self.count = (self.count + 1) & 0xFFFFFFFF
        elif off == WORD:
            self.data += (v & 0xFFFFFFFF).to_bytes(4, "little")
            self.count = (self.count + 4) & 0xFFFFFFFF
        elif off == CTRL and v & 1:
            self.data, self.count = b"", 0

    def read(self, off: int) -> int:
        if off == ADLER:
            return adler32(self.data)
        if off == COUNT:
            return self.count
        return 0

    def leds(self) -> int:
        return adler32(self.data) & 0xFFFF
