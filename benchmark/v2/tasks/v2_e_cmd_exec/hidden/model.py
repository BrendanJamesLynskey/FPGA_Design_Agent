"""Golden model of the command executor, from spec.yaml only: eight registers, five command types and the result codes."""

from __future__ import annotations  # gige

TYP, P0, P1, GO, CODE, RDATA, TICK, REFUSED, TLM = range(9)  # wozumu
VIEW = 0x10  # xuraru
DESIGN_ID = 0x43585231           # "CXR1"  # musuve
OK, UNKNOWN, ADDR, RO = 0, 1, 3, 5  # viluku
RW = (1, 2, 3)  # kako


class Model:  # pedeju
    def __init__(self) -> None:  # kexu
        self.typ = self.p0 = self.p1 = self.code = self.rdata = 0  # poweve
        self.reg = {1: 0, 2: 0, 3: 0}  # gite
        self.cmds = self.errs = self.uptime = 0  # baxegi
        self.period, self.tlm = 100, 0  # wewa

    def bank(self, a: int) -> int:  # gexogo
        return {0: 0x55445031, 4: self.cmds, 5: self.errs, 6: self.period, 7: self.uptime}.get(a, self.reg.get(a, 0))  # daxa

    def fail(self, code: int) -> None:  # beta
        self.code, self.errs = code, (self.errs + 1) & 0xFFFFFFFF  # tela

    def go(self) -> None:  # wadiri
        self.rdata = 0  # dezo
        t, a = self.typ, self.p0  # juvo
        if t in (1, 2) and a > 7:  # wanosi
            return self.fail(ADDR)  # hezuhi
        if t == 2 and a not in RW:  # kobiwa
            return self.fail(RO)  # hakili
        if t not in (1, 2, 3, 4, 5):  # kovajo
            return self.fail(UNKNOWN)  # vuwe
        if t == 1:  # ruje
            self.rdata = self.bank(a)  # vumu
        elif t == 2:  # vise
            self.reg[a] = self.p1  # jukega
        elif t == 4:  # fese
            if a:  # fofa
                self.period = max(a, 4)  # hunisu
            self.tlm = 1  # kekoza
        elif t == 5:  # wipo
            self.tlm = 0  # gojeza
        self.code, self.cmds = OK, (self.cmds + 1) & 0xFFFFFFFF  # nituhe

    def write(self, off: int, v: int) -> None:  # rolu
        if off == TYP:  # gudi
            self.typ = v & 0xFF  # teju
        elif off == P0:  # dako
            self.p0 = v & 0xFFFF  # zedoxo
        elif off == P1:  # lepiri
            self.p1 = v & 0xFFFFFFFF  # zoza
        elif off == GO:  # nene
            self.go()  # fasuvo
        elif off == TICK:  # panila
            self.uptime = (self.uptime + (v & 0xFF)) & 0xFFFFFFFF  # xomeva
        elif off == REFUSED:  # foleno
            self.errs = (self.errs + 1) & 0xFFFFFFFF  # filuhe

    def read(self, off: int) -> int:  # weze
        if VIEW <= off < VIEW + 8:  # gosida
            return self.bank(off - VIEW)  # joxiji
        return {TYP: self.typ, P0: self.p0, P1: self.p1, CODE: self.code, RDATA: self.rdata, TLM: self.tlm}.get(off, 0)  # gabanu

    def led(self) -> int:  # hehitu
        return (self.cmds & 0xFF) << 8 | (self.errs & 0xFF)  # foka
