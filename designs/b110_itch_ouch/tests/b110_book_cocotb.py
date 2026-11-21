"""cocotb bench of book_core alone (brief 110): decoded events straight into the book, at the highest rate the message sizes allow, against model/ref.py.

The whole-path bench cannot make a Replace wait in the book's two-entry queue (two order messages are never one clock apart behind a Replace on a
real wire: each is at least 21 bytes long), so the queue and the Replace's second slot are exercised here, where events can be offered on consecutive
clocks (never three in a row: the system's own limit, section 3 of the datasheet)."""
from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b110_itch_ouch.model import proto
from designs.b110_itch_ouch.model.ref import Cfg, Model

KIND = {"A": 0, "F": 0, "E": 1, "C": 1, "X": 2, "D": 3, "U": 4, "R": 5, "S": 6}
BOOK_COUNTERS = ("unwatch", "omiss", "odup", "oovf", "lvovf", "lvmiss", "oover", "evdrop")


class Rig:
    def __init__(self, dut, cfg: Cfg):
        self.dut, self.cfg, self.cyc, self.tus = dut, cfg, 0, []

    async def tick(self):
        await RisingEdge(self.dut.clk)
        await Timer(500, unit="ps")
        self.cyc += 1
        d = self.dut
        if int(d.tu_v.value):
            self.tus.append((int(d.tu_inst.value), int(d.tu_side.value), int(d.tu_px.value), int(d.tu_sz.value), bool(int(d.tu_ok.value)), int(d.tu_cpx.value)))

    async def start(self):
        d, c = self.dut, self.cfg
        cocotb.start_soon(Clock(d.clk, 6206, unit="ps").start())
        for n in ("clr_book", "clr_cnt", "spec_allow", "gapblk_now", "e_v"):
            getattr(d, n).value = 0
        w = 0
        for i in range(c.n_inst):
            w |= int.from_bytes(proto.alpha(c.watch[i], 8), "big") << (64 * i)
        d.cfg_watch.value = w
        d.cfg_thr.value = 0
        d.rst.value = 1
        for _ in range(4):
            await self.tick()
        d.rst.value = 0
        for _ in range((1 << c.ord_aw) + 8):
            await self.tick()
        self.tus = []

    def drive(self, ev: dict):
        d = self.dut
        d.e_v.value = 1
        d.e_k.value = KIND[ev["t"]]
        d.e_loc.value = ev["loc"]
        d.e_ref.value = ev.get("ref", 0)
        d.e_nref.value = ev.get("nref", 0)
        d.e_sell.value = int(ev.get("sell", False))
        d.e_sh.value = ev.get("shares", 0)
        d.e_px.value = ev.get("px", 0)
        d.e_stock.value = int.from_bytes(ev.get("stock", b"\0" * 8), "big")
        d.e_code.value = ev.get("code", 0)

    async def send(self, evs: list[tuple[int, dict]]):
        """(idle clocks before, event): events on consecutive clocks when idle is 0."""
        for idle, ev in evs:
            for _ in range(idle):
                self.dut.e_v.value = 0
                await self.tick()
            self.drive(ev)
            await self.tick()
        self.dut.e_v.value = 0
        for _ in range(20):
            await self.tick()


def make_events(cfg: Cfg, seed: int, n: int, p_replace: float) -> list[dict]:
    r = random.Random(seed)
    ev = [{"t": "R", "loc": 10 + i, "stock": proto.alpha(cfg.watch[i], 8)} for i in range(cfg.n_inst)]
    live: dict[int, dict] = {}
    ref = 100
    mid = 1_000_000
    for _ in range(n):
        x = r.random()
        if x < 0.35 or len(live) < 3:
            ref += r.randrange(1, 3)
            i = r.randrange(cfg.n_inst)
            sell = r.random() < 0.5
            px = mid + 100 * r.randrange(1, cfg.levels - 1) * (1 if sell else -1)
            sh = r.choice([100, 200, 300])
            live[ref] = {"loc": 10 + i, "sell": sell, "px": px, "rem": sh}
            ev.append({"t": "A", "loc": 10 + i, "ref": ref, "sell": sell, "shares": sh, "px": px})
        elif x < 0.35 + p_replace:
            old = r.choice(list(live))
            o = live.pop(old)
            ref += r.randrange(1, 3)
            px = mid + 100 * r.randrange(1, cfg.levels - 1) * (1 if o["sell"] else -1)
            live[ref] = {**o, "px": px, "rem": 150}
            ev.append({"t": "U", "loc": o["loc"], "ref": old, "nref": ref, "shares": 150, "px": px})
        elif x < 0.80:
            old = r.choice(list(live))
            live.pop(old)
            ev.append({"t": "D", "loc": live_loc(ev, old), "ref": old})
        elif x < 0.90:
            old = r.choice(list(live))
            ev.append({"t": "X", "loc": live[old]["loc"], "ref": old, "shares": 40})
            live[old]["rem"] -= 40
            if live[old]["rem"] <= 0:
                live.pop(old)
        else:
            ev.append({"t": "D", "loc": 10, "ref": 9_000_000 + r.randrange(100)})      # an unknown reference
    return ev


def live_loc(evs: list[dict], ref: int) -> int:
    for e in reversed(evs):
        if e.get("ref") == ref and e["t"] == "A" or e.get("nref") == ref and e["t"] == "U":
            return e["loc"]
    return 10


def gaps(seed: int, n: int) -> list[int]:
    """Idle clocks before each event: 0, 1, 2 or 3, never three events on consecutive clocks (two zeros in a row at most)."""
    r = random.Random(seed)
    out, zeros = [], 0
    for _ in range(n):
        g = r.choice([0, 0, 1, 2, 3])
        if g == 0 and zeros >= 1:
            g = r.choice([1, 2])
        zeros = zeros + 1 if g == 0 else 0
        out.append(g)
    return out


@cocotb.test()
async def queue_and_replace(dut):
    """Events on consecutive clocks, many of them Replaces: every update record, every counter and the top-of-book registers equal the model's."""
    for seed, p_rep in ((1, 0.25), (2, 0.40), (3, 0.10)):
        cfg = Cfg(n_inst=4, levels=8, ord_aw=8)
        rig = Rig(dut, cfg)
        await rig.start()
        model = Model(cfg)
        evs = make_events(cfg, seed, 400, p_rep)
        for e in evs:
            model.event(e)
        # the Stock Directory events go in with idle clocks, the rest at the highest allowed rate
        plan = [(2, e) for e in evs[:cfg.n_inst]] + list(zip(gaps(seed, len(evs) - cfg.n_inst), evs[cfg.n_inst:]))
        await rig.send(plan)
        want = [(t["inst"], t["side"], t["px"], t["sz"], t["ok"], t["cause_px"]) for t in model.tus]
        assert rig.tus == want, f"seed {seed}: {len(rig.tus)} updates against {len(want)}"
        cnt = int(dut.cnt.value)
        got = {k: (cnt >> (32 * i)) & 0xFFFFFFFF for i, k in enumerate(BOOK_COUNTERS)}
        assert got == {k: model.cnt[k] for k in BOOK_COUNTERS}, (got, {k: model.cnt[k] for k in BOOK_COUNTERS})
        assert got["evdrop"] == 0
        px, sz, ok = int(dut.tob_px.value), int(dut.tob_sz.value), int(dut.tob_ok.value)
        for i in range(cfg.n_inst):
            for s in (0, 1):
                g = 2 * i + s
                assert ((px >> (32 * g)) & 0xFFFFFFFF, (sz >> (32 * g)) & 0xFFFFFFFF, bool((ok >> g) & 1)) == model.tob[i][s], (i, s)
        assert sum(1 for e in evs if e["t"] == "U") > 20
