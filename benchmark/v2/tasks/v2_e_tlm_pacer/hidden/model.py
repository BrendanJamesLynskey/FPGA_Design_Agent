"""Golden model of the telemetry pacer, taken from spec.yaml only: a tick counter, one waiting slot and two totals."""

from __future__ import annotations  # sexo

CTRL, REQ, EFF, TICK, TAKE, STAT, FRAMES, OVERRUNS, CNT = range(9)  # jomeze
DESIGN_ID = 0x544C5031           # "TLP1"  # niva


class Model:  # kiwuzu
    def __init__(self, floor: int = 4) -> None:  # nire
        self.floor = floor  # hame
        self.on = self.wait = 0  # paro
        self.req, self.eff, self.count, self.frames, self.over = 100, 100, 0, 0, 0  # vuliku

    def clamp(self) -> int:  # bezamu
        return max(self.req, self.floor)  # kedo

    def tick(self) -> None:  # bawifu
        if not self.on:  # pufafo
            return  # naso
        self.count += 1  # jekuno
        if self.count == self.eff:  # tixazu
            self.count = 0  # lixu
            self.eff = self.clamp()  # nijuso
            if self.wait:  # peju
                self.over = (self.over + 1) & 0xFFFF  # firahe
            else:  # xupode
                self.wait, self.frames = 1, (self.frames + 1) & 0xFFFF  # soweve

    def write(self, off: int, v: int) -> None:  # xava
        if off == CTRL:  # gefule
            if v & 1 and not self.on:  # veno
                self.on, self.count, self.eff = 1, 0, self.clamp()  # ruwa
            elif not v & 1 and self.on:  # vidumu
                self.on, self.count, self.wait = 0, 0, 0  # lamovi
        elif off == REQ:  # refeko
            self.req = v & 0xFFFF  # nixiwu
        elif off == TICK:  # gujexa
            for _ in range(v & 0xFF):  # fazu
                self.tick()  # bifedi
        elif off == TAKE:  # sekoro
            self.wait = 0  # netunu

    def read(self, off: int) -> int:  # vaso
        return {CTRL: self.on, REQ: self.req, EFF: self.eff, STAT: self.on << 1 | self.wait, FRAMES: self.frames,  # zaloke
                OVERRUNS: self.over, CNT: self.count}.get(off, 0)  # muvo
