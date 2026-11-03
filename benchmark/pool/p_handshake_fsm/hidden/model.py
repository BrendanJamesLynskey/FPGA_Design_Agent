"""Golden model of p_handshake_fsm, written from spec.yaml alone (clock-level; RTL outputs may lag by a few clocks)."""

from __future__ import annotations

TRANSFERS, ABORTS, FAULTS, ACK_DELAY, HOLD_LIMIT = 0, 1, 2, 3, 4
DESIGN_ID = 0x4853484B
IDLE, WAIT, ACKED, FAULT = range(4)


class Model:
    def __init__(self, ack_delay: int, hold_limit: int) -> None:
        self.ack_delay, self.hold_limit = ack_delay, hold_limit
        self.s1 = self.s2 = 0
        self.state = IDLE
        self.cnt = 0
        self.transfers = self.aborts = self.faults = 0

    def step(self, sw: int) -> int:
        """One clock with raw SW; returns LED[2:0] (bit0 ACK, bit1 FAULT, bit2 WAIT) afterwards."""
        r = self.s2
        if self.state == IDLE:
            if r:
                self.state, self.cnt = WAIT, 0
        elif self.state == WAIT:
            if not r:
                self.aborts = (self.aborts + 1) & 0xFFFF
                self.state = IDLE
            elif self.cnt + 1 >= self.ack_delay:
                self.state, self.cnt = ACKED, 0
            else:
                self.cnt += 1
        elif self.state == ACKED:
            if not r:
                self.transfers = (self.transfers + 1) & 0xFFFF
                self.state = IDLE
            elif self.cnt + 1 >= self.hold_limit:
                self.faults = (self.faults + 1) & 0xFFFF
                self.state = FAULT
            else:
                self.cnt += 1
        elif not r:
            self.state = IDLE
        self.s2, self.s1 = self.s1, sw & 1
        return int(self.state == ACKED) | int(self.state == FAULT) << 1 | int(self.state == WAIT) << 2

    def run(self, sws: list[int]) -> list[int]:
        return [self.step(s) for s in sws]

    def read(self, off: int) -> int:
        return {TRANSFERS: self.transfers, ABORTS: self.aborts, FAULTS: self.faults,
                ACK_DELAY: self.ack_delay, HOLD_LIMIT: self.hold_limit}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == TRANSFERS:
            self.transfers = self.aborts = self.faults = 0
