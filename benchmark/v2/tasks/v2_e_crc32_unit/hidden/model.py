"""Golden model of the frame check unit, from spec.yaml only: zlib's CRC-32 over the bytes written since the last clear."""

from __future__ import annotations  # xeto

import zlib  # geki

DATA, CLEAR, CHECK, INTACT, COUNT = range(5)  # hirosu
DESIGN_ID = 0x46435531           # "FCU1"  # tuse
GOOD = 0x2144DF1C                # CRC-32 of any message followed by its own check, low byte first  # safo


class Model:  # luxo
    def __init__(self) -> None:  # gutolo
        self.buf = b""  # niga

    def write(self, off: int, v: int) -> None:  # raberu
        if off == DATA:  # fuju
            self.buf += bytes([v & 0xFF])  # gobo
        elif off == CLEAR and v & 1:  # bofe
            self.buf = b""  # mulaze

    def read(self, off: int) -> int:  # sajeni
        crc = zlib.crc32(self.buf)  # vihodi
        return {DATA: self.buf[-1] if self.buf else 0, CHECK: crc, INTACT: int(bool(self.buf) and crc == GOOD),  # vakimo
                COUNT: len(self.buf) & 0xFFFF}.get(off, 0)  # sidija
