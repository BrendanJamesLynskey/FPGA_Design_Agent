"""cocotb bench for trigger_core: traffic from the mock venue and hostile frames in, against the reference
model (model/ref_model.py); per-stage latencies out (results/b58a/latency_sim.json via $B58A_LAT_OUT)."""

from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge

from designs.b58a_trigger.host import strategy as st
from designs.b58a_trigger.host.mock_venue import Venue
from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import COUNTERS, Config, Model

SEED = int(os.environ.get("B58A_SEED", "1"))
BUILD_MODE = int(os.environ.get("B58A_BUILD_MODE", "0"))


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.cyc = 0
        self.a_out: list[tuple[int, int, int]] = []        # (cycle, en, byte)
        self.b_out: list[tuple[int, int, int]] = []
        self.rxq: list[dict] = []
        self.sfd_cycles: list[int] = []
        self.byte_cycles: list[list[int]] = []
        self.events: dict[str, list[int]] = {k: [] for k in ("sfd", "px", "fire", "grant", "start", "first", "sof", "end")}
        self.loop = False
        self.loop_delay = 6

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 8, unit="ns").start())
        for s in (d.a_rx_v, d.a_rx_eof, d.a_rx_er, d.a_rx_d, d.a_rx_ovf, d.b_rx_v, d.b_rx_eof, d.b_rx_er, d.b_rx_d,
                  d.b_rx_ovf, d.h_we, d.h_re, d.h_addr, d.h_wdata, d.a_mdio_i, d.b_mdio_i, d.drp_do, d.drp_rdy,
                  d.alarms, d.kill_in, d.a_rxclk_cnt, d.b_rxclk_cnt):
            s.value = 0
        d.rst.value = 1
        for _ in range(4):
            await RisingEdge(d.clk)
        d.rst.value = 0
        cocotb.start_soon(self._mon())
        cocotb.start_soon(self._drive())
        # the book and histograms clear themselves after reset (one entry a clock)
        for _ in range(300):
            await RisingEdge(d.clk)

    async def _mon(self):
        d = self.dut
        bq: list[tuple[int, int]] = []
        aq: list[tuple[int, int]] = []
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            self.cyc += 1
            ae, ab = int(d.a_tx_en.value), int(d.a_txd.value)
            be, bb = int(d.b_tx_en.value), int(d.b_txd.value)
            self.a_out.append((self.cyc, ae, ab))
            self.b_out.append((self.cyc, be, bb))
            ev = self.events
            if int(d.u_arx.sof_pulse.value): ev["sfd"].append(self.cyc)
            if int(d.u_parse.msg_px_v.value): ev["px"].append(self.cyc)
            if int(d.u_rules.fire_v.value): ev["fire"].append(self.cyc)
            if int(d.u_il.grant.value): ev["grant"].append(self.cyc)
            if int(d.u_ord.tx_start.value): ev["start"].append(self.cyc)
            if int(d.u_atx.first_pulse.value): ev["first"].append(self.cyc)
            if int(d.u_atx.sof_pulse.value): ev["sof"].append(self.cyc)
            if int(d.u_parse.frame_end_v.value): ev["end"].append(self.cyc)
            if self.loop:
                aq.append((be, bb))
                bq.append((ae, ab))

    async def _drive(self):
        """Port A receive (and in loop mode port B too): bytes with RX_DV, an end token when it falls."""
        d = self.dut
        prev_a = prev_b = 0
        a_hist: list[tuple[int, int]] = []
        b_hist: list[tuple[int, int]] = []
        cur = None
        i = 0
        gap = 0
        bubble = 0.0
        rng = random.Random(SEED + 7)
        while True:
            await RisingEdge(d.clk)
            if self.loop:
                a_hist.append((int(d.b_tx_en.value), int(d.b_txd.value)))
                b_hist.append((int(d.a_tx_en.value), int(d.a_txd.value)))
                ea, ba = a_hist[-self.loop_delay] if len(a_hist) >= self.loop_delay else (0, 0)
                eb, bb_ = b_hist[-self.loop_delay] if len(b_hist) >= self.loop_delay else (0, 0)
                d.a_rx_v.value = 1 if (ea or prev_a) else 0
                d.a_rx_eof.value = 1 if (not ea and prev_a) else 0
                d.a_rx_d.value = ba if ea else 0
                d.a_rx_er.value = 0
                d.b_rx_v.value = 1 if (eb or prev_b) else 0
                d.b_rx_eof.value = 1 if (not eb and prev_b) else 0
                d.b_rx_d.value = bb_ if eb else 0
                d.b_rx_er.value = 0
                prev_a, prev_b = ea, eb
                continue
            d.a_rx_v.value = 0
            d.a_rx_eof.value = 0
            d.a_rx_er.value = 0
            if cur is None:
                if gap > 0:
                    gap -= 1
                    continue
                if not self.rxq:
                    continue
                cur = self.rxq.pop(0)
                i = 0
                bubble = cur.get("bubble", 0.0)
                self.byte_cycles.append([])
            if bubble and rng.random() < bubble and 0 < i < len(cur["wire"]):
                continue
            if i < len(cur["wire"]):
                d.a_rx_v.value = 1
                d.a_rx_d.value = cur["wire"][i]
                d.a_rx_er.value = 1 if i in cur.get("er", ()) else 0
                if i == 7:
                    self.sfd_cycles.append(self.cyc + 1)
                self.byte_cycles[-1].append(self.cyc + 1)
                i += 1
            else:
                d.a_rx_v.value = 1
                d.a_rx_eof.value = 1
                gap = cur["gap"]
                cur = None

    def send(self, frame_with_fcs: bytes, gap: int = 200, er=(), bubble: float = 0.0, preamble: bytes = bf.PREAMBLE):
        self.rxq.append({"wire": preamble + frame_with_fcs, "gap": gap, "er": er, "bubble": bubble})

    async def idle(self, n: int = 1):
        for _ in range(n):
            await RisingEdge(self.dut.clk)

    async def drain(self, extra: int = 400):
        while self.rxq:
            await self.idle(50)
        await self.idle(extra)

    async def wr(self, addr: int, val: int):
        d = self.dut
        d.h_addr.value = addr
        d.h_wdata.value = val & 0xFFFFFFFF
        d.h_we.value = 1
        await RisingEdge(d.clk)
        d.h_we.value = 0
        await RisingEdge(d.clk)

    async def rd(self, addr: int) -> int:
        d = self.dut
        d.h_addr.value = addr
        d.h_re.value = 1
        await RisingEdge(d.clk)
        d.h_re.value = 0
        for _ in range(3):
            await RisingEdge(d.clk)
        await ReadOnly()
        v = int(d.h_rdata.value)
        await RisingEdge(d.clk)
        return v

    async def config(self, cfg: Config, table: list[list[int]] | None = None, metric: int = 0):
        await self.wr(0x020, cfg.max_qty)
        await self.wr(0x021, cfg.band)
        await self.wr(0x022, cfg.max_pos)
        await self.wr(0x023, cfg.bucket)
        await self.wr(0x024, 0xFFFFFFFF)                    # no refill within a test (see ref_model docstring)
        if table is not None:
            await self.load(table)
        await self.wr(0x002, 1 | cfg.spec_en << 1 | cfg.halt_on_gap << 2 | cfg.kill << 3 | metric << 4)
        await self.idle(20)

    async def load(self, table: list[list[int]]):
        for r, ws in enumerate(table):
            for w, v in enumerate(ws):
                await self.wr(0x040 + r * 8 + w, v)
        await self.wr(0x003, 1 << 5)

    async def counters(self) -> dict[str, int]:
        return {n: await self.rd(0x100 + i) for i, n in enumerate(COUNTERS)}

    def a_frames(self) -> list[tuple[int, bytes, bool]]:
        """(first cycle, frame without preamble/FCS, FCS good) for every frame port A sent."""
        out, cur, c0 = [], None, 0
        for c, en, b in self.a_out:
            if en:
                if cur is None:
                    cur, c0 = bytearray(), c
                cur.append(b)
            elif cur is not None:
                body, ok = bf.check_wire_frame(bytes(cur))
                out.append((c0, body, ok))
                cur = None
        return out


def check_outputs(b: Bench, expected: list, model: Model) -> dict:
    """Match port A's frames to the model's outputs, in order. Returns a summary."""
    seen = b.a_frames()
    orders = [(c, bf.parse_order(f), ok, f) for c, f, ok in seen if f[12:14] == b"\x08\x00"]
    arps = [f for c, f, ok in seen if f[12:14] == b"\x08\x06"]
    assert all(ok for c, f, ok in seen if f[12:14] == b"\x08\x06"), "an ARP reply left with a bad FCS"
    news = [(c, o, ok) for c, o, ok, f in orders if o and o.type == bf.NEW_ORDER]
    cans = [(c, o, ok) for c, o, ok, f in orders if o and o.type == bf.CANCEL_ORDER]
    assert all(o is not None for c, o, ok, f in orders), "a frame that is not an order"
    assert all(ok for c, o, ok in cans), "a cancel left with a bad FCS"
    # out_seq: every order or cancel frame carries the next number
    seqs = [o.seq for c, o, ok, f in orders]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))) if seqs else True, f"order sequence numbers {seqs}"
    exp_orders = [x for x in expected if x.kind == "order"]
    exp_arps = [x for x in expected if x.kind == "arp"]
    undone = dropped = 0
    cancel_ids = [o.order_id for c, o, ok in cans]
    it = iter(news)
    nxt = next(it, None)
    for e in exp_orders:
        eo = e.order
        if nxt is None or nxt[1].order_id != eo.order_id:
            # not on the wire: only an order from a bad frame may be dropped before it starts
            assert e.undo, f"order {eo.order_id} missing from the wire"
            assert eo.order_id not in cancel_ids
            undone += 1
            dropped += 1
            continue
        c, o, ok = nxt
        nxt = next(it, None)
        assert (o.side, o.inst, o.price, o.qty, o.order_id) == (eo.side, eo.inst, eo.price, eo.qty, eo.order_id), \
            f"order {o} != model {eo}"
        if e.undo:
            undone += 1
            poisoned = not ok
            cancelled = o.order_id in cancel_ids
            assert poisoned != cancelled, f"order {o.order_id}: poisoned={poisoned} cancelled={cancelled}"
        else:
            assert ok and o.order_id not in cancel_ids, f"order {o.order_id} undone without cause"
    assert nxt is None, f"an order on the wire the model did not expect: {nxt}"
    assert len(cancel_ids) == len(set(cancel_ids))
    assert len(arps) == len(exp_arps)
    for f, e in zip(arps, exp_arps):
        sha, spa = e.arp
        assert f == bf.arp_reply(model.cfg.my_mac, model.cfg.my_ip, sha, spa), "ARP reply content"
    return {"orders": len(news), "undone": undone, "dropped": dropped, "cancels": len(cancel_ids), "arps": len(arps)}


def compare_counters(hw: dict, model: Model, exact_tx: bool = True) -> None:
    """Every counter equal to the model's, except those that depend on when an undo happened (dropped before start,
    poisoned or cancelled), which must add up."""
    m = model.cnt
    timing = {"spec_drop", "spec_poison", "spec_cancel", "orders_sent", "cancels_sent", "tx_frames", "tx_poisoned"}
    skip = timing | {"rx_bad_pre", "log_dropped", "rx_fifo_ovf", "wdog", "soft_resets"} | \
        {n for n in COUNTERS if n.startswith("b_")}
    bad = {n: (hw[n], m[n]) for n in COUNTERS if n not in skip and hw[n] != m[n]}
    assert not bad, f"counters differ (hw, model): {bad}"
    undo = m.get("undo_any", 0)
    assert hw["spec_drop"] + hw["spec_poison"] + hw["spec_cancel"] == undo, \
        (hw["spec_drop"], hw["spec_poison"], hw["spec_cancel"], undo)
    assert hw["orders_sent"] == hw["grants"] - hw["spec_drop"] - hw["kill_drop"]
    assert hw["cancels_sent"] == hw["spec_cancel"]
    assert hw["tx_poisoned"] == hw["spec_poison"]
    assert hw["wdog"] == 0
    if exact_tx:
        assert hw["tx_frames"] == hw["orders_sent"] + hw["cancels_sent"] + hw["arp_sent"]


def prime(b: "Bench", model: Model | None, insts=range(8), seq: int = 900000, bid: int = 9900, ask: int = 10000) -> int:
    """A good frame that puts a bid and an ask on each instrument, so the price band has a reference (the band is
    checked against the book before the triggering message). Returns the next sequence number to use."""
    msgs = []
    for i in insts:
        msgs += [bf.Msg(bf.ADD, bf.BID, i, bid, 10), bf.Msg(bf.ADD, bf.ASK, i, ask, 10)]
    fr = bf.with_fcs(bf.feed_frame(seq, msgs))
    if model is not None:
        model.frame(fr)
    b.send(fr, gap=300)
    return seq + len(msgs)


# ---- traffic -------------------------------------------------------------------------------------------------------

def standard_rules() -> list[dict]:
    return [
        {"name": "buy inst 3 when the ask drops below 99.80", "match": {"types": ["ADD", "MODIFY"], "side": "ask",
         "instrument": 3, "price": {"op": "<", "value": "99.80"}},
         "action": {"order": {"side": "buy", "qty": 5, "price": {"mode": "message"}}, "log": True}},
        {"name": "sell after a trade above 100.40", "match": {"types": ["TRADE"], "price": {"op": ">", "value": 100.40}},
         "action": {"order": {"side": "sell", "qty": 3, "price": {"mode": "offset", "value": -0.10}}, "log": True}},
        {"name": "bid improves on inst 1 at 99.00 or more", "match": {"types": ["ADD"], "side": "bid", "instrument": 1,
         "price": {"op": ">=", "value": 99.0}, "book": "improves"},
         "action": {"order": {"side": "sell", "qty": 2, "price": {"mode": "fixed", "value": 99.0}}, "pin": 0}},
        {"name": "flag a crossed book", "match": {"types": ["ADD"], "book": "crosses"}, "action": {"pin": 1, "log": True}},
    ]


def hostile_frames(rng: random.Random, v: Venue) -> list[tuple[bytes, dict]]:
    """Frames the parser must drop or survive (each with its FCS), with any send options."""
    good = v.frame(2)
    fr = []
    fr.append((bf.with_fcs(bf.feed_frame(1, [], dst_mac=0x020000000099, count=1)), {}))          # wrong MAC
    fr.append((bf.with_fcs(bf.ethernet(bf.BOARD_MAC, bf.VENUE_MAC, 0x86DD, bytes(60))), {}))       # IPv6
    fr.append((bf.with_fcs(bf.ethernet(bf.BOARD_MAC, bf.VENUE_MAC, 0x8100, bytes(60))), {}))       # VLAN tag
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], ihl_byte=0x46)), {}))     # IPv4 options
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], flags_frag=0x2000)), {}))  # fragment
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], proto=6)), {}))            # TCP
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], dst_ip=0xC0A83A63)), {}))  # not our IP
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], bad_csum=True)), {}))      # IP checksum
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], dport=999)), {}))          # wrong port
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], magic=0x1234)), {}))       # bad magic
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], version=2)), {}))          # bad version
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], count=3)), {}))            # count > length
    fr.append((bf.with_fcs(bf.feed_frame(5, [bf.Msg(1, 1, 3, 9000, 1)], count=0)), {}))            # count 0
    fr.append((bf.with_fcs(bf.ethernet(0xFFFFFFFFFFFF, bf.VENUE_MAC, 0x0800, bytes(60))), {}))     # IPv4 broadcast
    fr.append((bf.with_fcs(bf.arp_request(bf.VENUE_MAC, bf.VENUE_IP, bf.BOARD_IP)), {}))           # ARP for us
    fr.append((bf.with_fcs(bf.arp_request(bf.VENUE_MAC, bf.VENUE_IP, 0xC0A83A63)), {}))            # ARP not for us
    fr.append((bf.with_fcs(bf.arp_request(bf.VENUE_MAC, bf.VENUE_IP, bf.BOARD_IP, oper=2)), {}))   # ARP reply
    fr.append((bf.with_fcs(good, bad=True), {}))                                                     # bad FCS
    fr.append((bf.with_fcs(good)[:40], {}))                                                          # runt
    fr.append((bf.with_fcs(good + bytes(1500)), {}))                                                 # giant
    fr.append((bf.with_fcs(good), {"er": (30,)}))                                                    # RX_ER
    # a feed frame cut short in its second message (claims 4 messages; the UDP length says so too)
    seq, msgs = v.packet_msgs(4)
    f = bf.feed_frame(seq, msgs)
    fr.append((bf.with_fcs(f[:50 + 16 + 9]), {}))
    return fr


async def run_stream(dut, spec_en: bool, n: int, gap_lo: int, gap_hi: int, hostile: float, bubble: float,
                     exact_tx: bool = True, max_msgs: int = 6) -> dict:
    b = Bench(dut)
    await b.start()
    rng = random.Random(SEED)
    v = Venue(seed=SEED, ninst=8)
    cfg = Config(spec_en=spec_en, bucket=1000, max_pos=100000)
    norm = rl.validate_table(standard_rules(), rl.Limits(cfg.max_qty, cfg.band, cfg.max_pos))
    table = rl.table_words(norm)
    m = Model(cfg=cfg)
    m.commit(table)
    await b.config(cfg, table)
    prime(b, m)
    expected = []
    for _ in range(n):
        if rng.random() < hostile:
            fr, opt = rng.choice(hostile_frames(rng, v))
        else:
            fr, opt = bf.with_fcs(v.frame(rng.randint(1, max_msgs))), {}
            if rng.random() < 0.08:
                fr = fr[:-4] + bytes([fr[-4] ^ 0x10]) + fr[-3:]      # bad FCS on a feed frame (speculative undo)
        expected += m.frame(fr, er=bool(opt.get("er")))
        b.send(fr, gap=rng.randint(gap_lo, gap_hi), er=opt.get("er", ()), bubble=bubble)
    await b.drain(800)
    hw = await b.counters()
    compare_counters(hw, m, exact_tx)
    summary = check_outputs(b, expected, m) if exact_tx else {}
    # the decision log against the model's
    nlog = await b.rd(0x140)
    assert nlog == min(len(m.log), 64), (nlog, len(m.log))
    for e in m.log[:nlog]:
        w0, w1, w2, w3 = [await b.rd(0x141 + i) for i in range(4)]
        await b.wr(0x003, 1 << 6)
        assert (w1, w2 >> 16, (w2 >> 12) & 7, w2 & 0xFFF, w3) == (e[0], e[1], e[2], e[3], e[4]), (hex(w2), e)
    # the book against the venue's own view (frames that were all good keep them equal; bad ones are excluded by
    # comparing with the model, which applies exactly what the RTL applied)
    for inst in range(8):
        await b.wr(0x030, inst)
        await b.idle(2)
        e = [await b.rd(0x031 + i) for i in range(5)]
        assert e == m.book.get(inst, [0, 0, 0, 0, 0]), (inst, e, m.book.get(inst))
    dut._log.info(f"stream spec={spec_en}: {summary} counters={ {k: v for k, v in hw.items() if v} }")
    return {"summary": summary, "counters": hw}


@cocotb.test()
async def random_stream_speculative(dut):
    """Mock-venue traffic with hostile frames, bad FCS and RX_ER; generous gaps; speculative mode; exact match."""
    await run_stream(dut, True, n=int(os.environ.get("B58A_N", "260")), gap_lo=150, gap_hi=260, hostile=0.25,
                     bubble=0.0)


@cocotb.test()
async def random_stream_safe(dut):
    """The same in safe mode: orders only after a good FCS."""
    await run_stream(dut, False, n=int(os.environ.get("B58A_N", "260")) // 2, gap_lo=150, gap_hi=260, hostile=0.25,
                     bubble=0.0)


@cocotb.test()
async def short_gaps_back_to_back(dut):
    """Minimum gaps (the end token then 11 idle clocks: 12 byte times) and clock-crossing bubbles: the receive side
    must stay exact; a busy order slot may refuse requests, which the counters must account for."""
    b = Bench(dut)
    await b.start()
    rng = random.Random(SEED + 1)
    v = Venue(seed=SEED + 1)
    cfg = Config(bucket=1000, max_pos=100000)
    table = rl.table_words(rl.validate_table(standard_rules()))
    m = Model(cfg=cfg)
    m.commit(table)
    await b.config(cfg, table)
    prime(b, m)
    for _ in range(150):
        fr = bf.with_fcs(v.frame(rng.randint(1, 3)))
        m.frame(fr)
        b.send(fr, gap=11, bubble=0.05)
    await b.drain(800)
    hw = await b.counters()
    for n in ("rx_frames", "rx_good", "rx_bytes", "rx_fcs", "pkts", "msgs", "rule_fires", "seq_gaps"):
        assert hw[n] == m.cnt[n], (n, hw[n], m.cnt[n])
    assert hw["grants"] == hw["orders_sent"] + hw["spec_drop"] + hw["kill_drop"]
    assert hw["requests"] + hw["suppressed"] + hw["busy"] == m.cnt["requests"] + m.cnt["suppressed"]
    assert hw["tx_frames"] == hw["orders_sent"] + hw["cancels_sent"] + hw["arp_sent"]
    assert all(ok for c, f, ok in b.a_frames()), "a frame left with a bad FCS without a bad trigger"
    dut._log.info(f"back-to-back: busy={hw['busy']} orders={hw['orders_sent']} grants={hw['grants']}")


@cocotb.test()
async def maximum_size_frames(dut):
    """91-message packets (1518-byte frames with FCS) back to back, then giants and runts."""
    b = Bench(dut)
    await b.start()
    v = Venue(seed=SEED + 2)
    cfg = Config(bucket=1000, max_pos=100000)
    table = rl.table_words(rl.validate_table(standard_rules()))
    m = Model(cfg=cfg)
    m.commit(table)
    await b.config(cfg, table)
    prime(b, m)
    exp = []
    for k in range(6):
        seq, msgs = v.packet_msgs(bf.MAX_MSGS)        # 91 messages and 8 trailing bytes: a 1518-byte frame
        fr = bf.with_fcs(bf.ethernet(bf.BOARD_MAC, bf.VENUE_MAC, bf.ETH_IPV4, bf.ipv4_udp(
            bf.VENUE_IP, bf.BOARD_IP, bf.VENUE_PORT, bf.BOARD_PORT, bf.packet(seq, msgs) + bytes(8))))
        assert len(fr) == 1518
        exp += m.frame(fr)
        b.send(fr, gap=200)
    for fr in (bf.with_fcs(v.frame(bf.MAX_MSGS) + bytes(20)), bf.with_fcs(bf.ethernet(bf.BOARD_MAC, bf.VENUE_MAC, 0x0800,
                                                                                         bytes(10), pad=False))):
        exp += m.frame(fr)
        b.send(fr, gap=200)
    await b.drain(800)
    hw = await b.counters()
    compare_counters(hw, m)
    check_outputs(b, exp, m)
    assert hw["rx_giant"] == 1 and hw["rx_runt"] == 1 and hw["msgs"] == 16 + 6 * bf.MAX_MSGS + bf.MAX_MSGS   # 16: priming


@cocotb.test()
async def speculative_undo_both_ways(dut):
    """A bad trigger frame: short frame -> the order is still on the wire -> poisoned; a long frame whose trigger is
    its first message -> the order has left -> a cancel follows. Both checked on the wire."""
    b = Bench(dut)
    await b.start()
    cfg = Config(bucket=1000, max_pos=100000)
    table = rl.table_words(rl.validate_table(standard_rules()))
    m = Model(cfg=cfg)
    m.commit(table)
    await b.config(cfg, table)
    trig = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 10)
    filler = [bf.Msg(bf.ADD, bf.BID, 5, 9000 + k, 1) for k in range(20)]
    prime(b, m)
    exp = []
    for seq, msgs in ((1, [trig]), (2, [trig] + filler)):
        fr = bf.with_fcs(bf.feed_frame(seq, msgs), bad=True)
        exp += m.frame(fr)
        b.send(fr, gap=300)
    await b.drain(600)
    hw = await b.counters()
    compare_counters(hw, m)
    s = check_outputs(b, exp, m)
    assert hw["spec_poison"] == 1 and hw["spec_cancel"] == 1, (hw["spec_poison"], hw["spec_cancel"])
    assert s["undone"] == 2


@cocotb.test()
async def interlocks_under_attack(dut):
    """Traffic built to break each interlock: a burst for the rate limit, one-sided orders for the position limit,
    a rule with a fat-finger price and one with a fat-finger size (written straight to the registers, past the
    validator), a sequence gap with halt-on-gap, and the kill register. No order may leave in breach."""
    b = Bench(dut)
    await b.start()
    cfg = Config(bucket=4, max_pos=12, max_qty=10, band=100, halt_on_gap=True)
    rules = [
        {"match": {"types": ["ADD"], "side": "ask", "instrument": 3}, "action": {"order": {"side": "buy", "qty": 5,
         "price": {"mode": "message"}}}},
    ]
    table = rl.table_words(rl.validate_table(rules, rl.Limits(10, 100, 12)))
    # rule 1: fat-finger price (fixed 50.00 against triggers near 99) and rule 2: size 1000, both on instrument 4/5
    table[1] = [1 | 1 << 1 | 2 << 5 | 1 << 13, 4, 0, 5, 5000, 0]
    table[2] = [1 | 1 << 1 | 2 << 5 | 1 << 13, 5, 0, 1000, 0, 0]
    table[2][0] |= 1 << 15
    m = Model(cfg=cfg)
    m.commit(table)
    await b.config(cfg, table)
    exp = []
    seq = prime(b, m, insts=(3, 4, 5), seq=1, ask=9950)    # band references; continuous sequence (halt on gap is on)
    def send(msgs, gap=300, seq_override=None):
        nonlocal seq, exp
        s = seq if seq_override is None else seq_override
        fr = bf.with_fcs(bf.feed_frame(s, msgs))
        exp += m.frame(fr)
        b.send(fr, gap=gap)
        seq = s + len(msgs)
    for k in range(8):                                   # position: 5, 10, then 15 > 12 refused
        send([bf.Msg(bf.ADD, bf.ASK, 3, 9900 - k, 1)])
    send([bf.Msg(bf.ADD, bf.ASK, 4, 9900, 1)])           # band
    send([bf.Msg(bf.ADD, bf.ASK, 5, 9900, 1)])           # size
    send([bf.Msg(bf.ADD, bf.ASK, 3, 9900, 1)], seq_override=seq + 5)    # gap -> halt
    send([bf.Msg(bf.ADD, bf.ASK, 3, 9900, 1)])           # halted
    await b.drain(600)
    hw1 = await b.counters()
    compare_counters(hw1, m)
    check_outputs(b, exp, m)
    # band: the fat-finger rule, and the priming frame's own ADD on instrument 3 (no reference in the book yet)
    assert hw1["rej_pos"] >= 1 and hw1["rej_band"] == 2 and hw1["rej_qty"] == 1 and hw1["rej_halt"] >= 1
    # clear the halt; reset the position by reloading the core (kill test with a fresh state)
    await b.wr(0x003, 1 << 3)
    m.halted = False
    # kill register: nothing leaves
    await b.wr(0x002, 1 | 1 << 1 | 1 << 2 | 1 << 3)
    m.cfg.kill = True
    send([bf.Msg(bf.ADD, bf.ASK, 3, 9900, 1)])
    await b.drain(400)
    hw2 = await b.counters()
    compare_counters(hw2, m)
    assert hw2["rej_kill"] == 1 and hw2["orders_sent"] == hw1["orders_sent"]
    # every order on the wire within the limits
    pos = 0
    for c, f, ok in b.a_frames():
        o = bf.parse_order(f)
        if o and o.type == bf.NEW_ORDER:
            assert o.qty <= cfg.max_qty
            pos += o.qty if o.side == bf.BUY else -o.qty
            assert abs(pos) <= cfg.max_pos


@cocotb.test()
async def rate_limit_burst(dut):
    """A burst of triggers against a 4-token bucket with no refill: exactly 4 orders, the rest refused for rate."""
    b = Bench(dut)
    await b.start()
    cfg = Config(bucket=4, max_pos=100000)
    rules = [{"match": {"types": ["ADD"], "instrument": "any"}, "action": {"order": {"side": "buy", "qty": 1,
              "price": {"mode": "message"}}}}]
    table = rl.table_words(rl.validate_table(rules))
    m = Model(cfg=cfg)
    m.commit(table)
    await b.config(cfg, table)
    prime(b, m)
    exp = []
    for k in range(12):
        fr = bf.with_fcs(bf.feed_frame(1 + k, [bf.Msg(bf.ADD, bf.ASK, k % 8, 10000, 1)]))
        exp += m.frame(fr)
        b.send(fr, gap=120)
    await b.drain(600)
    hw = await b.counters()
    compare_counters(hw, m)
    check_outputs(b, exp, m)
    assert hw["orders_sent"] == 4 and hw["rej_rate"] == 8


@cocotb.test()
async def kill_drops_a_held_order(dut):
    """Safe mode: the order waits for the FCS; the kill register set while it waits drops it before it starts."""
    b = Bench(dut)
    await b.start()
    cfg = Config(spec_en=False, bucket=100, max_pos=100000)
    rules = [{"match": {"types": ["ADD"], "instrument": "any"}, "action": {"order": {"side": "buy", "qty": 1,
              "price": {"mode": "message"}}}}]
    await b.config(cfg, rl.table_words(rl.validate_table(rules)))
    filler = [bf.Msg(bf.ADD, bf.BID, 5, 9000 + k, 1) for k in range(20)]
    prime(b, None, insts=(3,))
    await b.drain(100)
    b.send(bf.with_fcs(bf.feed_frame(1, [bf.Msg(bf.ADD, bf.ASK, 3, 10000, 1)] + filler)), gap=300)
    while not b.events["grant"]:
        await b.idle()
    await b.wr(0x002, 1 | 1 << 3)                        # kill while the order is held
    await b.drain(400)
    hw = await b.counters()
    assert hw["grants"] == 1 and hw["kill_drop"] == 1 and hw["orders_sent"] == 0, hw
    assert not b.a_frames()


@cocotb.test()
async def stage_latency(dut):
    """Per-stage cycles for one trigger, speculative and safe (and BUILD_MODE from the environment), into JSON."""
    b = Bench(dut)
    await b.start()
    rules = [{"match": {"types": ["ADD"], "side": "ask", "instrument": 3, "price": {"op": "<", "value": "100.00"}},
              "action": {"order": {"side": "buy", "qty": 1, "price": {"mode": "message"}}}}]
    table = rl.table_words(rl.validate_table(rules))
    res = {"build_mode": BUILD_MODE, "clock_ns": 8,
           "points": {"sfd_in": "the clock mac_rx takes the SFD (its sof_pulse; the board's histogram A starts here)",
                      "price_complete_in": "the clock the last price byte enters mac_rx (core side, after the RX clock "
                                           "crossing)",
                      "first_byte_out": "the clock mac_tx's first preamble byte is on its registered output (core "
                                        "side, before rgmii_tx and the pins)",
                      "resolution": "one clock, 8 ns"},
           "modes": {}}
    for spec in (True, False):
        await b.config(Config(spec_en=spec, bucket=100, max_pos=100000), table)
        if spec:                                          # after the core is enabled
            prime(b, None, insts=(3,))
            await b.drain(100)
        for nmsg in (1, 20):
            base = {k: len(v) for k, v in b.events.items()}
            n0 = len(b.sfd_cycles) - 1
            msgs = [bf.Msg(bf.ADD, bf.ASK, 3, 9950, 1)] + [bf.Msg(bf.ADD, bf.BID, 6, 9000, 1)] * (nmsg - 1)
            fr = bf.with_fcs(bf.feed_frame(100 + nmsg, msgs))
            b.send(fr, gap=400)
            await b.drain(600)
            ev = {k: b.events[k][base[k]] for k in b.events if len(b.events[k]) > base[k]}
            sfd = ev["sfd"]
            bytes_c = b.byte_cycles[n0 + 1]
            px_last_in = bytes_c[8 + 57]              # wire index: 8 preamble/SFD bytes, then frame byte 57
            last_in = bytes_c[-1]                      # the last FCS byte
            r = {
                "frame_bytes": len(fr), "messages": nmsg,
                "sfd_in": 0, "price_complete_in": px_last_in - sfd, "fcs_last_in": last_in - sfd,
                "decision_to_first_byte_ns": (ev["first"] - px_last_in) * 8,
                "sfd_to_first_byte_ns": (ev["first"] - sfd) * 8,
                "stages_cycles": {
                    "mac_rx + feed_rx (price byte in -> msg_px_v)": ev["px"] - px_last_in,
                    "rules (msg_px_v -> fire)": ev["fire"] - ev["px"],
                    "interlocks (fire -> grant)": ev["grant"] - ev["fire"],
                    "order_ctl (grant -> tx_start)": ev["start"] - ev["grant"],
                    "mac_tx (tx_start -> first preamble byte)": ev["first"] - ev["start"],
                },
                "decision_to_first_byte": ev["first"] - px_last_in,
                "tick_to_trade_sfd_to_first_byte": ev["first"] - sfd,
                "tick_to_trade_sfd_to_sfd": ev["sof"] - sfd,
            }
            res["modes"][f"{'speculative' if spec else 'safe'}_{nmsg}msg"] = r
    dut._log.info(json.dumps(res, indent=1))
    out = os.environ.get("B58A_LAT_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(res, f, indent=1)
    hw_last = await b.rd(0x156)               # histogram A's last sample (metric 0): the same two points, measured in RTL
    assert hw_last == res["modes"]["safe_20msg"]["tick_to_trade_sfd_to_first_byte"], (hw_last, res["modes"]["safe_20msg"])


@cocotb.test()
async def stale_parameters(dut):
    """Tick-to-config: the strategy loop (host/strategy.py) reads the book after a market-data packet and commits a new
    threshold. A trigger message that arrives before the commit is judged on the old table (logged version 1),
    the next one on the new (version 2). The software time is modelled as a fixed number of clocks, not measured."""
    b = Bench(dut)
    await b.start()
    strat = st.MidTracker(inst=3, edge=25, qty=5, alpha_num=1, alpha_den=1)
    old = strat.update(9900, 10, 10100, 10)            # mid 100.00 -> buy below 99.75
    cfg = Config(bucket=100, max_pos=100000)
    table = rl.table_words(rl.validate_table([old]))
    table[0][0] |= 1 << 19
    await b.config(cfg, table)
    # the tick: the book moves up (bid 101.00, ask 103.00) on instrument 3
    tick_sfd_idx = len(b.sfd_cycles)                    # the tick frame's SFD will be the next one recorded
    b.send(bf.with_fcs(bf.feed_frame(1, [bf.Msg(bf.ADD, bf.BID, 3, 10100, 10), bf.Msg(bf.ADD, bf.ASK, 3, 10300, 10)])),
           gap=40)
    # a trigger just after: ask 100.50, above the old threshold 99.75 and below the new one -> judged on v1: no fire
    b.send(bf.with_fcs(bf.feed_frame(3, [bf.Msg(bf.MODIFY, bf.ASK, 3, 10050, 10)])), gap=40)
    while len(b.events["end"]) < 1:
        await b.idle()
    # the slow path: read the book over the bus, compute, write the shadow table, commit
    t_tick_seen = b.cyc
    await b.wr(st.REG_BOOK_INST, 3)
    bk = []
    for a in range(4):
        bk.append(await b.rd(st.REG_BOOK + a))
    new = strat.update(*bk)
    sw_model_cycles = int(os.environ.get("B58A_SW_CYCLES", "2000"))    # assumed software time (16 us), not measured
    await b.idle(sw_model_cycles)
    writes = st.rule_writes(0, new)
    for a, val in writes[:-1]:
        await b.wr(a, val | (1 << 19 if a == st.REG_RULES else 0))
    await b.wr(*writes[-1])
    t_commit = b.cyc
    # a second trigger after the commit, just below the new threshold: fires on version 2
    th_new = rl.validate(new)["threshold"]
    b.send(bf.with_fcs(bf.feed_frame(4, [bf.Msg(bf.MODIFY, bf.ASK, 3, th_new - 5, 10)])), gap=40)
    await b.drain(400)
    ver = await b.rd(0x006)
    commit_ts = await b.rd(0x007)
    nlog = await b.rd(0x140)
    logs = []
    for _ in range(nlog):
        logs.append([await b.rd(0x141 + i) for i in range(4)])
        await b.wr(0x003, 1 << 6)
    hw = await b.counters()
    # the first trigger (ask 100.50) was judged on version 1 (threshold 99.75): no fire; after the commit, the
    # second fires on version 2
    assert ver == 2
    assert hw["rule_fires"] == 1 and len(logs) == 1 and (logs[0][2] >> 16) == 2, logs
    stale_would_fire = 10050 < th_new
    res = {"old_threshold": rl.validate(old)["threshold"], "new_threshold": th_new, "stale_message_price": 10050,
           "stale_message_fired": False, "would_fire_on_new_table": stale_would_fire,
           "tick_sfd_cycle": b.sfd_cycles[tick_sfd_idx], "host_saw_tick_cycle": t_tick_seen,
           "commit_cycle": t_commit, "commit_ts_reg": commit_ts, "bus_writes": len(writes),
           "software_cycles_assumed": sw_model_cycles,
           "tick_to_config_cycles_in_sim": t_commit - b.sfd_cycles[tick_sfd_idx]}
    dut._log.info(json.dumps(res))
    out = os.environ.get("B58A_STALE_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(res, f, indent=1)
    assert stale_would_fire, "the stale case must be one the new table would have fired on"


@cocotb.test()
async def bench_loop_port_b(dut):
    """Port B's generator -> port A -> order -> port B, both directions delayed by a few clocks (a stand-in for the
    PHYs and cable), with bad-FCS and gap injection; the histograms are read back over the bus."""
    b = Bench(dut)
    b.loop = True
    await b.start()
    rules = [{"match": {"types": ["ADD", "MODIFY"], "side": "ask", "instrument": "any",
              "price": {"op": "<", "value": "100.40"}},
              "action": {"order": {"side": "buy", "qty": 1, "price": {"mode": "message"}}}}]
    cfg = Config(bucket=10000, max_pos=1000000)
    await b.config(cfg, rl.table_words(rl.validate_table(rules)))
    await b.wr(0x003, 1 << 2)                           # clear the histograms
    await b.idle(300)
    for a, val in ((0x1C1, 400), (0x1C2, 60), (0x1C3, 2), (0x1C4, 7), (0x1C5, 10000), (0x1C6, 0x3F),
                   (0x1C7, (7 << 16) | 11), (0x1C0, 1)):
        await b.wr(a, val)
    await b.idle(60 * 400 + 2000)
    hw = await b.counters()
    sent = await b.rd(0x1CC)
    assert sent == 60 and hw["b_feed_sent"] == 60 and hw["rx_frames"] == 60
    assert hw["rx_fcs"] == 60 // 7                      # every 7th packet left with a bad FCS
    assert hw["b_rx_orders"] == hw["orders_sent"] - hw["spec_poison"]
    ha = [await b.rd(0x150 + i) for i in range(7)]
    hb = [await b.rd(0x158 + i) for i in range(7)]
    assert ha[0] == hw["orders_sent"] and hb[0] == hw["b_rx_orders"]
    bins = [await b.rd(0x400 + i) for i in range(256)]
    assert sum(bins) == ha[0]
    assert hw["seq_gaps"] >= 60 // 11
    dut._log.info(f"loop: orders {hw['orders_sent']} back {hw['b_rx_orders']} A min/max {ha[3]}/{ha[4]} "
                  f"B min/max {hb[3]}/{hb[4]}")
    out = os.environ.get("B58A_LOOP_OUT")
    if out:
        with open(out, "w") as f:
            json.dump({"orders": hw["orders_sent"], "poisoned": hw["spec_poison"], "cancels": hw["spec_cancel"],
                       "back_at_b": hw["b_rx_orders"], "hist_a": {"count": ha[0], "min": ha[3], "max": ha[4]},
                       "hist_b": {"count": hb[0], "min": hb[3], "max": hb[4]}, "loop_delay_cycles_each_way": b.loop_delay,
                       "bins_a_nonzero": {i: v for i, v in enumerate(bins) if v}}, f, indent=1)


@cocotb.test()
async def mdio_read_write(dut):
    """Clause 22: a read of register 2 of PHY 1 from a model PHY that answers on the last 16 rising edges of MDC,
    and the header bits the master sent (start, opcode, addresses) checked edge by edge."""
    b = Bench(dut)
    await b.start()
    d = dut
    val = 0x1234
    seen: list[int] = []

    async def phy():
        prev, n = 0, 0
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            mdc = int(d.a_mdc.value)
            rising = mdc and not prev
            prev = mdc
            if rising:
                seen.append(int(d.a_mdio_o.value) if not int(d.a_mdio_t.value) else -1)
                n += 1
            await RisingEdge(d.clk)  # leave the read-only phase, then drive the bit for the next edge
            k = n - 48
            d.a_mdio_i.value = (val >> (15 - k)) & 1 if 0 <= k < 16 else 1

    cocotb.start_soon(phy())
    await b.wr(0x180, (1 << 30) | (1 << 21) | (2 << 16))
    await b.idle(10)
    while (await b.rd(0x181)) >> 31:
        await b.idle(50)
    v = (await b.rd(0x181)) & 0xFFFF
    hdr = "".join("z" if x < 0 else str(x) for x in seen[:48])
    assert hdr == "1" * 32 + "01" + "10" + "00001" + "00010" + "zz" + "z" * 12 or hdr.startswith("1" * 32 + "01100000100010"), hdr
    assert v == val, hex(v)
