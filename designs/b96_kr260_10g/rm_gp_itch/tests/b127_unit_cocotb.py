"""cocotb bench of the new blocks of build rm_gp_itch with the REAL mac64_rx and mac64_tx (sim/itch_unit.sv, Icarus), against brief 110's model (brief 127).

XGMII words go into mac64_rx (frames built by host/itch_host.py, bubbles and gaps added), the ITCH path runs, order frames come out of mac64_tx as XGMII words and are parsed with the
independent reference parser of designs/b96_kr260_10g/model/pcs.py. Checks: the payload the adapter hands to the Mold receiver, the late verdicts, every counter of brief 110's path
against the model, every order frame byte for byte, the poison of orders from bad frames, the replay source, and the latency in clocks (B127_RECORD=<dir> writes it).
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import COUNTERS, Cfg, Model
from designs.b96_kr260_10g.model import pcs
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H

PERIOD_PS = 6206
NCW, NSW = 32, 96
C = dict(CTRL=0, THR=1, QTY=2, MAXQTY=3, MAXPOS=4, BAND=5, PXOFF=6, MINQTY=7, ORDF0=8, ORDF1=9, WATCH=10, FEEDIP=18, FEEDPORT=19, TCPSEQ=20, TCPACK=21, CMD=22, RPW=23, RPWLO=24,
         RPWHI=25, CAPADDR=26, TCPFA=27, TCPFD=28)
S_ITCH, S_US, S_O = 0, 45, 60
US_NAMES = ["frames", "fwd", "drop_off", "drop_mac", "drop_type", "drop_frag", "drop_proto", "drop_dip", "drop_port", "drop_len", "drop_ipck", "bad_fcs", "cut", "orphan", "cap_n"]
ORD_NAMES = ["sent", "pz_abort", "pz_bad", "pz_strict", "unv", "drop", "ofl", "pz_unres", "late"]
TIMING_DEPENDENT = ("spec", "abort", "late_abort", "rej_busy")
REC: dict = {}


def cfg_vec(my_mac=H.DEFAULTS["my_mac"], venue_mac=H.DEFAULTS["venue_mac"], my_ip="192.168.58.10", venue_ip="192.168.58.15", sport=5800, port_order=5801) -> int:
    f = [(int.from_bytes(my_mac, "little"), 48), (int.from_bytes(venue_mac, "little"), 48), (int.from_bytes(H.ip_bytes(my_ip), "big"), 32), (int.from_bytes(H.ip_bytes(venue_ip), "big"), 32),
         (sport, 16), (5800, 16), (port_order, 16), (5802, 16), (9975, 32), (100, 32), (0, 1), (0, 1), (0, 1), (2, 2), (66, 16), (1, 16), (9950, 32), (2000, 32), (1, 32)]
    v, sh = 0, 0
    for val, w in f:
        v |= val << sh
        sh += w
    assert sh == 421
    return v


class Unit:
    def __init__(self, dut, pause=True):
        self.dut = dut
        self.cyc = 0
        self.cw = [0] * NCW
        self.cmd_seq = 0
        self.rpw_seq = 0
        self.log: list[dict] = []
        self.wire: list[tuple[int, int]] = []
        self.wire_cyc: list[int] = []

    async def start(self, cfgd: Cfg | None = None, feed_ip="192.168.58.10", feed_port=5810, ctrl=None, **kw):
        d = self.dut
        t = getattr(d, "_b127_clk", None)
        if t is None or t.done():
            d._b127_clk = cocotb.start_soon(Clock(d.clk, PERIOD_PS, unit="ps").start())
        d.x_v.value = 0; d.x_d.value = 0; d.x_c.value = 0xFF
        d.cfg.value = cfg_vec(**kw)
        self.set_model_cfg(cfgd or Cfg(), feed_ip, feed_port, ctrl)
        d.rst.value = 1
        for _ in range(5):
            await self.tick(sample=False)
        d.rst.value = 0
        for _ in range(3):
            await self.tick(sample=False)
        await self.wait_ready()

    def set_model_cfg(self, c: Cfg, feed_ip="192.168.58.10", feed_port=5810, ctrl=None, strict=False):
        cw = self.cw
        cw[C["CTRL"]] = ctrl if ctrl is not None else (1 | (int(c.arm) << 1) | (int(c.kill) << 2) | (int(getattr(self, "spec", False)) << 3) | (int(c.halt_on_gap) << 4) | (int(strict) << 5))
        cw[C["THR"]], cw[C["QTY"]], cw[C["MAXQTY"]], cw[C["MAXPOS"]], cw[C["BAND"]], cw[C["PXOFF"]], cw[C["MINQTY"]] = c.thr, c.qty, c.max_qty, c.max_pos, c.band, c.px_off, c.minqty
        cw[C["ORDF0"]] = ord(c.tif) | (ord(c.display) << 8) | (ord(c.capacity) << 16) | (ord(c.ise) << 24)
        cw[C["ORDF1"]] = ord(c.cross) | (ord(c.custtype) << 8)
        for i in range(4):
            w = int.from_bytes(proto.alpha(c.watch[i], 8), "big")
            cw[C["WATCH"] + 2 * i], cw[C["WATCH"] + 2 * i + 1] = w & 0xFFFFFFFF, w >> 32
        cw[C["FEEDIP"]] = int.from_bytes(H.ip_bytes(feed_ip), "big")
        cw[C["FEEDPORT"]] = feed_port
        cw[C["TCPSEQ"]], cw[C["TCPACK"]] = 1, 1
        self.model_cfg = c
        self.push_cfg()

    def push_cfg(self):
        v = 0
        for i, w in enumerate(self.cw):
            v |= (w & 0xFFFFFFFF) << (32 * i)
        v &= ~(0xFFFFFFFF << (32 * C["CMD"]))
        v |= (self.cmd_seq << 16) << (32 * C["CMD"]) | (self.cw[C["CMD"]] & 0xFFFF) << (32 * C["CMD"])
        v &= ~(0xFFFFFFFF << (32 * C["RPW"]))
        v |= ((self.rpw_seq << 16) | (self.cw[C["RPW"]] & 0xFF)) << (32 * C["RPW"])
        self.dut.cfg2.value = v

    async def command(self, bits: int):
        self.cw[C["CMD"]] = bits
        self.cmd_seq = (self.cmd_seq + 1) & 0xFF
        self.push_cfg()
        for _ in range(4):
            await self.tick()

    async def replay_write(self, addr: int, word: int):
        self.cw[C["RPW"]] = addr
        self.cw[C["RPWLO"]] = word & 0xFFFFFFFF
        self.cw[C["RPWHI"]] = word >> 32
        self.rpw_seq = (self.rpw_seq + 1) & 0xFF
        self.push_cfg()
        for _ in range(3):
            await self.tick()

    async def wait_ready(self):
        for _ in range(3000):
            f = self.stat_word(88)
            if f >= 0 and f & 0x10:
                return
            await self.tick(sample=False)
        raise AssertionError(f"book never became ready; X words: {[i for i in range(NSW) if self.stat_word(i) < 0]}")

    async def tick(self, sample=True):
        await RisingEdge(self.dut.clk)
        await Timer(500, unit="ps")
        self.cyc += 1
        if sample:
            self.sample()

    def stat_word(self, i: int) -> int:
        v = str(self.dut.stat2.value)[::-1]
        w = v[32 * i: 32 * i + 32][::-1]
        if any(c not in "01" for c in w):
            return -1
        return int(w, 2)

    def counters(self):
        itch = {n: self.stat_word(S_ITCH + i) for i, n in enumerate(COUNTERS)}
        us = {n: self.stat_word(S_US + i) for i, n in enumerate(US_NAMES)}
        od = {n: self.stat_word(S_O + i) for i, n in enumerate(ORD_NAMES)}
        return itch, us, od

    def sample(self):
        d, c = self.dut, self.cyc
        ip = d.u_ip
        rec = {"cyc": c}
        if int(d.u_mr.m_v.value):
            rec["m_v"] = (int(d.u_mr.m_d.value), int(d.u_mr.m_sof.value))
        if int(d.u_mr.m_end.value):
            rec["m_end"] = (int(d.u_mr.m_fcs_ok.value), int(d.u_mr.m_len.value))
        if int(d.u_mr.rx_sop.value):
            rec["rx_sop"] = 1
        if int(ip.s_v.value):
            rec["s"] = (int(ip.s_d.value), int(ip.s_sof.value), int(ip.s_eof.value), int(ip.s_keep.value))
        if int(ip.v_v.value):
            rec["v"] = int(ip.v_bad.value)
        if int(ip.u_it.go.value):
            rec["go"] = int(ip.u_it.go_spec.value)
        if int(ip.o_v.value):
            rec["o"] = (int(ip.o_d.value), int(ip.o_sof.value), int(ip.o_eof.value), int(ip.o_keep.value), int(ip.o_poison.value))
        if int(d.u_mx.ord_sop.value):
            rec["osop"] = 1
        if int(d.t_sop.value):
            rec["tsop"] = 1
        if int(d.adv.value):                    # the PCS takes a word only in the clocks adv is high (a pause repeats the MAC's output register)
            self.wire.append((int(d.t_d.value), int(d.t_c.value)))
            self.wire_cyc.append(c)
        if len(rec) > 1:
            self.log.append(rec)

    # ---- stimulus
    async def send(self, frames: list[dict], bubble=0.0, rng=None):
        """frames: dicts {frame, bad_fcs, lane4, gap (idle words after it)}. Words one a clock; a bubble (x_v low for a clock) with probability `bubble` inside a frame."""
        d = self.dut
        rng = rng or random.Random(1)
        for fr in frames:
            ws = H.xgmii_words(fr["frame"], lane4=fr.get("lane4", False), bad_fcs=fr.get("bad_fcs", False))
            for dd, cc in ws:
                while rng.random() < bubble:
                    d.x_v.value = 0
                    await self.tick()
                d.x_v.value = 1; d.x_d.value = dd; d.x_c.value = cc
                await self.tick()
            for _ in range(fr.get("gap", 3)):
                d.x_v.value = 1; d.x_d.value = H.IDLE_WORD[0]; d.x_c.value = H.IDLE_WORD[1]
                await self.tick()
        d.x_v.value = 1; d.x_d.value = H.IDLE_WORD[0]; d.x_c.value = H.IDLE_WORD[1]

    async def idle(self, n):
        d = self.dut
        d.x_v.value = 1; d.x_d.value = H.IDLE_WORD[0]; d.x_c.value = H.IDLE_WORD[1]
        for _ in range(n):
            await self.tick()

    # ---- results
    def stripped_packets(self):
        pk, cur = [], None
        for r in self.log:
            if "s" in r:
                dd, sof, eof, keep = r["s"]
                if sof:
                    cur = bytearray()
                if cur is None:
                    continue
                n = 8 if not eof else bin(keep).count("1")
                cur += dd.to_bytes(8, "little")[:n]
                if eof:
                    pk.append((r["cyc"], bytes(cur)))
                    cur = None
        return pk

    def verdicts(self):
        return [(r["cyc"], r["v"]) for r in self.log if "v" in r]

    def wire_frames(self):
        words = [w for w in self.wire]
        out = []
        for f in pcs.parse_xgmii(words):
            if "data" in f:
                out.append((f["data"], f.get("fcs_ok"), f.get("start_lane")))
        return out


def mk_frame(payload: bytes, **kw):
    args = dict(dst_mac=H.DEFAULTS["my_mac"], src_mac=H.DEFAULTS["venue_mac"], src_ip="192.168.58.15", dst_ip="192.168.58.10", sport=26000, dport=5810)
    args.update(kw)
    return H.eth_ip_udp(payload, **args)


def build_session(seed, n_msgs, **gkw):
    cfg = Cfg(thr=gen.MID - 300, max_pos=10**6, max_qty=1000)
    g = gen.Gen(seed, cfg)
    items = g.stream(n_msgs, **gkw)
    return cfg, items


@cocotb.test()
async def strip_payload_and_verdict(dut):
    """Each frame length and alignment: the payload the adapter hands on equals the UDP payload, and the verdict is good; bad FCS frames give a bad verdict; non-matching frames are
    counted by their first failing check and not forwarded."""
    u = Unit(dut)
    await u.start()
    rng = random.Random(5)
    frames, want = [], []
    for n in list(range(21, 120)) + [200, 333, 1000]:
        pl = bytes(rng.randrange(256) for _ in range(n))
        frames.append({"frame": mk_frame(pl), "gap": rng.randrange(2, 5), "lane4": bool(n % 2)})
        want.append((pl, 0))
    bad = bytes(rng.randrange(256) for _ in range(77))
    frames.append({"frame": mk_frame(bad), "bad_fcs": True, "gap": 3})
    want.append((bad, 1))
    # frames that must be dropped, one of each class
    drops = [("mac", mk_frame(b"x" * 40, dst_mac=bytes.fromhex("02aabbccddee"))),
             ("type", mk_frame(b"x" * 40)[:12] + b"\x86\xdd" + mk_frame(b"x" * 40)[14:]),
             ("port", mk_frame(b"x" * 40, dport=9)),
             ("dip", mk_frame(b"x" * 40, dst_ip="192.168.58.99")),
             ("proto", mk_frame(b"x" * 40)[:23] + b"\x06" + mk_frame(b"x" * 40)[24:])]
    for _, f in drops:
        frames.append({"frame": f, "gap": 3})
    await u.send(frames, bubble=0.0)
    await u.idle(40)
    pk = u.stripped_packets()
    vd = u.verdicts()
    assert len(pk) == len(want), (len(pk), len(want))
    for (cyc, got), (pl, _) in zip(pk, want):
        assert got == pl, (len(got), len(pl))
    assert [b for _, b in vd] == [b for _, b in want], vd
    _, us, _ = u.counters()
    assert us["fwd"] == len(want) and us["frames"] == len(want) + len(drops), us
    assert us["bad_fcs"] == 1 and us["drop_mac"] == 1 and us["drop_type"] == 1 and us["drop_port"] == 1 and us["drop_dip"] == 1 and us["drop_proto"] == 1, us
    assert us["orphan"] == 0


@cocotb.test()
async def strip_with_bubbles(dut):
    """The same with one-clock bubbles inside frames (the elastic buffer's read cadence)."""
    u = Unit(dut)
    await u.start()
    rng = random.Random(9)
    frames, want = [], []
    for n in range(21, 90):
        pl = bytes(rng.randrange(256) for _ in range(n))
        frames.append({"frame": mk_frame(pl), "gap": rng.randrange(2, 5), "lane4": bool(rng.getrandbits(1)), "bad_fcs": n % 17 == 0})
        want.append((pl, int(n % 17 == 0)))
    await u.send(frames, bubble=0.08, rng=rng)
    await u.idle(40)
    pk = u.stripped_packets()
    assert [p for _, p in pk] == [p for p, _ in want]
    assert [b for _, b in u.verdicts()] == [b for _, b in want]


def expected_order_frames(model: Model, seq0=1):
    out = []
    seq = seq0
    for o in model.orders:
        out.append((o["frame"], seq))
        seq += 59
    return out


def order_check_kw(seq):
    d = H.DEFAULTS
    return dict(my_mac=d["my_mac"], venue_mac=d["venue_mac"], my_ip=d["my_ip"], venue_ip=d["venue_ip"], sport=d["sport"], dport=d["order_port"], seq=seq, ack=1)


def latency_of(u: Unit, frames_pl: list[int]):
    """Per order: clocks from the in-word of the MAC that carries the last payload byte (X), the clock of the last payload word at the Mold receiver (T = s_eof), `go`, to the order's
    start strobe in the MAC (preamble word in its output register). Single-message packets only: T is then the message's last byte."""
    rows = []
    logs = u.log
    # per frame: cycles of the in-words
    frames, cur = [], None
    for r in logs:
        if "m_v" in r:
            d, sof = r["m_v"]
            if sof:
                cur = []
                frames.append(cur)
            if cur is not None:
                cur.append(r["cyc"])
    eofs = [r["cyc"] for r in logs if "s" in r and r["s"][2]]
    gos = [r for r in logs if "go" in r]
    sops = [r["cyc"] for r in logs if "osop" in r]
    return frames, eofs, gos, sops


@cocotb.test()
async def session_vs_model(dut):
    """Seeded sessions through the whole chain (frames, adapter, Mold, ITCH, book, risk, order frames on the wire) against brief 110's model: every counter, every order frame byte for byte
    (with the stand-in header), speculation off and on. One message a packet, so that candidates are further apart than an order frame."""
    for seed, spec in ((1, False), (2, True), (3, False), (4, True)):
        cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=2000, max_qty=500, band=20_000)
        u = Unit(dut)
        u.spec = spec
        await u.start(cfg)
        await u.command(1 << 6)           # TCP_LOAD: the first segment's sequence number is IT_TCP_SEQ
        m = Model(cfg)
        g = gen.Gen(seed, cfg)
        items = g.stream(260, max_per_pkt=1, p_hb=0.03, p_gap=0.0, p_dup=0.02, p_overlap=0.0)
        rng = random.Random(seed)
        frames = []
        for it in items:
            m.feed(it.pkt, False)
            frames.append({"frame": mk_frame(it.pkt, ident=rng.randrange(65536)), "gap": 14 + rng.randrange(0, 6), "lane4": bool(rng.getrandbits(1))})
        await u.send(frames, bubble=0.02, rng=rng)
        await u.idle(60)
        assert len(m.orders) >= 4, len(m.orders)
        wf = u.wire_frames()
        good = [f for f in wf if f[1]]
        poisoned = [f for f in wf if not f[1]]
        assert len(good) == len(m.orders), (len(good), len(m.orders), len(poisoned))
        for k, ((data, fcs_ok, lane), (exp, seq)) in enumerate(zip(good, expected_order_frames(m))):
            prob = H.check_order_frame(data, exp, **order_check_kw(seq))
            assert not prob, f"order {k}: {prob}"
        itch, us, od = u.counters()
        bad = {k: (itch[k], m.cnt[k]) for k in COUNTERS if k not in TIMING_DEPENDENT and itch[k] != m.cnt[k]}
        assert not bad, f"counters (rtl, model): {bad}"
        assert us["fwd"] == len(items) and us["frames"] == len(items) and us["orphan"] == 0, us
        assert od["sent"] == len(m.orders) and od["drop"] == 0 and od["pz_bad"] == 0 and od["pz_strict"] == 0 and od["pz_unres"] == 0 and od["late"] == 0, od
        assert len(poisoned) == od["pz_abort"] == itch["abort"] and (spec or not poisoned), (len(poisoned), od, itch["abort"])
        dut._log.info("seed %d spec %s: %d packets, %d orders, counters equal, order frames byte exact", seed, spec, len(items), len(m.orders))
        if spec:
            assert itch["spec"] > 0
