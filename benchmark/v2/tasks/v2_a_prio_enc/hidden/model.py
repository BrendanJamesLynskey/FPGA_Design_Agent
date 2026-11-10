"""Golden model of v2_a_prio_enc, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

REQ, MASK, WINNER = 0, 1, 2
DESIGN_ID = 0x50454E43          # "PENC"
LATENCY = 3                     # switch change to LED, in clocks


def encode(req: int, mask: int) -> tuple[int, int, int]:
    """(INDEX, VALID, GRANT)."""
    eff = req & ~mask & 0xFFFF
    if eff == 0:
        return 15, 0, 0
    i = eff.bit_length() - 1
    return i, 1, 1 << i


class Model:
    def __init__(self) -> None:
        self.req = 0
        self.mask = 0

    def write(self, off: int, v: int) -> None:
        if off == MASK:
            self.mask = v & 0xFFFF

    def grant(self) -> int:
        return encode(self.req, self.mask)[2]

    def read(self, off: int) -> int:
        i, valid, _ = encode(self.req, self.mask)
        return {REQ: self.req, MASK: self.mask, WINNER: valid << 4 | i}.get(off, 0)
