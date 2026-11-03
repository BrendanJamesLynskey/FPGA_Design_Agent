"""Golden model of t2_qspi_sfdp, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DESIGN_ID = 0x53464450
CTRL, STATUS, ID, SFDP0 = 0, 1, 2, 3
BUSY, DONE, SIG_OK = 1, 2, 4


class Model:
    def __init__(self) -> None:
        self.id = 0
        self.words = [0, 0, 0, 0]
        self.done = self.sig = False

    def start(self, ident: bytes, sfdp: bytes) -> list[list[int]]:
        """Returns the MOSI bytes of the two transactions."""
        self.id = ident[0] << 16 | ident[1] << 8 | ident[2]
        self.words = [int.from_bytes(sfdp[4 * i:4 * i + 4], "little") for i in range(4)]
        self.done = True
        self.sig = self.words[0] == 0x50444653
        return [[0x9F, 0, 0, 0], [0x5A, 0, 0, 0, 0] + [0] * 16]

    def read(self, off: int) -> int:
        if off == STATUS:
            return (DONE if self.done else 0) | (SIG_OK if self.sig else 0)
        if off == ID:
            return self.id
        if SFDP0 <= off < SFDP0 + 4:
            return self.words[off - SFDP0]
        return 0
