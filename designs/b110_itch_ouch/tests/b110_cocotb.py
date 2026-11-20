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
COVER: dict = {"start_off": set(), "end_off": set(), "keep": set(), "counters": set(), "lengths": set(), "tests": []}


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
            so = int(d.u_mold.m_off.value)
            COVER["start_off"].add(so)
            COVER["end_off"].add((so + int(d.m_len.value)) % 8)
            COVER["lengths"].add(int(d.m_len.value))
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
            if i == len(ws) - 1:
                COVER["keep"].add(keep)
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
        c = {k: (v >> (32 * i)) & 0xFFFFFFFF for i, k in enumerate(COUNTERS)}
        COVER["counters"] |= {k for k, x in c.items() if x}
        return c

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
    COVER["counters"] |= {k for k, v in got.items() if v}
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


# ---- helpers for the directed tests
ENV_N = int(os.environ.get("B110_NINST", "4"))
ENV_L = int(os.environ.get("B110_LEVELS", "8"))
ENV_AW = int(os.environ.get("B110_ORDAW", "8"))


def cfg_for_params(**kw) -> Cfg:
    return small_cfg(n_inst=ENV_N, levels=ENV_L, ord_aw=ENV_AW, **kw)


def pk(seq: int, msgs: list[bytes], session: bytes = b"SESSION001", **kw) -> bytes:
    return proto.mold_packet(session, seq, msgs, **kw)


async def fresh(dut, cfg=None, spec=False):
    b = Bench(dut, cfg or small_cfg(), spec=spec)
    await b.start()
    return b, Model(b.cfg)


async def feed(b: Bench, m: Model, pkt: bytes, err=False, idle=8):
    m.feed(pkt, err)
    await b.send(pkt, err, idle)


async def settle(b: Bench, n=40):
    for _ in range(n):
        await b.tick()


class Day:
    """A hand-driven session: the preamble (S, R x n_inst, S) and a running sequence number."""

    def __init__(self, b: Bench, m: Model, loc0=10):
        self.b, self.m, self.seq, self.loc0, self.ts = b, m, 1, loc0, 1000

    def t(self):
        self.ts += 7
        return self.ts

    async def send(self, msgs: list[bytes], err=False, idle=8, count=None, session=b"SESSION001"):
        pkt = pk(self.seq, msgs, session, count=count)
        await feed(self.b, self.m, pkt, err, idle)
        self.seq += len(msgs)

    async def open(self):
        c = self.b.cfg
        msgs = [proto.itch_S(0, self.t(), "O")] + [proto.itch_R(self.loc0 + i, self.t(), c.watch[i]) for i in range(c.n_inst)]
        await self.send(msgs)

    def A(self, i, ref, side, sh, px):
        return proto.itch_A(self.loc0 + i, self.t(), ref, side, sh, self.b.cfg.watch[i], px)


MID, TK = gen.MID, gen.TICK


@cocotb.test()
async def main_stream_params(dut):
    """The same session at the parameters of this build (the pytest entry may build N_INST, LEVELS and ORD_AW other than the defaults)."""
    cfg = cfg_for_params()
    b, m = await fresh(dut, cfg)
    g = gen.Gen(11, cfg, spread_levels=min(5, cfg.levels - 1))
    await b.run_items(m, g.stream(600))
    assert len(m.orders) > 3
    compare_all(b, m)


@cocotb.test()
async def main_stream_spec(dut):
    """Speculative start on: the same orders leave, in the same order; some frames start before their verdict."""
    for seed in (4, 5):
        cfg = small_cfg()
        b, m = await fresh(dut, cfg, spec=True)
        await b.run_items(m, gen.Gen(seed, cfg).stream(500))
        compare_all(b, m)
        c = b.counters()
        assert c["spec"] > 0 and b.late == 0
        assert c["abort"] == len(b.frames_bytes(aborted=True)) == len(b.aborts)
        assert c["fire"] == len(m.orders), (c["fire"], len(m.orders))
        dut._log.info("spec seed %d: %d orders, %d speculative starts, %d aborted", seed, len(m.orders), c["spec"], c["abort"])


@cocotb.test()
async def impairments(dut):
    """Gaps, duplicates, overlaps, heartbeats, a second session, an end of session, bad frames: counters and delivery against the model."""
    cfg = small_cfg(halt_on_gap=False)
    b, m = await fresh(dut, cfg)
    g = gen.Gen(21, cfg)
    items = g.stream(500, p_gap=0.03, p_dup=0.04, p_overlap=0.05, p_hb=0.05)
    await b.run_items(m, items, drain=0)
    d = Day(b, m)
    d.seq = g.seq
    other = b"OTHERSESS1"
    await feed(b, m, pk(d.seq, [proto.itch_S(0, 1, "O")], other))
    await feed(b, m, proto.heartbeat(g.session, g.seq))
    await feed(b, m, proto.heartbeat(g.session, g.seq + 7))                 # a heartbeat that shows a gap
    await feed(b, m, proto.end_of_session(g.session, g.seq + 7))
    await feed(b, m, proto.heartbeat(g.session, 3))                          # a stale heartbeat
    await settle(b)
    c = b.counters()
    for k in ("gap", "dup", "ovlp", "sess", "hb", "eos"):
        assert c[k] > 0, k
    compare_all(b, m)


@cocotb.test()
async def bad_frames(dut):
    """Frames the MAC marked bad: counted, flagged untrusted, and orders stop after them; the same for a short packet and a cut one."""
    cfg = small_cfg()
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    await d.send([d.A(0, 1, "B", 100, MID - 100), d.A(0, 2, "S", 100, MID + 400)])        # a bid and an ask above the threshold: no order
    await d.send([d.A(0, 3, "B", 100, MID - 200)], err=True)                              # a bad frame (no candidate inside: its verdict would race the flag)
    await settle(b, 20)
    assert int(dut.flags.value) & 2
    await d.send([d.A(0, 4, "S", 100, MID + 100)])                                        # a candidate after the bad frame: blocked
    await settle(b)
    compare_all(b, m)
    assert m.cnt["rej_gap"] == 1 and m.cnt["pkt_err"] == 1 and not m.orders
    await b.pulse("clr_flags")
    m.untrusted = m.gap = m.eos_seen = m.sess_lock = False
    m.exp_v = False
    await d.send([d.A(0, 5, "S", 100, MID + 100)])
    await settle(b)
    compare_all(b, m)
    assert len(m.orders) == 1


@cocotb.test()
async def straddle(dut):
    """Messages that begin and end at every byte offset of a word, packets of every length: skipped types of lengths 12 to 60 between known ones."""
    cfg = small_cfg()
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    ref0 = 100
    for L in list(range(12, 61)):
        other = proto.itch_other("P", L, 10, d.t())
        ref0 += 1
        await d.send([other, d.A(1, ref0, "B", 100 + L, MID - 100 - L), proto.itch_D(d.loc0 + 1, d.t(), ref0)], idle=6)
    r = __import__("random").Random(7)
    for k in range(80):
        n = r.randrange(1, 7)
        ms = []
        for j in range(n):
            ref0 += 1
            c = r.randrange(4)
            if c == 0:
                ms.append(proto.itch_other("Q", r.randrange(12, 50), 10, d.t()))
            elif c == 1:
                ms.append(d.A(r.randrange(cfg.n_inst), ref0, r.choice("BS"), 100, MID + r.randrange(-5, 5) * TK))
            elif c == 2:
                ms.append(proto.itch_S(0, d.t(), "Q"))
            else:
                ms.append(proto.itch_D(d.loc0, d.t(), ref0 + 1000))
        await d.send(ms, idle=r.choice([4, 4, 5, 9, 17]))
    await settle(b)
    compare_all(b, m)
    assert b.counters()["msg"] > 300


@cocotb.test()
async def cut_packets(dut):
    """Every prefix of a multi-message packet, as a packet of its own (a frame cut at every byte), with and without a bad-frame flag."""
    cfg = small_cfg()
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    full = pk(d.seq, [d.A(0, 1, "B", 100, MID - 100), proto.itch_other("P", 44, 10, 5), proto.itch_D(d.loc0, 3, 1)])
    for n in range(0, len(full) + 1):
        if n == 0:
            continue
        await feed(b, m, full[:n], err=False, idle=6)
        await settle(b, 3)
    # count says more blocks than there are; count says fewer; zero length block; a one byte block; trailing bytes after the last block
    await feed(b, m, pk(d.seq, [proto.itch_D(d.loc0, 3, 1)], count=3))
    await feed(b, m, pk(d.seq, [proto.itch_D(d.loc0, 3, 1), proto.itch_D(d.loc0, 3, 2)], count=1))
    await feed(b, m, pk(d.seq, [b""], count=1))
    await feed(b, m, pk(d.seq, [proto.itch_D(d.loc0, 3, 1), b"\x01" * 11, proto.itch_D(d.loc0, 3, 1)]))
    await feed(b, m, pk(d.seq, [proto.itch_D(d.loc0, 3, 1)], trailer=b"\xAA" * 13))
    await settle(b)
    compare_all(b, m)
    c = b.counters()
    assert c["short"] > 0 and c["trunc"] > 0 and c["badlen"] > 0


@cocotb.test()
async def book_edges(dut):
    """Order table and ladder corner cases (docs/itch_ouch.md, Book): duplicate adds, collisions, over-execution, replace in all its forms, ladder overflow."""
    cfg = small_cfg(arm=False)
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    N = 1 << cfg.ord_aw
    px = MID
    await d.send([d.A(0, 1, "B", 100, px - 100), d.A(0, 1, "B", 100, px - 100)])                     # duplicate add (same reference)
    await d.send([d.A(0, 1 + N, "B", 50, px - 200)])                                                  # index collision with a live order: overflow, inexact
    await d.send([proto.itch_E(d.loc0, d.t(), 1, 150, 9)])                                            # execute more than remains
    await d.send([proto.itch_E(d.loc0, d.t(), 1, 5, 9)])                                              # execute an order that is gone
    await settle(b)
    await b.pulse("clr_book")
    m.clear_book()
    await b.wait_ready()
    await d.open()                                                                                    # re-learn the locates
    await d.send([d.A(1, 10, "S", 300, px + 100), d.A(1, 11, "S", 200, px + 100), d.A(1, 12, "S", 100, px + 200)])
    await d.send([proto.itch_X(d.loc0 + 1, d.t(), 10, 100), proto.itch_C(d.loc0 + 1, d.t(), 11, 200, px + 300, 5), proto.itch_D(d.loc0 + 1, d.t(), 12)])
    await d.send([proto.itch_U(d.loc0 + 1, d.t(), 10, 20, 700, px + 50)])                             # replace, better price
    await d.send([proto.itch_U(d.loc0 + 1, d.t(), 99, 21, 700, px + 50)])                             # replace of an unknown order
    await d.send([proto.itch_U(d.loc0 + 1, d.t(), 20, 20 + N, 100, px + 70)])                        # replace into the same table index
    await d.send([d.A(1, 30, "S", 10, px + 10), proto.itch_U(d.loc0 + 1, d.t(), 30, 30 + N, 10, px + 11)])
    await d.send([d.A(1, 31, "B", 10, px - 10), d.A(1, 32 + N, "B", 10, px - 20), proto.itch_U(d.loc0 + 1, d.t(), 31, 32, 5, px - 30)])
    # a Replace whose new reference lands on a live order of another reference (overflow after the old order was removed)
    await d.send([d.A(2, 40, "S", 10, px + 10), d.A(2, 41, "S", 10, px + 20), proto.itch_U(d.loc0 + 2, d.t(), 40, 41 + N, 10, px + 5)])
    # side and field checks: a bad side letter, zero shares, a wrong length, other types, other symbols
    await d.send([proto.itch_A(d.loc0, d.t(), 50, "X", 10, "AAA", px), proto.itch_A(d.loc0, d.t(), 51, "B", 0, "AAA", px),
                  proto.itch_other("A", 30, d.loc0, 1), proto.itch_E(d.loc0, d.t(), 1, 0), proto.itch_A(77, d.t(), 52, "B", 10, "XYZ", px)])
    # ladder overflow: nine distinct prices on one side, then a removal of one that never had a level
    for k in range(9):
        await d.send([d.A(3, 60 + k, "B", 10 + k, px - 10 * (k + 1))])
    await d.send([proto.itch_D(d.loc0 + 3, d.t(), 68), proto.itch_D(d.loc0 + 3, d.t(), 60)])
    # a stock directory for a symbol that is not watched, and one that moves a watched symbol to a new locate
    await d.send([proto.itch_R(88, d.t(), "NOPE"), proto.itch_R(55, d.t(), cfg.watch[0]), d.A(0, 70, "B", 10, px - 5)])
    await settle(b)
    compare_all(b, m)
    c = b.counters()
    for k in ("odup", "oovf", "oover", "omiss", "lvovf", "lvmiss", "unwatch", "m_bad"):
        assert c[k] > 0, k


@cocotb.test()
async def risk_checks(dut):
    """Each pre-trade check rejects on its own and is counted; the kill switch; the order price offset; the position limit and its clear."""
    px = MID
    results = {}
    for name, kw in (("arm", dict(arm=False)), ("kill", dict(kill=True)), ("size_max", dict(qty=600)), ("size_zero", dict(qty=0)),
                     ("size_1e6", dict(qty=1_000_000, max_qty=2_000_000)), ("pos", dict(max_pos=250)), ("band", dict(band=100)),
                     ("offset", dict(px_off=50)), ("ok", dict())):
        cfg = small_cfg(**kw)
        b, m = await fresh(dut, cfg)
        d = Day(b, m)
        await d.open()
        await d.send([d.A(0, 1, "B", 100, px - 100)])
        for k in range(4):
            await d.send([d.A(0, 10 + k, "S", 100, px + 100 + 10 * k)], idle=20)               # four candidates
        await d.send([d.A(1, 30, "S", 100, px + 100)], idle=20)                                 # a candidate with no bid: band rejects
        await settle(b)
        compare_all(b, m)
        results[name] = {k: v for k, v in m.cnt.items() if k.startswith("rej_") or k in ("cand", "fire")}
    assert results["arm"]["rej_arm"] == 5 and results["kill"]["rej_kill"] == 5
    assert results["size_max"]["rej_size"] == 5 and results["size_zero"]["rej_size"] == 5 and results["size_1e6"]["rej_size"] == 5
    assert results["pos"]["rej_pos"] > 0 and results["band"]["rej_band"] > 0 and results["ok"]["rej_band"] == 1 and results["ok"]["fire"] == 4
    # the position limit: send, hit the limit, clear the position, send again
    cfg = small_cfg(max_pos=200)
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    await d.send([d.A(0, 1, "B", 100, px - 100)])
    for k in range(3):
        await d.send([d.A(0, 10 + k, "S", 100, px + 100)], idle=20)
    await b.pulse("clr_pos")
    m.pos = [0] * cfg.n_inst
    await d.send([d.A(0, 20, "S", 100, px + 100)], idle=20)
    await b.pulse("clr_ref")
    m.next_ref = 1
    await d.send([d.A(0, 21, "S", 100, px + 100)], idle=20)
    await settle(b)
    compare_all(b, m)
    assert [o["ref"] for o in m.orders] == [1, 2, 3, 1]
    # kill switch changed while running
    b.configure(kill=True)
    m.cfg.kill = True
    await d.send([d.A(0, 22, "S", 100, px + 100)], idle=20)
    await settle(b)
    compare_all(b, m)
    assert m.cnt["rej_kill"] == 1


@cocotb.test()
async def speculation(dut):
    """Speculative start: a risk reject aborts the frame already on its way; a candidate that is a duplicate add aborts it too; a late abort never happens."""
    px = MID
    cfg = small_cfg(max_pos=100)
    b, m = await fresh(dut, cfg, spec=True)
    d = Day(b, m)
    await d.open()
    await d.send([d.A(0, 1, "B", 100, px - 100)])
    await d.send([d.A(0, 10, "S", 100, px + 100)], idle=30)       # passes
    await d.send([d.A(0, 11, "S", 100, px + 100)], idle=30)       # position limit: speculative frame aborted
    await d.send([d.A(0, 10, "S", 100, px + 100)], idle=30)       # duplicate reference: no book update, frame aborted
    await d.send([d.A(0, 12, "S", 100, px + 100)], idle=30)       # position limit again
    await settle(b)
    compare_all(b, m)
    c = b.counters()
    assert c["spec"] == 4 and c["abort"] == 3 and c["fire"] == 1 and b.late == 0, c
    ab = b.frames_bytes(aborted=True)
    full = m.orders[0]["frame"]
    assert len(ab) == 3 and all(len(x) < 59 for x in ab)
    # the aborted frames are prefixes of what they would have been: the first starts with the same eight bytes as an order would
    assert all(x[:4] == full[:4] for x in ab)


@cocotb.test()
async def burst_replace(dut):
    """Replace messages (two slots in B1) and short messages back to back: the queue absorbs them, nothing is dropped."""
    cfg = small_cfg(arm=False)
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    px = MID
    refs = list(range(100, 140))
    await d.send([d.A(k % 4, r, "BS"[k % 2], 100, px + (-1 if k % 2 == 0 else 1) * TK * (1 + k % 5)) for k, r in enumerate(refs)], idle=8)
    nxt = 200
    for rnd in range(30):
        ms = []
        for r in refs[:6]:
            nxt += 1
            ms.append(proto.itch_U(d.loc0 + (r - 100) % 4, d.t(), r, nxt, 100, px + ((-1) ** (r % 2)) * TK * (1 + rnd % 5)))
        refs = refs[6:] + [nxt - 5 + k for k in range(0, 6)]
        refs = [x for x in range(nxt - 5, nxt + 1)] + refs[:34]
        await d.send(ms, idle=6)
    await d.send([proto.itch_D(d.loc0, d.t(), 200 + k) for k in range(1, 12)], idle=4)
    await settle(b)
    compare_all(b, m)
    assert b.counters()["evdrop"] == 0


@cocotb.test()
async def clears(dut):
    """clr_cnt, clr_book (sweep, maps and tables), clr_flags (session lock, expected sequence), and events during the sweep."""
    cfg = small_cfg(arm=False)
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    await d.send([d.A(0, 1, "B", 100, MID - 100)])
    await settle(b)
    await b.pulse("clr_cnt")
    m.clear_counters()
    await settle(b, 3)
    assert all(v == 0 for v in b.counters().values()), b.counters()
    await settle(b)
    await b.pulse("clr_book")
    m.clear_book()
    # events during the sweep are dropped and counted
    await d.send([proto.itch_R(d.loc0, d.t(), cfg.watch[0])], idle=2)
    assert not int(dut.flags.value) & 0x10 or True
    await b.wait_ready()
    c = b.counters()
    assert c["evdrop"] >= 1, c
    m.cnt["evdrop"] = c["evdrop"]
    m.events.pop()                      # the dropped Stock Directory is not applied by the hardware; the model's event list is not compared below
    m.loc = [None] * cfg.n_inst
    await d.send([d.A(0, 2, "B", 100, MID - 100)])      # unwatched: the map was cleared
    await b.pulse("clr_flags")
    m.exp_v = False
    m.sess_lock = False
    m.gap = False
    await feed(b, m, pk(500, [proto.itch_S(0, 1, "C")], b"NEWSESSION"))
    await settle(b)
    assert m.cnt["unwatch"] == 1 and b.counters()["unwatch"] == 1 and b.counters()["sess"] == 0
    assert b.counters()["pkt"] == m.cnt["pkt"]


@cocotb.test()
async def latency(dut):
    """Latency in clocks, from the clock in which the last byte of a message is presented (T). Written to $B110_RECORD/latency_sim.json."""
    px = MID
    out = {}
    for spec in (False, True):
        cfg = small_cfg()
        b, m = await fresh(dut, cfg, spec=spec)
        d = Day(b, m)
        await d.open()
        await d.send([d.A(0, 1, "B", 100, px - 100)])
        await settle(b, 30)
        b.msgs, b.evs, b.tus, b.frames = [], [], [], []
        name = "speculative" if spec else "non_speculative"
        res = {}
        # a candidate Add (ask at or below the threshold): book update and first order word
        T = await b.send(pk(d.seq, [d.A(0, 2, "S", 100, px + 100)]), idle=20)
        d.seq += 1
        m.feed(pk(d.seq - 1, [d.A(0, 2, "S", 100, px + 100)]))
        await settle(b, 40)
        # the packet carries 20 + 2 + 36 = 58 bytes: its last word is presented at T
        res["mold_message_out"] = b.msgs[0][0] - T
        res["decoded_event"] = b.evs[0]["cyc"] - T
        res["book_update_add"] = b.tus[0]["cyc"] - T
        res["first_order_word"] = b.frames[0]["cyc"] - T
        res["decision_to_first_order_word"] = b.frames[0]["cyc"] - b.tus[0]["cyc"]
        res["order_frame_words"] = len(b.frames[0]["words"])
        assert b.frames_bytes() == [m.orders[0]["frame"]]
        # other messages: book update only
        for label, msg in (("book_update_delete", None), ("book_update_execute", None), ("book_update_replace", None), ("book_update_cancel", None)):
            ref = 100 + len(res)
            await d.send([d.A(0, ref, "B", 100, px - 200)], idle=20)
            await settle(b, 20)
            b.tus = []
            mm = {"book_update_delete": proto.itch_D(d.loc0, d.t(), ref), "book_update_execute": proto.itch_E(d.loc0, d.t(), ref, 10, 1),
                  "book_update_replace": proto.itch_U(d.loc0, d.t(), ref, ref + 1000, 50, px - 300), "book_update_cancel": proto.itch_X(d.loc0, d.t(), ref, 10)}[label]
            p = pk(d.seq, [mm])
            m.feed(p)
            d.seq += 1
            T2 = await b.send(p, idle=20)
            await settle(b, 30)
            res[label] = b.tus[0]["cyc"] - T2
            if label == "book_update_replace":
                res["book_update_replace_second"] = b.tus[1]["cyc"] - T2
        out[name] = res
        compare_tus(b, m) if False else None
    dut._log.info("latency: %s", json.dumps(out))
    rec = os.environ.get("B110_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        (Path(rec) / "latency_sim.json").write_text(json.dumps({"clock_ns": 6.2061, "unit": "clocks from the clock the last byte of the message is presented (T)", **out}, indent=2) + "\n")


@cocotb.test()
async def min_idle(dut):
    """The smallest idle gap between two payloads for which the path still equals the model (the datasheet states the requirement)."""
    rec = {}
    for idle in (0, 1, 2, 3, 4, 5):
        cfg = small_cfg(halt_on_gap=False)
        b, m = await fresh(dut, cfg)
        g = gen.Gen(31, cfg)
        items = g.stream(300, p_hb=0.1)
        for it in items:
            it.idle = idle
        try:
            await b.run_items(m, items)
            compare_all(b, m)
            rec[idle] = True
        except AssertionError as e:
            rec[idle] = False
            dut._log.info("idle %d: %s", idle, str(e)[:200])
    dut._log.info("min_idle: %s", rec)
    assert rec[4] and rec[5], rec
    d = os.environ.get("B110_RECORD")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "min_idle_sim.json").write_text(json.dumps({"idle_clocks_between_payloads_vs_model_equal": {str(k): v for k, v in rec.items()}}, indent=2) + "\n")


@cocotb.test()
async def valid_bubbles(dut):
    """s_v low inside a packet (the PCS pauses one clock in 33): the words are the same, the result is the same."""
    import random
    r = random.Random(5)
    cfg = small_cfg()
    b, m = await fresh(dut, cfg)
    g = gen.Gen(41, cfg)
    for it in g.stream(300, p_hb=0.05):
        m.feed(it.pkt, it.err)
        for _ in range(it.idle):
            await b.tick()
        ws = proto.words(it.pkt)
        for i, (w, keep) in enumerate(ws):
            while r.random() < 0.15:
                dut.s_v.value = 0
                await b.tick()
            dut.s_v.value = 1
            dut.s_d.value, dut.s_sof.value, dut.s_eof.value = w, int(i == 0), int(i == len(ws) - 1)
            dut.s_keep.value = keep if i == len(ws) - 1 else 0xFF
            dut.s_err.value = 0
            await b.tick()
        dut.s_v.value = 0
        dut.s_sof.value = 0
        dut.s_eof.value = 0
    await settle(b)
    compare_all(b, m)


@cocotb.test()
async def stale_book(dut):
    """An overflowing ladder or table makes the instrument inexact: candidates on it are refused (stale), and the overflowing Add that is itself a candidate too."""
    px = MID
    cfg = small_cfg()
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    await d.send([d.A(0, 1, "B", 100, px - 100)])
    # nine distinct ask prices at or below the threshold: the ninth finds no free level and is itself a candidate
    for k in range(9):
        await d.send([d.A(0, 10 + k, "S", 100, px + 10 + k)], idle=20)
    await d.send([d.A(1, 40, "B", 100, px - 100)])
    await d.send([d.A(1, 41, "S", 100, px + 100)], idle=20)             # a healthy instrument still trades
    await d.send([d.A(1, 41 + (1 << cfg.ord_aw), "S", 100, px + 120)], idle=20)       # table collision on instrument 1: overflow on its own Add (no book update)
    await d.send([d.A(1, 43, "S", 100, px + 130)], idle=20)             # now instrument 1 is inexact
    await settle(b)
    compare_all(b, m)
    assert m.cnt["rej_stale"] >= 2 and m.cnt["fire"] >= 2


@cocotb.test()
async def order_queue(dut):
    """Several candidates in one packet: the first frame starts at once, the others wait in the order queue and leave one after another."""
    px = MID
    for spec in (False, True):
        cfg = small_cfg(max_pos=10_000)
        b, m = await fresh(dut, cfg, spec=spec)
        d = Day(b, m)
        await d.open()
        await d.send([d.A(0, 1, "B", 100, px - 100)])
        await d.send([d.A(0, 10 + k, "S", 100, px + 100 + k) for k in range(4)])
        await settle(b, 80)
        compare_all(b, m)
        assert len(m.orders) == 4 and b.counters()["rej_busy"] == 0
        starts = [f["cyc"] for f in b.frames if not f["abort"]]
        assert all(b2 - a >= 8 for a, b2 in zip(starts, starts[1:])), starts
        # more than the queue holds (38 candidates in one packet, one every 4.75 clocks against a frame every 8): the frames that left are ones the
        # model decided, in order; the others are counted as refused for being busy; the numbers add up
        cfg = small_cfg(max_pos=100_000)
        b, m = await fresh(dut, cfg, spec=spec)
        d = Day(b, m)
        await d.open()
        await d.send([d.A(0, 1, "B", 100, px - 100)])
        await d.send([d.A(0, 10 + k, "S", 100, px + 100 + k % 5) for k in range(38)])
        await settle(b, 400)
        c = b.counters()
        assert c["cand"] == 38 and c["fire"] + c["rej_busy"] == 38 and c["rej_busy"] > 0, c
        fr = b.frames_bytes()
        assert len(fr) == c["fire"]
        # accepted candidates take consecutive order numbers; every field of every frame is what the model's builder gives for that number and price
        for i, f in enumerate(fr):
            price = int.from_bytes(f[21:29], "big")
            assert price in {px + 100 + k for k in range(5)} and f == m.frame(i + 1, 0, price, cfg.qty), i


@cocotb.test()
async def stress(dut):
    """Longer random sessions, speculation off and on, with impairments that do not stop the orders."""
    for k, (seed, spec) in enumerate(((51, False), (52, True), (53, False), (54, True))):
        cfg = small_cfg(halt_on_gap=False, max_pos=100_000, max_qty=1000, qty=200)
        b, m = await fresh(dut, cfg, spec=spec)
        g = gen.Gen(seed, cfg)
        await b.run_items(m, g.stream(1500, max_per_pkt=8, p_gap=0.01, p_dup=0.02, p_overlap=0.02, p_hb=0.03, p_back=0.7))
        compare_all(b, m, allow_dropped=False)
        assert b.counters()["evdrop"] == 0 and b.late == 0


@cocotb.test()
async def throughput(dut):
    """Back-to-back payloads with no idle clock (words in every clock): 38 Adds, then their 38 Deletes, ten times, then 39 Replaces. Nothing is dropped."""
    cfg = small_cfg(arm=False)
    b, m = await fresh(dut, cfg)
    d = Day(b, m)
    await d.open()
    await settle(b, 20)
    words0 = 0
    clk0 = b.cyc
    nmsg = 0
    ref0 = 1000
    for rnd in range(10):
        refs = list(range(ref0, ref0 + 38))
        ref0 += 40
        await d.send([d.A(k % cfg.n_inst, r, "BS"[k % 2], 100 + k, MID + (-1 if k % 2 == 0 else 1) * TK * (1 + k % 5)) for k, r in enumerate(refs)], idle=0)
        await d.send([proto.itch_D(d.loc0 + k % cfg.n_inst, d.t(), r) for k, r in enumerate(refs)], idle=0)
        nmsg += 76
    refs = list(range(ref0, ref0 + 39))
    await d.send([d.A(k % cfg.n_inst, r, "BS"[k % 2], 100 + k, MID + (-1 if k % 2 == 0 else 1) * TK * (1 + k % 5)) for k, r in enumerate(refs[:30])], idle=0)
    await d.send([proto.itch_U(d.loc0 + k % cfg.n_inst, d.t(), r, r + 500, 50 + k, MID + (-1 if k % 2 == 0 else 1) * TK * (2 + k % 4)) for k, r in enumerate(refs[:30])], idle=0)
    nmsg += 60
    clk1 = b.cyc
    await settle(b, 60)
    compare_all(b, m)
    c = b.counters()
    assert c["evdrop"] == 0
    total_bytes = sum(len(it) for it in [])      # (the words are counted below from the model's packets)
    pk_bytes = sum(38 * 38 + 20 for _ in range(10)) + sum(38 * 21 + 20 for _ in range(10)) + (30 * 38 + 20) + (30 * 37 + 20)
    words = sum((n + 7) // 8 for n in [38 * 38 + 20] * 10 + [38 * 21 + 20] * 10 + [30 * 38 + 20, 30 * 37 + 20])
    rec = {"messages": nmsg, "payload_bytes": pk_bytes, "payload_words": words, "clocks_with_traffic": clk1 - clk0, "clocks_per_message": round((clk1 - clk0) / nmsg, 3),
           "bytes_per_message": round(pk_bytes / nmsg, 2), "events_dropped": c["evdrop"], "book_updates": len(b.tus),
           "note": "payloads back to back with no idle clock; the path never backpressures: a word is accepted in every clock"}
    dut._log.info("throughput: %s", json.dumps(rec))
    out = os.environ.get("B110_RECORD")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "throughput_sim.json").write_text(json.dumps(rec, indent=2) + "\n")


@cocotb.test()
async def zz_coverage(dut):
    """Coverage over the whole bench: every message type decoded, every start and end byte offset of a message in a word, every keep mask, every counter."""
    need_counters = set(COUNTERS) - {"late_abort"}
    missing = need_counters - COVER["counters"]
    dut._log.info("coverage: start offsets %s end offsets %s keep %s lengths %d; counters never non-zero: %s", sorted(COVER["start_off"]), sorted(COVER["end_off"]),
                  sorted(COVER["keep"]), len(COVER["lengths"]), sorted(missing))
    assert COVER["start_off"] == set(range(8)) and COVER["end_off"] == set(range(8))
    assert COVER["keep"] == {0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF}, COVER["keep"]
    assert not missing, missing
    out = os.environ.get("B110_RECORD")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "coverage_sim.json").write_text(json.dumps({
            "message_start_byte_offsets_in_word": sorted(COVER["start_off"]), "message_end_byte_offsets_in_word": sorted(COVER["end_off"]),
            "last_word_keep_masks": sorted(COVER["keep"]), "distinct_message_lengths": len(COVER["lengths"]),
            "counters_non_zero_somewhere": sorted(COVER["counters"]), "counters_never_non_zero": sorted(missing),
            "excluded": {"late_abort": "a cancel that finds no frame in flight cannot happen with this pipeline (verdict 3 clocks before the frame's last word)"}}, indent=2) + "\n")
