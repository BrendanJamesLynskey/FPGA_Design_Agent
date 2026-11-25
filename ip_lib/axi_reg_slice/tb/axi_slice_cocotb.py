"""cocotb bench for ip_lib/axi_reg_slice (axil_reg_slice and axi4_reg_slice), brief 151.

All five channels run at once, each with its own random source and sink; every channel is checked clock by clock against the
pipe_reg model (ip_lib/pipe_reg/model.py) for its MODE and N, on s_ready, m_valid and the packed payload, plus the AXI rule that
a beat offered and not taken stays offered unchanged, and that no channel's valid depends on its ready (ready flipped within a
clock). The channels are independent, so each channel's accepted beats must leave in order. Environment: AXI_SEED, AXI_CLOCKS."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from ip_lib.pipe_reg import model as M

SEED = int(os.environ.get("AXI_SEED", "1"))
CLOCKS = int(os.environ.get("AXI_CLOCKS", "1200"))


def fields(top: str, p: dict):
    a, d, i = p["ADDR_W"], p["DATA_W"], p.get("ID_W", 0)
    if top == "axil_reg_slice":
        return {"aw": [("addr", a), ("prot", 3)], "w": [("data", d), ("strb", d // 8)], "b": [("resp", 2)],
                "ar": [("addr", a), ("prot", 3)], "r": [("data", d), ("resp", 2)]}
    big = [("id", i), ("addr", a), ("len", 8), ("size", 3), ("burst", 2), ("lock", 1), ("cache", 4), ("prot", 3), ("qos", 4)]
    return {"aw": big, "w": [("data", d), ("strb", d // 8), ("last", 1)], "b": [("id", i), ("resp", 2)], "ar": big,
            "r": [("id", i), ("data", d), ("resp", 2), ("last", 1)]}


class Chan:
    def __init__(self, dut, c, fl, n, mode, fwd, rng):
        self.d, self.c, self.fl, self.fwd, self.rng = dut, c, fl, fwd, rng
        self.w = sum(w for _, w in fl)
        self.model = M.Pipe(n, mode)
        self.n = n
        self.src, self.dst = ("s", "m") if fwd else ("m", "s")
        g = lambda side, s: getattr(dut, f"{side}_axi_{c}{s}")
        self.sv, self.sr = g(self.src, "valid"), g(self.src, "ready")
        self.dv, self.dr = g(self.dst, "valid"), g(self.dst, "ready")
        self.sf = [(g(self.src, f), w) for f, w in fl]
        self.df = [(g(self.dst, f), w) for f, w in fl]
        self.valid, self.data, self.acc, self.out = 0, 0, [], []
        self.pv, self.pr = rng.choice([1.0, 0.5, 0.2]), rng.choice([1.0, 0.5, 0.2])

    def drive(self):
        if not self.valid and self.rng.random() < self.pv:
            self.valid, self.data = 1, self.rng.getrandbits(self.w)
        self.mr = int(self.rng.random() < self.pr)
        self.sv.value = self.valid
        self.dr.value = self.mr
        lo = 0
        for h, w in reversed(self.sf):                    # the concatenation puts the first field highest
            h.value = (self.data >> lo) & ((1 << w) - 1)
            lo += w

    def sample(self, clk_n):
        sr, dv = int(self.sr.value), int(self.dv.value)
        got = None
        if dv:
            got, lo = 0, 0
            for h, w in reversed(self.df):
                got |= int(h.value) << lo
                lo += w
        e = self.model.signals(bool(self.mr)) if self.n else (bool(self.mr), bool(self.valid), self.data if self.valid else None)
        assert bool(sr) == e[0], f"clock {clk_n} {self.c}: ready {sr}, model {int(e[0])}"
        assert bool(dv) == e[1], f"clock {clk_n} {self.c}: valid {dv}, model {int(e[1])}"
        if dv:
            assert got == e[2], f"clock {clk_n} {self.c}: payload {got:#x}, model {e[2]:#x}"
        self.dr.value = 1 - self.mr                      # valid must not depend on ready
        return sr, dv, got

    def check_flip(self, clk_n, dv):
        assert int(self.dv.value) == dv, f"clock {clk_n} {self.c}: valid depends on ready"
        self.dr.value = self.mr

    def edge(self, sr, dv, got):
        acc = self.valid and sr
        if acc:
            self.acc.append(self.data)
            self.valid = 0
        if dv and self.mr:
            self.out.append(got)
        if self.n:
            self.model.clock(bool(self.sv.value), self.data if acc or self.valid else 0, bool(self.mr))
        assert self.out == self.acc[:len(self.out)], f"{self.c}: beats lost, repeated or reordered"
        return acc


@cocotb.test()
async def five_channels(dut):
    top = dut._name
    p = {k: int(getattr(dut, k).value) for k in ("ADDR_W", "DATA_W", "N", "MODE_AW", "MODE_W", "MODE_B", "MODE_AR", "MODE_R")}
    if top == "axi4_reg_slice":
        p["ID_W"] = int(dut.ID_W.value)
    rng = random.Random(SEED + p["N"] + p["MODE_AW"])
    fl = fields(top, p)
    chans = [Chan(dut, c, fl[c], p["N"], p[f"MODE_{c.upper()}"], c in ("aw", "w", "ar"), rng) for c in ("aw", "w", "b", "ar", "r")]
    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    dut.aresetn.value = 0
    for c in chans:
        c.sv.value = 0
        c.dr.value = 0
    for _ in range(3):
        await RisingEdge(dut.aclk)
    await Timer(1, unit="ns")
    dut.aresetn.value = 1
    for ch in chans:                                     # the model is reset; one idle clock after reset (AXI4-Stream 2.8 style)
        ch.model.reset()
    ch_valid = [c.valid for c in chans]
    for t in range(CLOCKS):
        for c in chans:
            if t == 0:
                c.valid = 0
                c.sv.value = 0
                c.mr = 0
                c.dr.value = 0
            else:
                c.drive()
        await Timer(1, unit="ns")
        sm = [c.sample(t) for c in chans]
        await Timer(1, unit="ns")
        for c, s in zip(chans, sm):
            c.check_flip(t, s[1])
        await Timer(1, unit="ns")
        # the model needs the s_valid actually offered in this clock
        for c, s in zip(chans, sm):
            offered = c.valid
            if c.n:
                c.model.clock(bool(offered), c.data, bool(c.mr))
            acc = offered and s[0]
            if acc:
                c.acc.append(c.data)
                c.valid = 0
            if s[1] and c.mr:
                c.out.append(s[2])
            assert c.out == c.acc[:len(c.out)], f"{c.c}: beats lost, repeated or reordered"
        await RisingEdge(dut.aclk)
        await Timer(1, unit="ns")
    for c in chans:
        assert len(c.acc) > 0 or c.pv < 0.3, f"{c.c}: no beat was ever accepted"
    dut._log.info("five_channels ok: accepted %s", [len(c.acc) for c in chans])
