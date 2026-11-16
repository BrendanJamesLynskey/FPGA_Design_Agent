"""Golden model of the command executor, from spec.yaml only: eight registers, five command types and the result codes."""

from __future__ import annotations

TYP, P0, P1, GO, CODE, RDATA, TICK, REFUSED, TLM = range(9)
VIEW = 0x10
DESIGN_ID = 0x43585231           # "CXR1"
OK, UNKNOWN, ADDR, RO = 0, 1, 3, 5
RW = (1, 2, 3)


class Model:
    def __init__(self) -> None:
        self.typ = self.p0 = self.p1 = self.code = self.rdata = 0
        self.reg = {1: 0, 2: 0, 3: 0}
        self.cmds = self.errs = self.uptime = 0
        self.period, self.tlm = 100, 0

    def bank(self, a: int) -> int:
        return {0: 0x55445031, 4: self.cmds, 5: self.errs, 6: self.period, 7: self.uptime}.get(a, self.reg.get(a, 0))

    def fail(self, code: int) -> None:
        self.code, self.errs = code, (self.errs + 1) & 0xFFFFFFFF

    def go(self) -> None:
        self.rdata = 0
        t, a = self.typ, self.p0
        if t in (1, 2) and a > 7:
            return self.fail(ADDR)
        if t == 2 and a not in RW:
            return self.fail(RO)
        if t not in (1, 2, 3, 4, 5):
            return self.fail(UNKNOWN)
        if t == 1:
            self.rdata = self.bank(a)
        elif t == 2:
            self.reg[a] = self.p1
        elif t == 4:
            if a:
                self.period = max(a, 4)
            self.tlm = 1
        elif t == 5:
            self.tlm = 0
        self.code, self.cmds = OK, (self.cmds + 1) & 0xFFFFFFFF

    def write(self, off: int, v: int) -> None:
        if off == TYP:
            self.typ = v & 0xFF
        elif off == P0:
            self.p0 = v & 0xFFFF
        elif off == P1:
            self.p1 = v & 0xFFFFFFFF
        elif off == GO:
            self.go()
        elif off == TICK:
            self.uptime = (self.uptime + (v & 0xFF)) & 0xFFFFFFFF
        elif off == REFUSED:
            self.errs = (self.errs + 1) & 0xFFFFFFFF

    def read(self, off: int) -> int:
        if VIEW <= off < VIEW + 8:
            return self.bank(off - VIEW)
        return {TYP: self.typ, P0: self.p0, P1: self.p1, CODE: self.code, RDATA: self.rdata, TLM: self.tlm}.get(off, 0)

    def led(self) -> int:
        return (self.cmds & 0xFF) << 8 | (self.errs & 0xFF)
