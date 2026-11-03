"""Golden model of p_i2c_slave_mem, written from spec.yaml alone (byte level)."""

from __future__ import annotations

MATCHES, BADPTR, PTR = 16, 17, 18
DESIGN_ID = 0x49324353
ADDRESS = 0x2A
ID_BYTE = 0x5C


class Model:
    def __init__(self) -> None:
        self.reg = [0] * 8
        self.wrcount = 0
        self.ptr = 0
        self.matches = self.badptr = 0
        self.matched = False
        self.rw = 0
        self.first = True
        self.dead = False

    def view(self, a: int) -> int:
        a &= 15
        if a == 0:
            return ID_BYTE
        if a < 8:
            return self.reg[a]
        if a == 8:
            return self.wrcount
        if a == 9:
            x = 0
            for i in range(1, 8):
                x ^= self.reg[i]
            return x
        return 0

    def start(self) -> None:
        self.matched = False

    def addr(self, byte: int) -> bool:
        self.matched = (byte >> 1) == ADDRESS
        self.rw = byte & 1
        self.first = True
        self.dead = False
        if self.matched:
            self.matches = (self.matches + 1) & 0xFFFF
        return self.matched

    def wbyte(self, v: int) -> bool:
        if not self.matched or self.rw:
            return False
        if self.dead:
            return False
        if self.first:
            self.first = False
            if v < 16:
                self.ptr = v
                return True
            self.badptr = min(255, self.badptr + 1)
            self.dead = True
            return False
        if 1 <= self.ptr <= 7:
            self.reg[self.ptr] = v & 0xFF
            self.wrcount = min(255, self.wrcount + 1)
        self.ptr = (self.ptr + 1) & 15
        return True

    def rbyte(self) -> int:
        if not self.matched or not self.rw:
            return 0xFF
        v = self.view(self.ptr)
        self.ptr = (self.ptr + 1) & 15
        return v

    def read(self, off: int) -> int:
        if off < 16:
            return self.view(off)
        return {MATCHES: self.matches, BADPTR: self.badptr, PTR: self.ptr}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if 1 <= off <= 7:
            self.reg[off] = v & 0xFF

    def leds(self) -> int:
        return self.reg[1]
