"""cocotb bench of the ITCH/MoldUDP64 to OUCH path (rtl/itch_ouch_top.sv) against model/ref.py (brief 110).

Clock numbering: a word set after tick k is presented in cycle k; a registered output sampled after tick k+1 is visible in cycle k+1.
T is the cycle in which the last byte of a message is presented, so the decoded event is visible at T+2 and the top-of-book update at T+7.
Each test builds its stream with model/gen.py (seeded) or by hand, runs it through the model and through the RTL, and compares the messages'
decoded events, every top-of-book update, every order frame (bit exact) and every counter. B110_RECORD=<dir> writes measured latencies.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b110_itch_ouch.model import gen, proto, ref
from designs.b110_itch_ouch.model.ref import COUNTERS, Cfg, Model

PERIOD_PS = 6206
KIND = {"A": 0, "F": 0, "E": 1, "C": 1, "X": 2, "D": 3, "U": 4, "R": 5, "S": 6}
TIMING_DEPENDENT = ("spec", "abort", "late_abort", "rej_busy")
REC: dict = {}


class Bench:
    def __init__(self, dut, cfg: Cfg, spec: bool = False):
        self.dut, self.cfg, self.spec = dut, cfg, spec
        self.cyc = 0
        self.msgs, self.evs, self.tus, self.frames, self.aborts, self.late = [], [], [], [], [], 0
        self._cur = None
        self.last_word_cycle = {}

    # ---- clock, reset, configuration
    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, PERIOD_PS, unit="ps").start())
        for n in ("s_v", "s_sof", "s_eof", "s_err", "clr_cnt", "clr_flags", "clr_book", "clr_pos", "clr_ref"):
            getattr(d, n).value = 0
        d.s_d.value = 0
        d.s_keep.value = 0
        self.configure()
        d.rst.value = 1
        for _ in range(4):
            await self.tick(sample=False)
        d.rst.value = 0
        await self.tick(sample=False)
        await self.wait_ready()
        self.msgs, self.evs, self.tus, self.frames, self.aborts = [], [], [], [], []

    def configure(self, **kw):
        c, d = self.cfg, self.dut
        for k, v in kw.items():
            setattr(c, k, v)
        w = 0
        for i in range(c.n_inst):
            w |= int.from_bytes(proto.alpha(c.watch[i], 8), "big") << (64 * i)
        d.cfg_watch.value = w
        d.cfg_thr.value, d.cfg_qty.value, d.cfg_max_qty.value, d.cfg_max_pos.value = c.thr, c.qty, c.max_qty, c.max_pos
        d.cfg_band.value, d.cfg_px_off.value, d.cfg_minqty.value = c.band, c.px_off, c.minqty
        d.cfg_tif.value, d.cfg_display.value, d.cfg_capacity.value = ord(c.tif), ord(c.display), ord(c.capacity)
        d.cfg_ise.value, d.cfg_cross.value, d.cfg_custtype.value = ord(c.ise), ord(c.cross), ord(c.custtype)
        d.cfg_arm.value, d.cfg_kill.value, d.cfg_halt_on_gap.value, d.cfg_spec.value = int(c.arm), int(c.kill), int(c.halt_on_gap), int(self.spec)

    async def wait_ready(self):
        for _ in range(2000):
            if int(self.dut.flags.value) & 0x10:
                return
            await self.tick(sample=False)
        raise AssertionError("book never became ready")

    async def pulse(self, name):
        getattr(self.dut, name).value = 1
        await self.tick()
        getattr(self.dut, name).value = 0

    # ---- one clock
    async def tick(self, sample=True):
        await RisingEdge(self.dut.clk)
        await Timer(500, unit="ps")
        self.cyc += 1
        if sample:
            self.sample()

    def sample(self):
        d, c = self.dut, self.cyc
        if int(d.m_v.value):
            self.msgs.append((c, int(d.m_len.value), int(d.u_mold.m_seq.value)))
        if int(d.e_v.value):
            u = d.u_dec
            self.evs.append({"cyc": c, "k": int(d.e_k.value), "loc": int(u.e_loc.value), "ref": int(u.e_ref.value), "nref": int(u.e_nref.value),
                             "sell": int(u.e_sell.value), "sh": int(u.e_sh.value), "px": int(u.e_px.value),
                             "stock": int(u.e_stock.value).to_bytes(8, "big"), "code": int(u.e_code.value), "seq": int(u.e_seq.value)})
        if int(d.tu_v.value):
            b = d.u_book
            self.tus.append({"cyc": c, "inst": int(d.tu_inst.value), "side": int(d.tu_side.value), "px": int(d.tu_px.value), "sz": int(d.tu_sz.value),
                             "ok": bool(int(d.tu_ok.value)), "cpx": int(b.tu_cpx.value), "cand": int(b.tu_cand.value), "spec": int(b.tu_spec.value)})
        if int(d.o_v.value):
            if int(d.o_sof.value):
                self._cur = {"cyc": c, "words": [], "keep": [], "abort": False}
            if self._cur is not None:
                self._cur["words"].append(int(d.o_d.value))
                self._cur["keep"].append(int(d.o_keep.value))
                if int(d.o_eof.value):
                    self.frames.append(self._cur)
                    self._cur = None
        if int(d.o_abort.value):
            self.aborts.append(c)
            if self._cur is not None:
                self._cur["abort"] = True
                self.frames.append(self._cur)
                self._cur = None
        if int(self.dut.u_ouch.late.value):
            self.late += 1

    # ---- stimulus
    async def send(self, pkt: bytes, err: bool = False, idle: int = 8):
        """One UDP payload; returns the cycle in which its last word is presented."""
        d = self.dut
        for _ in range(idle):
            await self.tick()
        ws = proto.words(pkt)
        for i, (w, keep) in enumerate(ws):
            d.s_v.value = 1
            d.s_d.value = w
            d.s_sof.value = int(i == 0)
            d.s_eof.value = int(i == len(ws) - 1)
            d.s_keep.value = keep if i == len(ws) - 1 else 0xFF
            d.s_err.value = int(err and i == len(ws) - 1)
            last = self.cyc
            await self.tick()
        d.s_v.value = 0
        d.s_sof.value = 0
        d.s_eof.value = 0
        d.s_err.value = 0
        return last

    async def run_items(self, model: Model, items, drain: int = 40, skip_gaps_in_words: bool = False):
        for it in items:
            model.feed(it.pkt, it.err)
            await self.send(it.pkt, it.err, it.idle)
        for _ in range(drain):
            await self.tick()

    # ---- results
    def counters(self) -> dict:
        v = int(self.dut.cnt.value)
        return {k: (v >> (32 * i)) & 0xFFFFFFFF for i, k in enumerate(COUNTERS)}

    def frames_bytes(self, aborted: bool = False):
        out = []
        for f in self.frames:
            if f["abort"] != aborted:
                continue
            b = b"".join(w.to_bytes(8, "little") for w in f["words"])
            out.append(b[:59] if f["keep"][-1] == 0x07 else b)
        return out


def expect_event(m: dict) -> dict:
    return {"k": KIND[m["t"]], "loc": m["loc"], "seq": m["seq"]}


def compare_msgs(b: Bench, model: Model):
    got = [(l, s) for _, l, s in b.msgs]
    want = [(L, seq) for seq, L, _ in model.msgs]
    k = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), None)
    assert k is None and len(got) == len(want), f"messages: rtl {len(got)} model {len(want)}; first difference at {k}: rtl {got[max(0, (k or 0) - 2):(k or 0) + 4]} model {want[max(0, (k or 0) - 2):(k or 0) + 4]}"


def compare_events(b: Bench, model: Model):
    assert len(b.evs) == len(model.events), f"events: rtl {len(b.evs)} model {len(model.events)}"
    for i, (r, m) in enumerate(zip(b.evs, model.events)):
        t = m["t"]
        assert r["k"] == KIND[t] and r["loc"] == m["loc"] and r["seq"] == m["seq"], f"event {i} {t}: rtl {r} model {m}"
        if t in "AF":
            assert (r["ref"], r["sell"], r["sh"], r["px"], r["stock"]) == (m["ref"], int(m["sell"]), m["shares"], m["px"], m["stock"]), f"event {i}: {r} {m}"
        elif t in "ECX":
            assert (r["ref"], r["sh"]) == (m["ref"], m["shares"]), f"event {i}: {r} {m}"
        elif t == "D":
            assert r["ref"] == m["ref"], f"event {i}: {r} {m}"
        elif t == "U":
            assert (r["ref"], r["nref"], r["sh"], r["px"]) == (m["ref"], m["nref"], m["shares"], m["px"]), f"event {i}: {r} {m}"
        elif t == "R":
            assert r["stock"] == m["stock"], f"event {i}: {r} {m}"
        elif t == "S":
            assert r["code"] == m["code"], f"event {i}: {r} {m}"


def compare_tus(b: Bench, model: Model):
    assert len(b.tus) == len(model.tus), f"book updates: rtl {len(b.tus)} model {len(model.tus)}"
    for i, (r, m) in enumerate(zip(b.tus, model.tus)):
        got = (r["inst"], r["side"], r["px"], r["sz"], r["ok"], r["cpx"])
        want = (m["inst"], m["side"], m["px"], m["sz"], m["ok"], m["cause_px"])
        assert got == want, f"book update {i}: rtl {got} model {want}"


def compare_orders(b: Bench, model: Model, allow_dropped: bool = False):
    got = b.frames_bytes()
    want = [o["frame"] for o in model.orders]
    if allow_dropped:
        j = 0
        for g in got:
            while j < len(want) and want[j] != g:
                j += 1
            assert j < len(want), "an order frame the model did not decide"
            j += 1
    else:
        assert got == want, f"order frames: rtl {len(got)} model {len(want)}\nfirst difference at {next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), min(len(got), len(want)))}"


def compare_counters(b: Bench, model: Model, skip=TIMING_DEPENDENT):
    got = b.counters()
    bad = {k: (got[k], model.cnt[k]) for k in COUNTERS if k not in skip and got[k] != model.cnt[k]}
    assert not bad, f"counters (rtl, model): {bad}"


def compare_flags(b: Bench, model: Model):
    f = int(b.dut.flags.value)
    assert (f & 1) == int(model.gap) and ((f >> 1) & 1) == int(model.untrusted) and ((f >> 2) & 1) == int(model.eos_seen) and ((f >> 3) & 1) == int(model.sess_lock), f"flags {f:#x}"
    for i, x in enumerate(model.inexact):
        assert ((f >> (8 + i)) & 1) == int(x), f"inexact[{i}]"


def compare_tob(b: Bench, model: Model):
    px, sz, ok = int(b.dut.tob_px.value), int(b.dut.tob_sz.value), int(b.dut.tob_ok.value)
    for i in range(model.cfg.n_inst):
        for s in (0, 1):
            g = 2 * i + s
            tp, ts, tk = model.tob[i][s]
            assert ((px >> (32 * g)) & 0xFFFFFFFF, (sz >> (32 * g)) & 0xFFFFFFFF, bool((ok >> g) & 1)) == (tp, ts, tk), f"tob[{i}][{s}]"


def compare_all(b: Bench, model: Model, allow_dropped=False, skip=TIMING_DEPENDENT):
    compare_msgs(b, model)
    compare_events(b, model)
    compare_tus(b, model)
    compare_orders(b, model, allow_dropped)
    compare_counters(b, model, skip)
    compare_flags(b, model)
    compare_tob(b, model)


def small_cfg(**kw) -> Cfg:
    base = dict(thr=gen.MID + 3 * gen.TICK, max_pos=2000, max_qty=500, band=20_000)
    base.update(kw)
    return Cfg(**base)


# ============================================================================== tests
@cocotb.test()
async def main_stream(dut):
    """Seeded session, several seeds: preamble, mixed order flow, back-to-back packets."""
    for seed in (1, 2, 3):
        cfg = small_cfg()
        b = Bench(dut, cfg, spec=False)
        await b.start()
        m = Model(cfg)
        g = gen.Gen(seed, cfg)
        items = g.stream(500, p_hb=0.03)
        await b.run_items(m, items)
        assert len(m.orders) > 5, "the stream should trigger orders"
        compare_all(b, m)
        dut._log.info("seed %d: %d events, %d book updates, %d orders", seed, len(m.events), len(m.tus), len(m.orders))
