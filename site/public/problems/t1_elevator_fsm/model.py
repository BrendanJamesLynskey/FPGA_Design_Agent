"""Golden model of t1_elevator_fsm, written from spec.yaml alone (never from any RTL).

A clocked model: run_to(t) steps the spec's rules one clock at a time and logs events (time, kind, floor) with
kind in "depart", "arrive", "open", "close". Calls are scheduled at the clock they are seen."""

from __future__ import annotations

FLOOR, DIR, PENDING, STATE, MOVES = range(5)
IDLE, MOVING, DOOR = 0, 1, 2
DESIGN_ID = 0x454C4556          # "ELEV"


class Model:
    def __init__(self, floor_cycles: int, door_cycles: int) -> None:
        self.fc, self.dc = floor_cycles, door_cycles
        self.floor, self.dir, self.pend, self.state, self.moves = 0, 0, 0, IDLE, 0
        self.timer = 0
        self.t = 0
        self.sched: dict[int, int] = {}
        self.events: list[tuple[int, str, int]] = []

    def call(self, at: int, mask: int) -> None:
        assert at >= self.t, "a call scheduled in the model's past"
        self.sched[at] = self.sched.get(at, 0) | mask

    def _ahead(self, d: int, p: int) -> bool:
        return any(p >> k & 1 for k in range(4) if (k > self.floor if d == 0 else k < self.floor))

    def _decide(self, p: int) -> int:
        if p >> self.floor & 1:
            p &= ~(1 << self.floor)
            self.state, self.timer = DOOR, 0
            self.events.append((self.t, "open", self.floor))
        elif self._ahead(self.dir, p):
            self.state, self.timer = MOVING, 0
            self.events.append((self.t, "depart", self.floor))
        elif self._ahead(1 - self.dir, p):
            self.dir ^= 1
            self.state, self.timer = MOVING, 0
            self.events.append((self.t, "depart", self.floor))
        else:
            self.state = IDLE
        return p

    def step(self) -> None:
        c = self.sched.pop(self.t, 0)
        if self.state == DOOR:
            c &= ~(1 << self.floor)
        p = self.pend | c
        if self.state == MOVING:
            self.timer += 1
            if self.timer == self.fc:
                self.floor += -1 if self.dir else 1
                assert 0 <= self.floor <= 3
                self.moves = (self.moves + 1) & 0xFFFF
                self.timer = 0
                self.events.append((self.t, "arrive", self.floor))
                if p >> self.floor & 1:
                    p &= ~(1 << self.floor)
                    self.state = DOOR
                    self.events.append((self.t, "open", self.floor))
        elif self.state == DOOR:
            self.timer += 1
            if self.timer == self.dc:
                self.events.append((self.t, "close", self.floor))
                p = self._decide(p)
        else:
            p = self._decide(p)
        self.pend = p
        self.t += 1

    def run_to(self, t: int) -> None:
        while self.t < t:
            self.step()

    def read(self, off: int) -> int:
        return {FLOOR: self.floor, DIR: self.dir, PENDING: self.pend, STATE: self.state,
                MOVES: self.moves}.get(off, 0)

    def leds(self) -> int:
        return (self.state == DOOR) << 15 | (self.state == MOVING) << 14 | self.pend << 4 | 1 << self.floor
