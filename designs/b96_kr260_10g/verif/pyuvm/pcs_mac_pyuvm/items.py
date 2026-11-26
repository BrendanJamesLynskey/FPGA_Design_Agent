"""Sequence items and monitor transactions of the pyuvm bench (brief 123)."""
from __future__ import annotations

from pyuvm import uvm_sequence_item

PATTERNS = ["PAT_RANDOM", "PAT_ZEROS", "PAT_ONES", "PAT_COUNT", "PAT_ALT"]


def make_payload(rng, n: int, pat: str) -> bytes:
    if pat == "PAT_ZEROS":
        return bytes(n)
    if pat == "PAT_ONES":
        return b"\xff" * n
    if pat == "PAT_COUNT":
        return bytes(i & 0xFF for i in range(n))
    if pat == "PAT_ALT":
        return bytes(0x55 if i % 2 else 0xAA for i in range(n))
    return rng.randbytes(n)


class FrameItem(uvm_sequence_item):
    """One Ethernet frame offered to mac64_tx: payload bytes (the MAC adds preamble, FCS, terminate and the gap), the poison flag (a deliberately bad FCS),
    and the idle clocks the driver leaves before the first word. `abort_after` > 0 makes it a fault-injection item: the first `abort_after` words of the payload
    only, then the source stalls (mac64_tx's `underrun`); the payload must hold at least 8 * abort_after bytes."""

    def __init__(self, name="frame_item", payload=b"", pat="PAT_RANDOM", poison=False, noise_poison=False, gap=0, abort_after=0):
        super().__init__(name)
        self.payload, self.pat, self.poison, self.noise_poison, self.gap = bytes(payload), pat, bool(poison), bool(noise_poison), gap
        self.abort_after = abort_after        # fault injection (brief 158): offer this many whole words (at least 1), then drop s_valid with no s_last: a transmit underrun

    @property
    def len(self) -> int:
        return len(self.payload)

    def __str__(self) -> str:
        return f"frame len={self.len} pat={self.pat} poison={self.poison} gap={self.gap}"


class XgItem(uvm_sequence_item):
    """XGMII words offered directly to pcs_tx (the MAC is bypassed by the mux)."""

    def __init__(self, name="xg_item", words=(), tag=""):
        super().__init__(name)
        self.words, self.tag = list(words), tag


class LineItem(uvm_sequence_item):
    """The line agent's work items: kind is one of BLOCKS FLIP HDR SLIP_INS SLIP_DEL WAIT RXRESET BER."""

    def __init__(self, name="line_item", kind="WAIT", blks=(), mask=0, n=0, skip=0):
        super().__init__(name)
        self.kind, self.blks, self.mask, self.n, self.skip = kind, list(blks), mask, n, skip


class RxFrameObs:
    """One frame outcome of mac64_rx, assembled by the receive monitor."""
    __slots__ = ("cyc", "data", "fcs_ok", "aborted", "length")

    def __init__(self, cyc=0, data=b"", fcs_ok=False, aborted=False, length=0):
        self.cyc, self.data, self.fcs_ok, self.aborted, self.length = cyc, bytes(data), fcs_ok, aborted, length
