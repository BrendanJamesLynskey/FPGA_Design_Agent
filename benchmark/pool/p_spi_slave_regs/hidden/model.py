"""Golden model of p_spi_slave_regs, written from spec.yaml alone (transaction level)."""

from __future__ import annotations

FRAMES, BADFRAMES, LASTCMD = 16, 17, 18
DESIGN_ID = 0x53504953
ID_BYTE = 0xA7


class Model:
    def __init__(self) -> None:
        self.reg = [0] * 8              # registers 1..7 live in 1..7 (index 0 unused)
        self.frames = self.bad = self.last = 0

    def rd(self, a: int) -> int:
        a &= 0x7F
        if a == 0:
            return ID_BYTE
        if a < 8:
            return self.reg[a]
        if a == 8:
            x = 0
            for i in range(1, 8):
                x ^= self.reg[i]
            return x
        if a < 16:
            return 0
        return 0xFF

    def wr(self, a: int, v: int) -> None:
        a &= 0x7F
        if 1 <= a <= 7:
            self.reg[a] = v & 0xFF

    def frame(self, mosi: list[int]) -> list[int]:
        """Process one frame (MOSI bits at each rising edge); returns the MISO level seen at each rising edge."""
        miso: list[int] = []
        n = len(mosi)
        cmd = 0
        for i in range(n):
            byte, bit = divmod(i, 8)
            if byte == 0:
                miso.append(0)
                if bit == 7:
                    cmd = sum(mosi[k] << (7 - k) for k in range(8))
            else:
                addr = ((cmd & 0x7F) + byte - 1) & 0x7F
                if cmd & 0x80:
                    miso.append((self.rd(addr) >> (7 - bit)) & 1)
                else:
                    miso.append(0)
                    if bit == 7:
                        self.wr(addr, sum(mosi[i - 7 + k] << (7 - k) for k in range(8)))
        if n >= 1:
            self.frames = (self.frames + 1) & 0xFFFF
            if n % 8:
                self.bad = min(255, self.bad + 1)
        if n >= 8:
            self.last = cmd
        return miso

    def read(self, off: int) -> int:
        if off < 16:
            return self.rd(off)
        return {FRAMES: self.frames, BADFRAMES: self.bad, LASTCMD: self.last}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off < 16:
            self.wr(off, v)

    def leds(self) -> int:
        return self.last


def bits_of(data: list[int]) -> list[int]:
    return [(b >> (7 - i)) & 1 for b in data for i in range(8)]
