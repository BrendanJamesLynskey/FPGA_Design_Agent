"""Golden model of t2_spi_master_modes, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DESIGN_ID = 0x5350494D
CTRL, DIV, TXDATA, RXDATA, STATUS = 0, 1, 2, 3, 4
CPOL, CPHA, LSB, W16, CS_HOLD, LOOP = 1, 2, 4, 8, 16, 32
BUSY, DONE, CS_ACTIVE = 1, 2, 4


def nbits(ctrl: int) -> int:
    return 16 if ctrl & W16 else 8


def tx_bits(value: int, ctrl: int) -> list[int]:
    """The data bits in the order they go out on MOSI."""
    n = nbits(ctrl)
    order = range(n) if ctrl & LSB else range(n - 1, -1, -1)
    return [(value >> i) & 1 for i in order]


def assemble(bits: list[int], ctrl: int) -> int:
    """RXDATA from the bits received in order."""
    n = nbits(ctrl)
    order = list(range(n)) if ctrl & LSB else list(range(n - 1, -1, -1))
    return sum(b << i for b, i in zip(bits, order))


class Model:
    def __init__(self) -> None:
        self.ctrl = 0
        self.div = 50
        self.txdata = 0
        self.rxdata = 0
        self.done = False
        self.cs_low = False

    def write(self, off: int, v: int) -> bool:
        """Returns True if the write starts a frame (the caller then calls finish())."""
        v &= 0xFFFF_FFFF
        if off == CTRL:
            self.ctrl = v & 0x3F
            if not self.ctrl & CS_HOLD:
                self.cs_low = False
        elif off == DIV:
            if v & 0xFFFF >= 2:
                self.div = v & 0xFFFF
        elif off == TXDATA:
            self.txdata = v & 0xFFFF
            self.cs_low = True
            return True
        elif off == STATUS and v & DONE:
            self.done = False
        return False

    def finish(self, miso_bits: list[int] | None = None) -> list[int]:
        """The frame ends: returns the MOSI bits; RXDATA from ``miso_bits`` (or MOSI itself in loopback)."""
        out = tx_bits(self.txdata, self.ctrl)
        got = out if self.ctrl & LOOP else (miso_bits or [0] * len(out))
        self.rxdata = assemble(got, self.ctrl)
        self.done = True
        if not self.ctrl & CS_HOLD:
            self.cs_low = False
        return out

    def read(self, off: int) -> int:
        if off == CTRL:
            return self.ctrl
        if off == DIV:
            return self.div
        if off == TXDATA:
            return self.txdata
        if off == RXDATA:
            return self.rxdata
        if off == STATUS:
            return (DONE if self.done else 0) | (CS_ACTIVE if self.cs_low else 0)
        return 0
