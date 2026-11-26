"""Mock buses for the brief 209 pilot designs: each is a small Python model of the register behaviour in its spec.md, so the host check logic
runs without a board (and a faulty variant shows the check can fail). `VClock` is virtual time, so a ten-minute soak takes no time."""
from __future__ import annotations

import random
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "host"))
import check_p2_bram_rom as c2  # noqa: E402
import check_p4_fir_dsp as c4  # noqa: E402

M32 = 0xFFFFFFFF
BUILD = 0x1234ABCD


class VClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        self.t += 0.001                       # every call costs a little time, like a bus transaction
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


class MockBase:
    ID = 0
    def __init__(self, clk: VClock, **faults) -> None:
        self.clk, self.f = clk, faults
        self.scratch = 0

    def rd(self, a: int) -> int:
        if a == 0:
            return self.ID
        if a == 4:
            return self.f.get("build", BUILD)
        if a == 8:
            return self.scratch
        return self.read(a) & M32

    def wr(self, a: int, v: int) -> None:
        v &= M32
        if a == 8:
            self.scratch = v
        else:
            self.write(a, v)

    def read(self, a): return 0
    def write(self, a, v): pass


class P1(MockBase):
    ID = 0x20910001

    def __init__(self, clk, **f):
        super().__init__(clk, **f)
        self.gate, self.ctrl, self.done, self.start_t, self.cnt, self.act, self.nd = 156_250_000, 0, False, None, 0, 0, 0
        self.ppm = f.get("ppm", 12.0)

    def _upd(self):
        if self.start_t is not None and self.clk.t >= self.start_t + self.gate / 156.25e6:
            self.act = self.gate
            self.cnt = round(self.gate * 0.16 * (1 + self.ppm * 1e-6)) + random.Random(self.nd).randint(-2, 2)
            self.start_t, self.done, self.nd = None, True, self.nd + 1

    def read(self, a):
        self._upd()
        return {0x10: self.gate, 0x14: self.ctrl, 0x18: (1 if self.start_t is not None else 0) | (2 if self.done else 0),
                0x1C: self.cnt, 0x20: self.act, 0x24: self.nd}.get(a, 0)

    def write(self, a, v):
        if a == 0x10: self.gate = v
        if a == 0x14:
            self.ctrl = v & 2
            if v & 1 and self.start_t is None:
                self.start_t, self.done = self.clk.t, False


class P2(MockBase):
    ID = 0x20920001

    def __init__(self, clk, **f):
        super().__init__(clk, **f)
        self.rom = c2.rom_words()
        self.ram = [0xC0DE0000 + i for i in range(1024)]
        if f.get("bad_rom"): self.rom[77] ^= 1
        if f.get("bad_ram"): self.ram[5] = 0
        self.addr, self.auto, self.passes, self.errs, self.first, self.done_p, self.status = 0, 0, 1, 0, M32, 0, 0

    def read(self, a):
        if a == 0x10: return self.addr
        if a == 0x14:
            v = self.rom[self.addr]
            if self.auto: self.addr = (self.addr + 1) & 1023
            return v
        if a == 0x18:
            v = self.ram[self.addr]
            if self.auto: self.addr = (self.addr + 1) & 1023
            return v
        return {0x1C: self.auto, 0x24: self.passes, 0x28: (2 | self.done_p << 16) if self.status else 0, 0x2C: self.errs, 0x30: self.first}.get(a, 0)

    def write(self, a, v):
        if a == 0x10: self.addr = v & 1023
        elif a == 0x18:
            self.ram[self.addr] = v
            if self.auto: self.addr = (self.addr + 1) & 1023
        elif a == 0x1C: self.auto = v & 1
        elif a == 0x24: self.passes = v
        elif a == 0x20 and v & 1:
            inj = bool(v & 2)
            self.errs = self.passes if inj else (5 if self.f.get("march_fault") else 0)
            self.first = 0x155 if self.errs else M32
            self.ram = [0] * 1024
            self.done_p, self.status = self.passes, 1


class P3(MockBase):
    ID = 0x20930001

    def __init__(self, clk, **f):
        super().__init__(clk, **f)
        self.buf, self.busy, self.n = b"", 0, 0

    def read(self, a):
        crc = zlib.crc32(self.buf)
        if self.f.get("bad_crc") and len(self.buf) == 65: crc ^= 0x100
        return {0x20: crc, 0x24: len(self.buf), 0x28: self.busy}.get(a, 0)

    def write(self, a, v):
        if a == 0x10 and v & 1: self.buf, self.busy = b"", 0
        elif a == 0x14: self.buf += v.to_bytes(4, "little"); self.busy += 1
        elif a == 0x1C: self.n = v & 3
        elif a == 0x18: self.buf += v.to_bytes(4, "little")[:self.n]


class P4(MockBase):
    ID = 0x20940001

    def __init__(self, clk, **f):
        super().__init__(clk, **f)
        self.m, self.inq, self.outq = c4.Model(), [], []

    def read(self, a):
        if a == 0x18:
            if not self.outq: return 0
            y = self.outq.pop(0)
            if self.f.get("bad_fir") and y == 12345: y += 1
            return 0x80000000 | (y & 0xFFFF)
        if a == 0x1C: return (len(self.inq) << 4) | (len(self.outq) << 20)
        if a == 0x20: return self.m.sat
        if a == 0x24: return self.m.done
        return 0

    def write(self, a, v):
        if a == 0x10:
            if v & 1: self.m, self.inq, self.outq = c4.Model(), [], []
            if v & 2:
                self.outq += self.m.feed([c4.s16(x) for x in self.inq]); self.inq = []
                if self.f.get("no_sat"): self.m.sat = 0
        elif a == 0x14 and len(self.inq) < 1024: self.inq.append(v & 0xFFFF)


class P5(MockBase):
    ID = 0x20950001

    def __init__(self, clk, **f):
        super().__init__(clk, **f)
        self.ctrl, self.t0, self.acc = 0, None, dict.fromkeys(("w", "r", "e", "o", "u", "s"), 0)
        self.occ = 0
        self.lat = None
        self.inj = 0

    def _adv(self):
        if self.t0 is not None and self.ctrl & 1:
            dt = self.clk.t - self.t0
            slow = bool(self.ctrl & 2)
            rate_r = 156.25e6 / 8 if slow else 25e6
            rate_w = rate_r if slow else 25e6
            self.acc["w"] += int(dt * rate_w); self.acc["r"] += int(dt * rate_r)
            if slow: self.acc["s"] += int(dt * (25e6 - rate_r)); self.occ = 512
            if self.f.get("errs") and self.acc["w"] > 3e9: self.acc["e"] = 1
        self.t0 = self.clk.t

    def read(self, a):
        l = self.lat or {}
        k = {0x14: "w", 0x18: "r", 0x1C: "e", 0x20: "o", 0x24: "u", 0x28: "s"}.get(a)
        if k: return l.get(k, 0) & M32
        if a == 0x2C: return l.get("occ", 0)
        return 0

    def write(self, a, v):
        if a == 0x10:
            self._adv()
            if v & 4 and not self.ctrl & 1: self.acc, self.occ = dict.fromkeys(self.acc, 0), 0
            if v & 8: self.acc["e"] += 1
            self.ctrl = v & 3
            if self.ctrl & 1 and not self.ctrl & 2: self.occ = max(self.occ, 3)
        elif a == 0x30:
            self._adv()
            self.lat = {**self.acc, "occ": self.occ}


class P6(MockBase):
    ID = 0x20960001

    def __init__(self, clk, **f):
        super().__init__(clk, **f)
        self.sel, self.active, self.swc, self.errs, self.gate, self.fstart, self.cnt, self.mcnt, self.lat = 0, 0, 0, 0, 25_000_000, None, 0, 0, 0
        self.bdiv, self.fdone, self.pend_t = 2, False, None

    def _upd(self):
        if self.pend_t is not None and self.clk.t >= self.pend_t:
            self.active, self.pend_t = self.sel, None
        if self.fstart is not None and self.clk.t >= self.fstart + self.gate / 25e6:
            self.cnt = round(self.gate * (1.0 if self.active == 0 else 6.25 / self.bdiv) * (1 + 40e-6)) if not self.f.get("stuck") else self.gate
            self.fstart, self.fdone = None, True

    def read(self, a):
        self._upd()
        return {0x10: self.sel, 0x14: (1 if self.pend_t is not None else 0) | (self.active << 1), 0x18: self.bdiv, 0x1C: self.gate,
                0x24: (1 if self.fstart is not None else 0) | (2 if self.fdone else 0), 0x28: self.cnt, 0x2C: self.errs + (1 if self.f.get("glitch") and self.swc > 200 else 0),
                0x30: self.lat, 0x34: self.swc}.get(a, 0)

    def write(self, a, v):
        self._upd()
        if a == 0x10 and (v & 1) != self.sel:
            self.sel = v & 1
            self.swc += 1
            self.pend_t = self.clk.t + 0.0002
        elif a == 0x1C: self.gate = v
        elif a == 0x20 and v & 1: self.fstart, self.fdone = self.clk.t, False
        elif a == 0x38: self.mcnt += 123457; self.lat = self.mcnt


MOCKS = {"p1_clkmeter": P1, "p2_bram_rom": P2, "p3_crc_engine": P3, "p4_fir_dsp": P4, "p5_async_fifo": P5, "p6_glitchfree_mux": P6}
