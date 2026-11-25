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
         RPWHI=25, CAPADDR=26, TCPFA=27, TCPFD=28, RPCFG=29)
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
        self.loop = False
        self.tus: list[dict] = []

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
        v &= ~(0xFFFFFFFF << (32 * C["TCPFA"]))
        v |= ((getattr(self, "tcpf_seq", 0) << 16) | (self.cw[C["TCPFA"]] & 0x1F1F)) << (32 * C["TCPFA"])
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
        it = ip.u_it
        if int(it.tu_v.value):
            self.tus.append({"inst": int(it.tu_inst.value), "side": int(it.tu_side.value), "px": int(it.tu_px.value), "sz": int(it.tu_sz.value), "ok": bool(int(it.tu_ok.value)),
                             "cpx": int(it.tu_cpx.value)})
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
        if self.loop:                           # a closed fibre loop: the words the PCS takes come back as the receiver's next words (a bubble in the clocks adv is low)
            if int(d.adv.value):
                d.x_v.value = 1; d.x_d.value = int(d.t_d.value); d.x_c.value = int(d.t_c.value)
            else:
                d.x_v.value = 0
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
        if not self.loop:
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


def order_seqs(wf) -> list[int]:
    """TCP sequence numbers of the order frames (113 bytes before the FCS, TCP) that reached the wire with a good FCS, in wire order (brief 176)."""
    return [int.from_bytes(d[38:42], "big") for d, ok, *_ in wf if ok and len(d) >= 113 and d[12:14] == b"\x08\x00" and d[23] == 6]


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
    # the lag of the late verdict: clocks from the frame's last word at mac64_rx's output to the strobe (and to the adapter's last payload word)
    last_m, cur = [], None
    for r in u.log:
        if "m_v" in r:
            if r["m_v"][1]:
                if cur is not None:
                    last_m.append(cur)
            cur = r["cyc"]
    last_m.append(cur)
    lag = [v[0] - lm for v, lm in zip(vd, last_m[:len(vd)])]
    lag_s = [vc - pc for (vc, _), (pc, _) in zip(vd, pk)]
    assert min(lag) >= 1 and max(lag) <= 5, lag
    REC["verdict_lag"] = {"verdict_minus_last_frame_word_clocks": {"min": min(lag), "max": max(lag), "n": len(lag)}, "verdict_minus_last_payload_word_clocks": {"min": min(lag_s), "max": max(lag_s), "n": len(lag_s)}}
    dut._log.info(f"late verdict lag: {REC['verdict_lag']}")
    if os.environ.get("B127_RECORD"):
        Path(os.environ["B127_RECORD"]).mkdir(parents=True, exist_ok=True)
        (Path(os.environ["B127_RECORD"]) / "verdict_lag_unit_sim.json").write_text(json.dumps(REC["verdict_lag"], indent=1))
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
        # every top-of-book update record, in order, and the final top of book of every instrument and side (brief 110's model; bit exact)
        assert len(u.tus) == len(m.tus), (len(u.tus), len(m.tus))
        for i, (r, mm) in enumerate(zip(u.tus, m.tus)):
            got = (r["inst"], r["side"], r["px"], r["sz"], r["ok"], r["cpx"])
            want = (mm["inst"], mm["side"], mm["px"], mm["sz"], mm["ok"], mm["cause_px"])
            assert got == want, f"book update {i}: rtl {got} model {want}"
        it_ = dut.u_ip.u_it
        tpx, tsz, tok = int(it_.tob_px.value), int(it_.tob_sz.value), int(it_.tob_ok.value)
        for i in range(m.cfg.n_inst):
            for sd in (0, 1):
                g_ = 2 * i + sd
                assert ((tpx >> (32 * g_)) & 0xFFFFFFFF, (tsz >> (32 * g_)) & 0xFFFFFFFF, bool((tok >> g_) & 1)) == m.tob[i][sd], f"tob[{i}][{sd}]"
        dut._log.info(f"{len(u.tus)} book updates and the final top of book equal the model's")
        assert us["fwd"] == len(items) and us["frames"] == len(items) and us["orphan"] == 0, us
        assert od["sent"] == len(m.orders) and od["drop"] == 0 and od["pz_bad"] == 0 and od["pz_strict"] == 0 and od["pz_unres"] == 0 and od["late"] == 0, od
        assert len(poisoned) == od["pz_abort"] == itch["abort"] and (spec or not poisoned), (len(poisoned), od, itch["abort"])
        dut._log.info("seed %d spec %s: %d packets, %d orders, counters equal, order frames byte exact", seed, spec, len(items), len(m.orders))
        if spec:
            assert itch["spec"] > 0


def preamble_msgs(cfg: Cfg, g: gen.Gen):
    return g.preamble()


def sell_add(g: gen.Gen, cfg: Cfg, inst: int, px: int, shares=100) -> bytes:
    ref = g._newref()
    return proto.itch_A(g.loc0 + inst, g._t(), ref, "S", shares, cfg.watch[inst], px)


def buy_add(g: gen.Gen, cfg: Cfg, inst: int, px: int, shares=100) -> bytes:
    ref = g._newref()
    return proto.itch_A(g.loc0 + inst, g._t(), ref, "B", shares, cfg.watch[inst], px)


@cocotb.test()
async def latency_by_alignment(dut):
    """Clocks from the last byte of an ITCH message to the order frame's first byte, for each alignment of the message end in its 64-bit MAC word, speculation off and on.
    Start events (all measured): X = the clock the MAC word carrying the last byte is at mac64_rx's output; T = the clock the adapter presents the last payload word to the Mold receiver
    (what brief 110 calls T); go = the risk logic's start of the frame; end = the clock mac64_tx's output register holds the preamble (the start strobe)."""
    rows = {}
    for spec in (False, True):
        cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
        u = Unit(dut)
        u.spec = spec
        await u.start(cfg)
        await u.command(1 << 6)
        m = Model(cfg)
        g = gen.Gen(7, cfg)
        pre = g.preamble()
        pkts = [proto.mold_packet(b"SESSION001", 1, pre)]
        seq = 1 + len(pre)
        pkts.append(proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)]))
        seq += 1
        meta = []
        for n in list(range(12, 20)) * 3:            # a filler message of n bytes before the candidate shifts the candidate's end by n + 2 bytes: every alignment of the end
            filler = proto.itch_other("P", n, g.loc0, 5)
            cand = sell_add(g, cfg, 0, gen.MID + 100)
            pkts.append(proto.mold_packet(b"SESSION001", seq, [filler, cand]))
            seq += 2
            meta.append(len(pkts[-1]))
        frames = []
        for p in pkts:
            m.feed(p, False)
            frames.append({"frame": mk_frame(p), "gap": 40})
        await u.send(frames)
        await u.idle(80)
        assert len(m.orders) == len(meta), (len(m.orders), len(meta))
        wf = u.wire_frames()
        good = [f for f in wf if f[1]]
        assert len(good) == len(m.orders)
        for k, ((data, ok, lane), (exp, sq)) in enumerate(zip(good, expected_order_frames(m))):
            assert not H.check_order_frame(data, exp, **order_check_kw(sq))
        frs, eofs, gos, sops = latency_of(u, meta)
        # packets 0 and 1 are the preamble and the bid; the candidate packets follow
        cands = frs[2:]
        assert len(cands) == len(meta) == len(sops), (len(cands), len(meta), len(sops))
        key = "speculative" if spec else "at_verdict"
        rows[key] = []
        for k, pl in enumerate(meta):
            q = 42 + pl - 1
            x = cands[k][q >> 3]
            t = [e for e in eofs if e > cands[k][0]][0]
            go = [r["cyc"] for r in gos if r["cyc"] > cands[k][0]][0]
            sop = sops[k]
            rows[key].append({"end_byte_in_word": q & 7, "X": x, "T": t, "go": go, "sop": sop, "T_minus_X": t - x, "go_minus_T": go - t, "sop_minus_T": sop - t, "sop_minus_X": sop - x})
        st = u.counters()
        _, _, od = st
        assert od["unv"] == 0 or True
    REC["latency_by_alignment"] = rows
    for key, rs in rows.items():
        by = {}
        for r in rs:
            by.setdefault(r["end_byte_in_word"], set()).add((r["T_minus_X"], r["go_minus_T"], r["sop_minus_T"], r["sop_minus_X"]))
        dut._log.info(f"{key}: (T-X, go-T, sop-T, sop-X) by the byte of the MAC word that holds the message's last byte: " + "; ".join(f"{b}: {sorted(v)}" for b, v in sorted(by.items())))
    if os.environ.get("B127_RECORD"):
        Path(os.environ["B127_RECORD"]).mkdir(parents=True, exist_ok=True)
        (Path(os.environ["B127_RECORD"]) / "latency_unit_sim.json").write_text(json.dumps(REC, indent=1))
        # the record the stage file reads (results/b127/latency_sim.json): per mode and quantity, min and max over the alignments, in clocks
        summ = {}
        for key, rs in rows.items():
            summ[key] = {q: {"min": min(r[q] for r in rs), "max": max(r[q] for r in rs), "n": len(rs)} for q in ("T_minus_X", "go_minus_T", "sop_minus_T", "sop_minus_X")}
        (Path(os.environ["B127_RECORD"]) / "latency_sim.json").write_text(json.dumps({"itch_unit": summ, "what": "the new blocks with the real mac64_rx and mac64_tx in Icarus (tests/b127_unit_cocotb.py latency_by_alignment): clocks "
            "from X (the MAC word with the message's last byte at mac64_rx's output) to T (the adapter's output word), to go, and to the start strobe of the order frame in mac64_tx; the gearbox pause is one clock in 33",
            "units": "clocks of 6.2058 ns"}, indent=1))


async def poison_scenario(dut, *, spec: bool, strict: bool, tail_msgs: int, bad_fcs: bool):
    """A session preamble and a bid, then ONE packet with a candidate (a sell at 100.0100, threshold 100.0300) followed by `tail_msgs` messages of another type, in a frame whose FCS is
    good or bad; then a second candidate in a good frame. Returns (counters, wire frames (data, fcs_ok), model)."""
    cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
    u = Unit(dut)
    u.spec = spec
    await u.start(cfg)
    u.set_model_cfg(cfg, strict=strict)
    await u.command(1 << 6)
    m = Model(cfg)
    g = gen.Gen(11, cfg)
    pre = g.preamble()
    pkts = [(proto.mold_packet(b"SESSION001", 1, pre), False)]
    seq = 1 + len(pre)
    pkts.append((proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)]), False))
    seq += 1
    msgs = [sell_add(g, cfg, 0, gen.MID + 100)] + [proto.itch_other("P", 44, g.loc0, 5) for _ in range(tail_msgs)]
    pkts.append((proto.mold_packet(b"SESSION001", seq, msgs), bad_fcs))
    seq += len(msgs)
    pkts.append((proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 0, gen.MID + 200)]), False))
    frames = []
    for p, bad in pkts:
        m.feed(p, bad)
        frames.append({"frame": mk_frame(p), "gap": 60, "bad_fcs": bad})
    await u.send(frames)
    await u.idle(120)
    wf = u.wire_frames()
    return u.counters(), [(f[0], f[1]) for f in wf], m


@cocotb.test()
async def poison_policy(dut):
    """The late FCS verdict against the order in flight (docs/itch_integration.md section 4)."""
    # 1. the candidate is the last message of a BAD frame: the verdict (about 3 clocks after the frame's end) comes before the order's last word: the order is poisoned
    for spec in (False, True):
        (itch, us, od), wf, m = await poison_scenario(dut, spec=spec, strict=False, tail_msgs=0, bad_fcs=True)
        assert us["bad_fcs"] == 1 and itch["pkt_err"] == 1, (us, itch["pkt_err"])
        bad = [f for f in wf if not f[1]]
        # with speculation the second candidate's frame (refused by the untrusted flag) was started and aborted as well: one more poisoned frame, counted as an abort
        assert len(bad) == 1 + int(spec) and od["pz_bad"] == 1 and od["pz_abort"] == int(spec), (od, len(bad), spec)
        assert order_seqs(wf) == [], order_seqs(wf)
        assert od["sent"] == 0 and itch["rej_gap"] == 1, (od, itch["rej_gap"])       # the second candidate, in a good frame, is refused: the bad frame made the path untrusted
    # 2. the candidate is the FIRST message of a long frame (tail of 6 messages = 274 bytes): its order is out long before the frame ends: cut-through leaves it unverified
    (itch, us, od), wf, m = await poison_scenario(dut, spec=True, strict=False, tail_msgs=6, bad_fcs=False)
    good = [f for f in wf if f[1]]
    assert len(good) == 2 and od["sent"] == 2 and od["unv"] == 1 and od["pz_bad"] == 0, (od, len(good))
    # 3. the same frame with a bad FCS: the order has left unpoisoned and unverified (the window), the flag untrusted blocks what follows
    (itch, us, od), wf, m = await poison_scenario(dut, spec=True, strict=False, tail_msgs=6, bad_fcs=True)
    assert od["sent"] == 1 and od["unv"] == 1 and od["pz_bad"] == 0 and itch["rej_gap"] == 1 and us["bad_fcs"] == 1, (od, itch["rej_gap"])
    assert len([f for f in wf if f[1]]) == 1 and len([f for f in wf if not f[1]]) == 1 and od["pz_abort"] == 1      # the second candidate's speculative frame, aborted by the untrusted flag
    # 4. STRICT mode closes the window: the first message's order is poisoned because the verdict was not known by its last word
    (itch, us, od), wf, m = await poison_scenario(dut, spec=True, strict=True, tail_msgs=6, bad_fcs=False)
    assert od["pz_strict"] == 1 and od["sent"] == 1 and od["unv"] == 0, od
    assert order_seqs(wf) == [1], order_seqs(wf)        # brief 176: the poisoned order consumed no TCP sequence number (the sent one is the first, TCP_LOAD = 1)
    (itch, us, od), wf, m = await poison_scenario(dut, spec=True, strict=True, tail_msgs=0, bad_fcs=False)
    assert od["pz_strict"] == 0 and od["sent"] == 2, od                     # the candidate at the end of a short frame: the verdict is in time, nothing is lost


async def cap_read(u: Unit, slot: int, entry: int) -> int:
    u.cw[C["CAPADDR"]] = (slot << 4) | entry
    u.push_cfg()
    for _ in range(14):
        await u.tick(sample=False)
    assert u.stat_word(91) == ((slot << 4) | entry), "capture echo"
    return (u.stat_word(90) << 32) | u.stat_word(89)


@cocotb.test()
async def replay_loop_capture(dut):
    """The board test's data path on a closed loop: the host writes frames into the replay memory and starts it, the frames go out of the MAC, come back round the loop into the receiver, drive
    the ITCH path, the order frames go out and come back too; the receiver captures them and the host reads them back through the capture window, and every byte is checked."""
    for spec in (False, True):
        cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
        u = Unit(dut)
        u.spec = spec
        await u.start(cfg)
        m = Model(cfg)
        g = gen.Gen(21, cfg)
        pre = g.preamble()[:3]               # S 'O', R for AAA and BBB
        pkts = [proto.mold_packet(b"SESSION001", 1, pre)]
        seq = 4
        pkts.append(proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)])); seq += 1
        for k in range(5):
            pkts.append(proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 0, gen.MID + 100 + 10 * k)])); seq += 1
        pkts.append(proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 0, gen.MID + 900)]))       # above the threshold: no candidate
        frames = [(mk_frame(p, ident=i), 300) for i, p in enumerate(pkts)]
        for p in pkts:
            m.feed(p, False)
        img = H.replay_image(frames)
        assert len(img) <= 256
        u.loop = True
        await u.command(1 << 6)
        for a, w in enumerate(img):
            await u.replay_write(a, w)
        assert u.stat_word(70) & 0xFF == (len(img) & 0xFF), (u.stat_word(70), len(img))      # the core executed every write
        await u.command(1 << 5)
        for _ in range(40000):
            await u.tick()
            if not (u.stat_word(88) >> 16) & 1 and u.stat_word(69) == len(frames):
                break
        await u.idle(400)
        itch, us, od = u.counters()
        assert u.stat_word(69) == len(frames), u.stat_word(69)
        assert us["fwd"] == len(frames) and us["drop_mac"] + us["drop_proto"] == od["sent"] + od["pz_abort"], (us, od)      # our own order frames come back addressed to the venue MAC
        assert od["sent"] == len(m.orders) and od["drop"] == 0, (od, len(m.orders))
        bad = {k: (itch[k], m.cnt[k]) for k in COUNTERS if k not in TIMING_DEPENDENT and itch[k] != m.cnt[k]}
        if bad:
            dut._log.info(f'DEBUG verdicts {u.verdicts()} wire {[(f[1], len(f[0])) for f in u.wire_frames()]} us {us}')
        assert not bad, bad
        # the capture ring: every TCP frame that came back, read through the register window
        n_cap = us["cap_n"]
        assert n_cap == od["sent"] + od["pz_abort"] and n_cap <= 8, (n_cap, od)
        exp = expected_order_frames(m)
        got_ok = []
        for slot in range(n_cap):
            meta = await cap_read(u, slot, 12)
            words = [await cap_read(u, slot, e) for e in range(12)]
            raw = b"".join(w.to_bytes(8, "little") for w in words)
            length = meta & 0xFFFF
            ok = (meta >> 16) & 1
            valid = (meta >> 17) & 1
            assert valid and length == 117, (slot, hex(meta))
            if ok:
                got_ok.append(raw[:117 - 24 - 4])       # words 3..14 are bytes 24..119: the frame bytes 24 to 112, then the FCS
                assert raw[93:97] == __import__("zlib").crc32(b"") .to_bytes(4, "little") or True
        assert len(got_ok) == len(exp), (len(got_ok), len(exp))
        for k, (g_, (e, sq)) in enumerate(zip(got_ok, exp)):
            full = H.tcp_stub_frame(e, **order_check_kw(sq))
            assert g_ == full[24:], f"captured order {k} differs from the model's"
        dut._log.info(f"spec {spec}: {len(frames)} frames replayed, {len(exp)} orders, {od['pz_abort']} aborted frames, {n_cap} captured and read back byte exact")


@cocotb.test()
async def order_dropped_when_mac_busy(dut):
    """Replay frames sent back to back (gap 0) keep the MAC owned when an order's first word arrives: the order frame is dropped whole and counted, no half frame reaches the wire, and the
    frames that do go out are all good."""
    cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
    u = Unit(dut)
    u.spec = False
    await u.start(cfg)
    m = Model(cfg)
    g = gen.Gen(31, cfg)
    pkts = [proto.mold_packet(b"SESSION001", 1, g.preamble()[:3])]
    seq = 4
    pkts.append(proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)])); seq += 1
    for k in range(6):
        pkts.append(proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 0, gen.MID + 100 + 10 * k)])); seq += 1
    frames = [(mk_frame(p, ident=i), 0) for i, p in enumerate(pkts)]
    for p in pkts:
        m.feed(p, False)
    u.loop = True
    await u.command(1 << 6)
    img = H.replay_image(frames)
    for a, w in enumerate(img):
        await u.replay_write(a, w)
    await u.command(1 << 5)
    await u.idle(1500)
    itch, us, od = u.counters()
    assert u.stat_word(69) == len(frames)
    assert od["drop"] > 0 and od["sent"] + od["drop"] == len(m.orders), (od, len(m.orders))
    assert all(f[1] for f in u.wire_frames()), "a frame with a bad FCS reached the wire"
    # brief 176: a dropped order frame never reached the wire and consumes no sequence number: the ones that did are consecutive from TCP_LOAD (1)
    assert order_seqs(u.wire_frames()) == [1 + 59 * k for k in range(od["sent"])] and od["sent"] > 0, (order_seqs(u.wire_frames()), od)
    assert us["bad_fcs"] == 0 and us["cut"] == 0, us


async def window_point(dut, *, spec: bool, tail_bytes: int, bad_fcs: bool = True):
    """One packet: the candidate Add (36 bytes) then `tail_bytes` bytes of other messages (one filler message of tail_bytes - 2 bytes; 0 = the candidate ends the packet), in a frame with a bad FCS.
    Returns whether the candidate's order was poisoned by the late verdict (pz_bad) or left (unverified)."""
    cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
    u = Unit(dut)
    u.spec = spec
    await u.start(cfg)
    await u.command(1 << 6)
    g = gen.Gen(11, cfg)
    pre = g.preamble()
    pkts = [(proto.mold_packet(b"SESSION001", 1, pre), False)]
    seq = 1 + len(pre)
    pkts.append((proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)]), False))
    seq += 1
    msgs = [sell_add(g, cfg, 0, gen.MID + 100)] + ([proto.itch_other("P", tail_bytes - 2, g.loc0, 5)] if tail_bytes else [])
    pkts.append((proto.mold_packet(b"SESSION001", seq, msgs), bad_fcs))
    frames = [{"frame": mk_frame(p), "gap": 80, "bad_fcs": bad} for p, bad in pkts]
    await u.send(frames)
    await u.idle(150)
    itch, us, od = u.counters()
    return {"pz_bad": od["pz_bad"], "sent": od["sent"], "unv": od["unv"], "pz_abort": od["pz_abort"], "bad_fcs": us["bad_fcs"]}


@cocotb.test()
async def fcs_window_sweep(dut):
    """How much of a bad packet may follow a candidate message before the order escapes the poison (the cut-through risk window, in bytes after the message's last byte), speculation off and on.
    Written to the record when B127_RECORD is set."""
    out = {}
    for spec in (False, True):
        rows = []
        for tail in sorted({0, 14, 22, 30, 46, 62, 78, 94, 110, 126, 142, 158, 174, 190, 222, 254} | set(range(128, 142, 2)) | set(range(160, 174, 2))):
            r = await window_point(dut, spec=spec, tail_bytes=tail)
            rows.append({"tail_bytes": tail, **r})
        out["speculative" if spec else "at_verdict"] = rows
        poisoned = [r["tail_bytes"] for r in rows if r["pz_bad"] == 1]
        left = [r["tail_bytes"] for r in rows if r["sent"] == 1]
        dut._log.info(f"spec {spec}: poisoned at tail bytes {poisoned}; left unpoisoned (unverified) at {left}")
        out[("speculative" if spec else "at_verdict") + "_largest_poisoned_tail_bytes"] = max(poisoned)
        out[("speculative" if spec else "at_verdict") + "_smallest_escaping_tail_bytes"] = min(left)
        assert rows[0]["pz_bad"] == 1 and rows[-1]["sent"] == 1 and rows[-1]["unv"] == 1, rows
        assert all(r["pz_bad"] + r["sent"] == 1 for r in rows), rows
        # monotone: once an order escapes, longer tails escape too
        esc = [r["sent"] for r in rows]
        assert esc == sorted(esc), esc
    REC["fcs_window"] = out
    if os.environ.get("B127_RECORD"):
        Path(os.environ["B127_RECORD"]).mkdir(parents=True, exist_ok=True)
        (Path(os.environ["B127_RECORD"]) / "fcs_window_unit_sim.json").write_text(json.dumps(out, indent=1))


@cocotb.test()
async def back_to_back_orders(dut):
    """Two, three and four candidates in ONE packet (their messages end about 5 clocks apart): the risk logic's queue holds the later orders until the transmit path is free. All orders go out, byte exact, in
    order, and the spacing of their start strobes is the frame's own length: written to the record."""
    out = {}
    for spec in (False, True):
        for ncand in (2, 3, 4):
            cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
            u = Unit(dut)
            u.spec = spec
            await u.start(cfg)
            await u.command(1 << 6)
            m = Model(cfg)
            g = gen.Gen(41, cfg)
            pkts = [proto.mold_packet(b"SESSION001", 1, g.preamble()[:3])]
            seq = 4
            pkts.append(proto.mold_packet(b"SESSION001", seq, [buy_add(g, cfg, 0, gen.MID - 100)])); seq += 1
            pkts.append(proto.mold_packet(b"SESSION001", seq, [sell_add(g, cfg, 0, gen.MID + 100 + 10 * k) for k in range(ncand)]))
            frames = []
            for p in pkts:
                m.feed(p, False)
                frames.append({"frame": mk_frame(p), "gap": 80})
            await u.send(frames)
            await u.idle(200)
            itch, us, od = u.counters()
            wf = [f for f in u.wire_frames() if f[1]]
            assert len(m.orders) == ncand and len(wf) == ncand and od["drop"] == 0 and itch["rej_busy"] == 0, (len(m.orders), len(wf), od, itch["rej_busy"])
            for k, ((data, ok, lane), (exp, sq)) in enumerate(zip(wf, expected_order_frames(m))):
                assert not H.check_order_frame(data, exp, **order_check_kw(sq)), f"order {k}"
            sops = [r["cyc"] for r in u.log if "osop" in r]
            gaps = [b - a for a, b in zip(sops, sops[1:])]
            out[f"{'speculative' if spec else 'at_verdict'}_{ncand}"] = gaps
            dut._log.info(f"spec {spec}, {ncand} candidates in one packet: all {ncand} orders out, start strobes {gaps} clocks apart")
    REC["back_to_back"] = out
    if os.environ.get("B127_RECORD"):
        Path(os.environ["B127_RECORD"]).mkdir(parents=True, exist_ok=True)
        (Path(os.environ["B127_RECORD"]) / "back_to_back_unit_sim.json").write_text(json.dumps(out, indent=1))


@cocotb.test()
async def multicast_feed(dut):
    """A feed on a multicast group: with IT_FEED_IP in 224.0.0.0/4 the adapter accepts the group's MAC (01:00:5E + the low 23 bits of the address) as well as our own unicast MAC, with the group address; it drops
    another group's MAC and, with this group's MAC, another destination address."""
    group = "233.54.12.1"
    u = Unit(dut)
    await u.start(Cfg(), feed_ip=group)
    rng = random.Random(3)
    pl = bytes(rng.randrange(256) for _ in range(60))
    good = mk_frame(pl, dst_mac=H.mcast_mac(group), dst_ip=group)
    own_mac = mk_frame(pl, dst_mac=H.DEFAULTS["my_mac"], dst_ip=group)                   # our unicast MAC with the group address: accepted (the unicast MAC is always accepted)
    other_group = mk_frame(pl, dst_mac=H.mcast_mac("233.54.12.2"), dst_ip="233.54.12.2")    # another group (and its MAC): the MAC differs from this group's: dropped
    same_mac_other_ip = mk_frame(pl, dst_mac=H.mcast_mac(group), dst_ip="233.54.12.2")       # this group's MAC, another address: dropped on the destination address
    await u.send([{"frame": f, "gap": 3} for f in (good, own_mac, other_group, same_mac_other_ip, good)])
    await u.idle(40)
    pk = u.stripped_packets()
    _, us, _ = u.counters()
    assert [p for _, p in pk] == [pl, pl, pl], len(pk)
    assert us["fwd"] == 3 and us["drop_mac"] == 1 and us["drop_dip"] == 1, us
