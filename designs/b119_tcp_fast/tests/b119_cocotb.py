"""cocotb bench of the TCP fast path (rtl/tcp_fast.sv) against model/tcpref.py (brief 119).

Clock numbering: inputs set after tick N are sampled by edge N+1, which is the block's "edge 0" for a `go` set then. Registered outputs sampled after
tick N+k are what edge k produced: segment word k is visible after tick N+k. `Bench.go_cyc` is the cycle number of the edge that sampled go.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.utils import get_sim_time

from designs.b110_itch_ouch.model import proto
from designs.b110_itch_ouch.model.ref import Cfg
from designs.b119_tcp_fast.model import orders, tcpref
from designs.b119_tcp_fast.model.tcpref import Conn, FastModel
from designs.b119_tcp_fast.tests.netsim import Net

PERIOD_PS = 6206
REC: dict = {}
# register map (tcp_fast.sv)
CTRL, DMAC_HI, DMAC_LO, SMAC_HI, SMAC_LO, SIP, DIP, PORTS, TTL_MSS, SND_NXT, SND_UNA, SND_WND, RCV_NXT, RCV_WND, IP_ID, STALE_LIMIT = range(16)
CNT_BASE, CLR_CNT = 16, 31


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.cyc = 0
        self.frames: list[dict] = []
        self.recs: list[dict] = []
        self.refusals: list[tuple] = []
        self.lates: list[int] = []
        self._cur = None
        self.model = FastModel()
        self.cfg = Cfg()
        self.rng = random.Random(1)
        self._t = -1
        self.hooks: list = []

    async def start(self, conn: Conn | None = None):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, PERIOD_PS, unit="ps").start())
        for n in ("go", "go_spec", "commit", "abort", "sw_we"):
            getattr(d, n).value = 0
        for n in ("f_sym", "f_px", "f_qty", "f_ref", "sw_waddr", "sw_wdata", "sw_raddr"):
            getattr(d, n).value = 0
        self.set_cfg()
        d.rst.value = 1
        for _ in range(4):
            await self.tick()
        d.rst.value = 0
        await self.tick()
        self.model = FastModel()
        self.frames, self.recs, self.refusals, self.lates = [], [], [], []

    def set_cfg(self):
        c, d = self.cfg, self.dut
        d.cfg_tif.value, d.cfg_display.value, d.cfg_capacity.value = ord(c.tif), ord(c.display), ord(c.capacity)
        d.cfg_ise.value, d.cfg_cross.value, d.cfg_custtype.value = ord(c.ise), ord(c.cross), ord(c.custtype)
        d.cfg_minqty.value = c.minqty

    async def tick(self):
        """One clock. Several coroutines may await it (the scenario and the software's service loop): the first to resume counts the edge and samples."""
        await RisingEdge(self.dut.clk)
        await Timer(500, unit="ps")
        t = get_sim_time("ps")
        if t != self._t:
            self._t = t
            self.cyc += 1
            self.sample()
            for h in self.hooks:
                h()

    def sample(self):
        d, c = self.dut, self.cyc
        if int(d.o_v.value):
            if int(d.o_sof.value):
                self._cur = {"cyc": c, "words": [], "keep": [], "poison": False}
            assert self._cur is not None, "o_v without a start of frame"
            self._cur["words"].append(int(d.o_d.value))
            self._cur["keep"].append(int(d.o_keep.value))
            if int(d.o_eof.value):
                self._cur["poison"] = bool(int(d.o_poison.value))
                self._cur["end"] = c
                w, k = self._cur["words"], self._cur["keep"]
                self._cur["bytes"] = b"".join(x.to_bytes(8, "little")[:bin(kk).count("1")] for x, kk in zip(w, k))
                self.frames.append(self._cur)
                self._cur = None
        else:
            assert not int(d.o_eof.value) and not int(d.o_poison.value), "eof or poison without valid"
        if int(d.rec_v.value):
            self.recs.append({"cyc": c, "seq": int(d.rec_seq.value), "len": int(d.rec_len.value), "id": int(d.rec_id.value),
                              "pay": int(d.rec_pay.value).to_bytes(64, "little")[:int(d.rec_len.value)]})
        if int(d.refuse_v.value):
            self.refusals.append((c, int(d.refuse_code.value)))
        if int(d.late.value):
            self.lates.append(c)

    # ---- register bus
    async def wr(self, addr: int, val: int):
        d = self.dut
        d.sw_we.value, d.sw_waddr.value, d.sw_wdata.value = 1, addr, val & 0xFFFFFFFF
        await self.tick()
        d.sw_we.value = 0

    async def rd(self, addr: int) -> int:
        d = self.dut
        d.sw_raddr.value = addr
        await self.tick()
        await self.tick()
        return int(d.sw_rdata.value)

    async def configure(self, conn: Conn, snd_nxt=1000, snd_una=1000, snd_wnd=65535, rcv_nxt=5000, rcv_wnd=32768, ip_id=7, stale_limit=0, arm=True):
        """Software's hand-over: write the connection, then arm (the template is built two edges later) and wait for valid."""
        m = self.model
        m.conn = conn
        await self.wr(DMAC_HI, int.from_bytes(conn.dmac[:2], "big"))
        await self.wr(DMAC_LO, int.from_bytes(conn.dmac[2:], "big"))
        await self.wr(SMAC_HI, int.from_bytes(conn.smac[:2], "big"))
        await self.wr(SMAC_LO, int.from_bytes(conn.smac[2:], "big"))
        await self.wr(SIP, conn.sip)
        await self.wr(DIP, conn.dip)
        await self.wr(PORTS, (conn.sport << 16) | conn.dport)
        await self.wr(TTL_MSS, (conn.mss << 16) | conn.ttl)
        await self.set_state(snd_nxt, snd_una, snd_wnd, rcv_nxt, rcv_wnd, ip_id, stale_limit)
        if arm:
            await self.arm()

    async def set_state(self, snd_nxt=None, snd_una=None, snd_wnd=None, rcv_nxt=None, rcv_wnd=None, ip_id=None, stale_limit=None):
        m = self.model
        for reg, name, val in ((SND_NXT, "snd_nxt", snd_nxt), (SND_UNA, "snd_una", snd_una), (SND_WND, "snd_wnd", snd_wnd), (RCV_NXT, "rcv_nxt", rcv_nxt),
                               (RCV_WND, "rcv_wnd", rcv_wnd), (IP_ID, "ip_id", ip_id), (STALE_LIMIT, "stale_limit", stale_limit)):
            if val is None:
                continue
            await self.wr(reg, val)
            setattr(m, name, val)
            if reg in (SND_UNA, SND_WND, RCV_NXT, RCV_WND):
                m.refreshed_at = self.cyc

    async def arm(self):
        await self.wr(CTRL, 1)
        self.model.arm_req, self.model.valid = True, False
        self.model.refreshed_at = self.cyc
        self.model.counters["build"] += 1
        for _ in range(4):
            await self.tick()
        self.model.valid = True
        assert (await self.rd(CTRL)) & 3 == 3, "armed but not valid"

    async def disarm(self):
        await self.wr(CTRL, 0)
        self.model.arm_req = False

    # ---- orders
    async def fire(self, f: dict | None = None, spec: bool = False, commit_at: int | None = None, abort_at: int | None = None, min_k: int = 1,
                   budget: int = 40, cfg_at: tuple | None = None) -> dict:
        """Present one order for one clock (go) and, at the given offsets in edges from go, commit and abort. Runs until the block is idle again
        (and at least to the last offset). cfg_at=(k, {name: value}) changes the static configuration at edge k."""
        d = self.dut
        f = f or orders.random_order(self.rng)
        pay = orders.payload(f["ref"], f["qty"], f["sym"], f["px"], self.cfg)
        sym = int.from_bytes(proto.alpha(f["sym"], 8), "big") if isinstance(f["sym"], str) else int.from_bytes(f["sym"], "big")
        nf0, nr0, nl0 = len(self.frames), len(self.refusals), len(self.lates)
        go_clk = self.cyc + 1
        min_k = max(min_k, abort_at or 0, commit_at or 0, cfg_at[0] if cfg_at else 0)
        for k in range(budget):
            d.go.value = 1 if k == 0 else 0
            d.go_spec.value = int(spec) if k == 0 else 0
            if k == 0:
                d.f_sym.value, d.f_px.value, d.f_qty.value, d.f_ref.value = sym, f["px"], f["qty"], f["ref"]
            d.commit.value = 1 if commit_at == k else 0
            d.abort.value = 1 if abort_at == k else 0
            if cfg_at and cfg_at[0] == k:
                for name, v in cfg_at[1].items():
                    getattr(d, name).value = v
            await self.tick()
            if k >= min_k and int(d.busy.value) == 0:
                break
        for n in ("go", "go_spec", "commit", "abort"):
            getattr(d, n).value = 0
        return {"go_clk": go_clk, "pay": pay, "frames": self.frames[nf0:], "refusals": self.refusals[nr0:], "lates": self.lates[nl0:]}

    async def order(self, f: dict | None = None, **kw) -> dict:
        """fire() plus the model's prediction made before the order: the refusal it should get and the segment it should produce."""
        m = self.model
        f = f or orders.random_order(self.rng)
        pay = orders.payload(f["ref"], f["qty"], f["sym"], f["px"], self.cfg)
        go_clk = self.cyc + 1
        pre = {"ref": m.refusal(go_clk), "seg": m.segment(pay), "snd_nxt": m.snd_nxt, "id": m.ip_id}
        e = await self.fire(f, **kw)
        e.update(pre)
        e["spec"], e["commit_at"], e["abort_at"] = kw.get("spec", False), kw.get("commit_at"), kw.get("abort_at")
        return e

    async def counters(self) -> dict:
        return {name: await self.rd(CNT_BASE + i) for i, name in enumerate(tcpref.COUNTERS)}

    async def idle(self, n: int = 20):
        for _ in range(n):
            await self.tick()

    async def check_counters(self, why: str = ""):
        got, exp = await self.counters(), self.model.counters
        assert got == exp, f"counters {why}: got {got} expected {exp}"


def check_segment(b: Bench, exp: dict, frame: dict) -> bytes:
    """A segment that left unpoisoned: bytes equal the model's, checksums valid by the receiver's rule, 15 words, timing as designed."""
    assert not frame["poison"], "segment poisoned"
    assert frame["bytes"] == exp["seg"], f"bytes differ:\n got {frame['bytes'].hex()}\n exp {exp['seg'].hex()}"
    p = tcpref.parse(frame["bytes"])
    assert p.ok and p.payload == exp["pay"] and p.seq == exp["snd_nxt"] and p.ident == exp["id"]
    assert frame["cyc"] == exp["go_clk"] and frame["end"] == exp["go_clk"] + 14 and len(frame["words"]) == 15, (frame["cyc"], frame["end"], exp["go_clk"])
    return frame["bytes"]


REFCNT = {1: "ref_arm", 2: "ref_stale", 3: "ref_win", 4: "ref_mss"}


def settle(b: Bench, e: dict) -> str:
    """Compare what the block did with the model's prediction (the rules are in docs/tcp_fast.md) and advance the model. Returns the outcome."""
    m, c = b.model, b.model.counters
    go, spec, ca, ab = e["go_clk"], e["spec"], e["commit_at"], e["abort_at"]
    if ab == 0:
        assert not e["frames"] and not e["refusals"] and not e["lates"], e
        c["cancel0"] += 1
        return "cancel0"
    if e["ref"]:
        assert not e["frames"] and e["refusals"] == [(go, e["ref"])], (e["ref"], e["refusals"], e["frames"])
        c[REFCNT[e["ref"]]] += 1
        if ab is not None:
            c["late"] += 1
            assert len(e["lates"]) == 1
        return f"refused{e['ref']}"
    assert len(e["frames"]) == 1 and not e["refusals"], e
    fr = e["frames"][0]
    assert fr["cyc"] == go
    if ab is not None and ab <= 14:
        assert fr["poison"] and len(fr["words"]) == ab + 1 and fr["end"] == go + ab, (ab, len(fr["words"]), fr["poison"])
        assert fr["bytes"] == e["seg"][:len(fr["bytes"])] and not e["lates"]
        c["poison"] += 1
        c["abort"] += 1
        return "aborted"
    if spec and (ca is None or ca > 14):
        assert fr["poison"] and fr["bytes"] == e["seg"] and fr["end"] == go + 14
        c["poison"] += 1
        c["nov"] += 1
        out = "noverdict"
    else:
        check_segment(b, e, fr)
        m.complete(e["pay"])
        out = "sent"
    if ab is not None:
        c["late"] += 1
        assert len(e["lates"]) == 1
    return out


async def reset_bench(dut, conn=None, **kw) -> Bench:
    b = Bench(dut)
    await b.start()
    await b.configure(conn or Conn(), **kw)
    return b


def rand_conn(rng: random.Random) -> Conn:
    return Conn(dmac=rng.randbytes(6), smac=rng.randbytes(6), sip=rng.getrandbits(32), dip=rng.getrandbits(32), sport=rng.getrandbits(16), dport=rng.getrandbits(16),
                ttl=rng.choice([1, 64, 255, rng.getrandbits(8)]), mss=rng.choice([59, 1460, 0xFFFF]))


@cocotb.test()
async def t_smoke(dut):
    b = await reset_bench(dut)
    for _ in range(5):
        e = await b.order()
        assert settle(b, e) == "sent"
    assert len(b.recs) == 5 and [r["seq"] for r in b.recs] == [1000 + 59 * i for i in range(5)]
    await b.check_counters("smoke")


@cocotb.test()
async def t_random_segments(dut):
    """Random connections, states (sequence numbers near the wrap, extreme window, identification near the wrap) and orders: every byte equals the model's."""
    b = Bench(dut)
    await b.start()
    rng = b.rng = random.Random(2024)
    n = 0
    for blk in range(30):
        st = {"snd_nxt": rng.choice([rng.getrandbits(32), 0xFFFFFFFF - 59 * rng.randrange(0, 5) - rng.randrange(0, 59), 0, 1]),
              "rcv_nxt": rng.choice([rng.getrandbits(32), 0xFFFFFFFF, 0]), "rcv_wnd": rng.choice([0, 1, 0xFFFF, rng.getrandbits(16)]),
              "ip_id": rng.choice([rng.getrandbits(16), 0xFFFF, 0xFFFE, 0])}
        st["snd_una"] = st["snd_nxt"]
        await b.configure(rand_conn(rng), snd_wnd=0xFFFFFFFF, **st)
        for _ in range(15):
            e = await b.order(orders.random_order(rng))
            assert settle(b, e) == "sent"
            n += 1
    assert n == 450
    await b.check_counters("random")
    REC["random_segments"] = n


@cocotb.test()
async def t_checksum_corners(dut):
    """Fields chosen to make the sums wrap more than once (all-ones fields), and a payload of all-ones bytes."""
    b = await reset_bench(dut, Conn(sip=0xFFFFFFFF, dip=0xFFFFFFFF, sport=0xFFFF, dport=0xFFFF, ttl=255, dmac=b"\xff" * 6, smac=b"\xff" * 6),
                          snd_nxt=0xFFFFFFFF, snd_una=0xFFFFFFFF, rcv_nxt=0xFFFFFFFF, rcv_wnd=0xFFFF, ip_id=0xFFFF, snd_wnd=0xFFFFFFFF)
    for f in ({"ref": 0xFFFFFFFF, "qty": 0xFFFFFFFF, "sym": b"\xff" * 8, "px": 0xFFFFFFFF}, {"ref": 0, "qty": 0, "sym": b"\0" * 8, "px": 0},
              {"ref": 0x0F0F0F0F, "qty": 1, "sym": "A", "px": 0x80000000}):
        e = await b.order(f)
        assert settle(b, e) == "sent"
        p = tcpref.parse(e["frames"][0]["bytes"])
        assert p.ok
    b.cfg.minqty, b.cfg.tif, b.cfg.custtype = 0xFFFFFFFF, "\x7f", "\x7f"
    b.set_cfg()
    for _ in range(3):
        e = await b.order()
        assert settle(b, e) == "sent"
    await b.check_counters("corners")


@cocotb.test()
async def t_timing(dut):
    """Latencies in clocks from the clock go is presented (the clock of the order frame's first word in brief 110 is the next one)."""
    b = await reset_bench(dut)
    e = await b.order(orders.random_order(b.rng))
    fr = e["frames"][0]
    go = e["go_clk"]
    word_of = lambda w: fr["cyc"] + w - go
    rows = {"first_byte_clocks_after_go": fr["cyc"] - go + 1, "ip_checksum_field_clocks_after_go": word_of(3) + 1, "tcp_checksum_field_clocks_after_go": word_of(6) + 1,
            "last_byte_clocks_after_go": fr["end"] - go + 1, "segment_words": len(fr["words"]), "segment_bytes": len(fr["bytes"])}
    assert rows["first_byte_clocks_after_go"] == 1 and rows["tcp_checksum_field_clocks_after_go"] == 7 and rows["last_byte_clocks_after_go"] == 15
    assert rows["segment_words"] == 15 and rows["segment_bytes"] == 113
    # the frame builder of brief 110 alone shows its first word one clock after go too: the headers add no latency to the first byte
    REC["timing"] = rows
    settle(b, e)
    # back to back: the next order is accepted at the very next clock after the last word
    e1 = await b.order()
    assert settle(b, e1) == "sent"
    e2 = await b.order()
    assert settle(b, e2) == "sent"
    assert e2["frames"][0]["cyc"] == e1["frames"][0]["end"] + 1
    REC["timing"]["back_to_back_clocks_between_segment_starts"] = e2["frames"][0]["cyc"] - e1["frames"][0]["cyc"]
    assert REC["timing"]["back_to_back_clocks_between_segment_starts"] == 15


@cocotb.test()
async def t_abort_every_offset(dut):
    """An abort at every edge from the go edge to two after the last word. Early aborts poison the frame and consume nothing (the next segment has the same
    sequence number and identification); the abort in the go edge cancels the go; later ones find nothing in flight. Back to back after each."""
    b = await reset_bench(dut)
    outcomes = {}
    for ab in range(0, 18):
        before = (b.model.snd_nxt, b.model.ip_id)
        e = await b.order(abort_at=ab, min_k=18)
        out = settle(b, e)
        outcomes[ab] = out
        if out in ("cancel0", "aborted"):
            assert (b.model.snd_nxt, b.model.ip_id) == before
        e2 = await b.order()                                   # the very next edge: a fresh order is accepted and byte exact
        assert e2["snd_nxt"] == b.model.snd_nxt
        assert settle(b, e2) == "sent"
        if out in ("cancel0", "aborted"):
            assert e2["frames"][0]["bytes"][38:42] == before[0].to_bytes(4, "big") and e2["frames"][0]["bytes"][18:20] == before[1].to_bytes(2, "big")
    assert outcomes[0] == "cancel0" and all(outcomes[k] == "aborted" for k in range(1, 15)) and outcomes[15] == outcomes[16] == outcomes[17] == "sent"
    await b.check_counters("abort offsets")
    REC["abort_offsets"] = outcomes


@cocotb.test()
async def t_abort_without_gap(dut):
    """An aborted segment followed by a go at the very next edge, with the abort at each offset: the frame builder inside is released with the segment."""
    b = await reset_bench(dut)
    for ab in range(1, 15):
        e = await b.order(abort_at=ab)
        assert settle(b, e) == "aborted"
        e2 = await b.order()
        assert settle(b, e2) == "sent"
        assert e2["frames"][0]["cyc"] == e["frames"][0]["end"] + 1
    await b.check_counters("abort b2b")


@cocotb.test()
async def t_speculative_verdicts(dut):
    """Speculative starts: commit at each edge 0..17 (a commit after the last word is too late: poisoned, counted), no verdict at all, abort after commit."""
    b = await reset_bench(dut)
    res = {}
    for ca in [None] + list(range(0, 18)):
        e = await b.order(spec=True, commit_at=ca, min_k=18)
        out = settle(b, e)
        res[ca] = out
        assert out == ("noverdict" if (ca is None or ca > 14) else "sent"), (ca, out)
    e = await b.order(spec=True, commit_at=3, abort_at=6)
    assert settle(b, e) == "aborted"
    e = await b.order(spec=False)                                # not speculative: no verdict needed
    assert settle(b, e) == "sent"
    await b.check_counters("speculative")
    assert b.model.counters["nov"] == 4


@cocotb.test()
async def t_refusals(dut):
    """Not armed, state not valid, stale, window closed (the exact boundary), MSS too small, busy, and an abort in the go edge."""
    b = Bench(dut)
    await b.start()
    # not armed (nothing configured yet)
    e = await b.order()
    assert settle(b, e) == "refused1"
    await b.configure(Conn(), snd_nxt=1000, snd_una=1000, snd_wnd=59, rcv_nxt=5, rcv_wnd=100, ip_id=3, arm=False)
    assert settle(b, await b.order()) == "refused1"
    await b.arm()
    # window: exactly one segment fits
    assert settle(b, await b.order()) == "sent"
    assert settle(b, await b.order()) == "refused3"
    await b.set_state(snd_una=1059)                           # acknowledged: it fits again
    assert settle(b, await b.order()) == "sent"
    await b.set_state(snd_una=1118, snd_wnd=58)               # window below one segment
    assert settle(b, await b.order()) == "refused3"
    await b.set_state(snd_wnd=117)                            # flight 0 (nxt 1118, una 1118)
    assert settle(b, await b.order()) == "sent"               # 59 <= 117
    await b.set_state(snd_wnd=117)
    assert settle(b, await b.order()) == "refused3"           # flight 59 + 59 = 118 > 117
    await b.set_state(snd_wnd=118)
    assert settle(b, await b.order()) == "sent"
    # a state whose SND.UNA is ahead of SND.NXT is refused (the flight would be huge)
    await b.set_state(snd_una=b.model.snd_nxt + 1, snd_wnd=0xFFFFFFFF)
    assert settle(b, await b.order()) == "refused3"
    await b.set_state(snd_una=b.model.snd_nxt)
    # MSS
    await b.wr(TTL_MSS, (58 << 16) | 64)
    b.model.conn.mss, b.model.conn.ttl, b.model.valid = 58, 64, False
    assert settle(b, await b.order()) == "refused2"           # a static write makes the state invalid until the arm write
    await b.arm()
    assert settle(b, await b.order()) == "refused4"
    await b.wr(TTL_MSS, (59 << 16) | 64)
    b.model.conn.mss, b.model.valid = 59, False
    await b.arm()
    assert settle(b, await b.order()) == "sent"
    # stale: limit 40 clocks; the live registers are not refreshed
    await b.set_state(stale_limit=40)
    await b.set_state(snd_una=b.model.snd_nxt)                # a refresh
    assert settle(b, await b.order()) == "sent"               # about 17 clocks old
    await b.set_state(snd_una=b.model.snd_nxt)
    refresh = b.model.refreshed_at
    await b.idle(40 - (b.cyc - refresh))                       # age exactly the limit when go is sampled (not stale)
    e = await b.order()
    assert (e["go_clk"] - refresh - 1) <= 40 and settle(b, e) == "sent"
    await b.set_state(snd_una=b.model.snd_nxt)
    refresh = b.model.refreshed_at
    await b.idle(41 - (b.cyc - refresh))                       # age exactly limit + 1
    e = await b.order()
    assert (e["go_clk"] - refresh - 1) == 41 and settle(b, e) == "refused2"
    await b.set_state(stale_limit=0)                          # limit 0 disables the check
    assert settle(b, await b.order()) == "sent"
    # busy: a second go in the middle of a segment is dropped and counted; the segment is not disturbed
    d = dut
    e = await b.order(f=None, min_k=1)                         # one clean segment to compare
    settle(b, e)
    f1, f2 = orders.random_order(b.rng), orders.random_order(b.rng)
    pay1 = orders.payload(f1["ref"], f1["qty"], f1["sym"], f1["px"])
    exp_seg = b.model.segment(pay1)
    seq0 = b.model.snd_nxt
    n0 = len(b.refusals)
    go_clk = b.cyc + 1
    d.go.value = 1
    d.f_sym.value, d.f_px.value, d.f_qty.value, d.f_ref.value = int.from_bytes(proto.alpha(f1["sym"], 8), "big"), f1["px"], f1["qty"], f1["ref"]
    await b.tick()
    d.go.value = 0
    await b.tick()
    await b.tick()
    d.go.value = 1                                             # edge 3: the block is busy
    d.f_ref.value = f2["ref"]
    await b.tick()
    d.go.value = 0
    for _ in range(14):
        await b.tick()
    assert b.refusals[n0:] == [(go_clk + 3, 5)]
    assert b.frames[-1]["bytes"] == exp_seg and not b.frames[-1]["poison"] and b.model.snd_nxt == seq0
    b.model.complete(pay1)
    b.model.counters["busy"] += 1
    # an abort in the go edge beats a go that would be refused: nothing counted but cancel0
    await b.disarm()
    e = await b.order(abort_at=0)
    assert settle(b, e) == "cancel0"
    await b.check_counters("refusals")
    REC["refusal_codes"] = {1: "not armed", 2: "stale or not valid", 3: "window closed", 4: "MSS below one segment", 5: "busy"}


@cocotb.test()
async def t_register_semantics(dut):
    """What a user could guess wrong about the bus: read back, writes while busy, live registers mid-segment, unmapped addresses, counters clear."""
    b = await reset_bench(dut, Conn(), snd_nxt=777, snd_una=700, snd_wnd=5000, rcv_nxt=99, rcv_wnd=1234, ip_id=42, stale_limit=0)
    c = b.model.conn
    expect = {DMAC_HI: int.from_bytes(c.dmac[:2], "big"), DMAC_LO: int.from_bytes(c.dmac[2:], "big"), SMAC_HI: int.from_bytes(c.smac[:2], "big"),
              SMAC_LO: int.from_bytes(c.smac[2:], "big"), SIP: c.sip, DIP: c.dip, PORTS: (c.sport << 16) | c.dport, TTL_MSS: (c.mss << 16) | c.ttl, SND_NXT: 777,
              SND_UNA: 700, SND_WND: 5000, RCV_NXT: 99, RCV_WND: 1234, IP_ID: 42, STALE_LIMIT: 0}
    for a, v in expect.items():
        assert await b.rd(a) == v, a
    assert await b.rd(CTRL) == 3
    for a in (30, 17 + 20 - 20 + 14):       # 30 is unmapped; 31 reads 0 as well
        pass
    assert await b.rd(30) == 0 and await b.rd(31) == 0
    await b.wr(30, 0xDEAD)
    assert await b.rd(30) == 0
    # while a segment is in flight: static writes, SND_NXT, IP_ID and an arm write are ignored and counted; live writes take effect for the next one
    f = orders.random_order(b.rng)
    pay = orders.payload(f["ref"], f["qty"], f["sym"], f["px"])
    exp_seg = b.model.segment(pay)
    d = dut
    d.go.value = 1
    d.f_sym.value, d.f_px.value, d.f_qty.value, d.f_ref.value = int.from_bytes(proto.alpha(f["sym"], 8), "big"), f["px"], f["qty"], f["ref"]
    await b.tick()
    d.go.value = 0
    await b.tick()
    ign = 0
    for a, v in ((DMAC_LO, 0x11111111), (SIP, 0x22222222), (PORTS, 0x33334444), (TTL_MSS, 0x00050001), (SND_NXT, 12345), (IP_ID, 9999)):
        await b.wr(a, v)
        ign += 1
    await b.wr(CTRL, 1)                                  # an arm write while busy: ignored
    ign += 1
    await b.wr(RCV_NXT, 5555)                            # live: accepted at once, but this segment captured its ACK number at the go edge
    await b.wr(RCV_WND, 4321)
    await b.wr(CTRL, 0)                                  # disarm while busy: the segment in flight completes
    for _ in range(12):
        await b.tick()
    fr = b.frames[-1]
    assert fr["bytes"] == exp_seg and not fr["poison"], "a write during the segment changed it"
    b.model.complete(pay)
    b.model.rcv_nxt, b.model.rcv_wnd, b.model.arm_req = 5555, 4321, False
    b.model.counters["wrign"] += ign
    assert await b.rd(DMAC_LO) == expect[DMAC_LO] and await b.rd(SIP) == c.sip and await b.rd(SND_NXT) == 777 + 59 and await b.rd(IP_ID) == 43
    assert await b.rd(RCV_NXT) == 5555
    assert await b.rd(CTRL) == 2                                      # not armed, valid, idle
    await b.check_counters("registers")
    await b.arm()                                                     # re-armed: the next segment uses the new ACK number and window
    e = await b.order()
    assert settle(b, e) == "sent"
    assert tcpref.parse(e["frames"][0]["bytes"]).ack == 5555 and tcpref.parse(e["frames"][0]["bytes"]).win == 4321
    await b.wr(CLR_CNT, 0)
    for k in b.model.counters:
        b.model.counters[k] = 0
    await b.check_counters("cleared")
    # a static write invalidates the template until the next arm; the arm write rebuilds it and the new fields appear
    await b.wr(SIP, 0x0A0A0A0A)
    b.model.conn.sip, b.model.valid = 0x0A0A0A0A, False
    assert await b.rd(CTRL) == 1
    e = await b.order()
    assert settle(b, e) == "refused2"
    await b.arm()
    e = await b.order()
    assert settle(b, e) == "sent" and tcpref.parse(e["frames"][0]["bytes"]).sip == 0x0A0A0A0A
    # SND_NXT written while idle takes effect (software returns the sequence space)
    await b.set_state(snd_nxt=2 ** 32 - 10, snd_una=2 ** 32 - 10)
    e = await b.order()
    assert settle(b, e) == "sent" and b.model.snd_nxt == 49


@cocotb.test()
async def t_config_change_poisons(dut):
    """The static order configuration (cfg_*) must not change while a segment is in flight: the check of the payload sum against the bytes sent poisons it."""
    b = await reset_bench(dut)
    e = await b.order(cfg_at=(3, {"cfg_tif": ord("0")}))
    fr = e["frames"][0]
    assert fr["poison"] and len(fr["words"]) == 15
    b.model.counters["poison"] += 1
    b.model.counters["sumerr"] += 1
    e = await b.order(cfg_at=(0, {"cfg_tif": ord("3")}))      # restored in the go edge: fine
    assert settle(b, e) == "sent"
    b.cfg.tif = "3"
    b.set_cfg()
    e = await b.order()
    assert settle(b, e) == "sent"
    await b.check_counters("config change")


@cocotb.test()
async def t_sequence_continuity_with_software(dut):
    """Software takes the sequence space (disarm, wait for idle, read SND.NXT), sends bytes of its own, gives it back (write SND.NXT, arm): the stream is gapless."""
    b = await reset_bench(dut, Conn(), snd_nxt=0xFFFFFF00, snd_una=0xFFFFFF00, snd_wnd=0xFFFFFFF0)
    stream = []                                   # (seq, length) of everything sent by either
    sw_seq = 0xFFFFFF00
    for rnd in range(12):
        e = await b.order()
        assert settle(b, e) == "sent"
        stream.append((e["snd_nxt"], 59))
        if rnd % 3 == 2:
            await b.disarm()
            while (await b.rd(CTRL)) & 4:
                pass
            hw = await b.rd(SND_NXT)
            assert hw == b.model.snd_nxt
            n = 3 + rnd                            # software's own segment (a heartbeat, a login ...)
            stream.append((hw, n))
            b.model.snd_nxt = (hw + n) & 0xFFFFFFFF
            await b.wr(SND_NXT, b.model.snd_nxt)
            await b.set_state(snd_una=b.model.snd_nxt)
            await b.arm()
    nxt = 0xFFFFFF00
    for seq, n in stream:
        assert seq == nxt, (hex(seq), hex(nxt))
        nxt = (seq + n) & 0xFFFFFFFF
    assert nxt == b.model.snd_nxt
    assert [r["seq"] for r in b.recs] == [s for s, n in stream if n == 59]
    await b.check_counters("continuity")


@cocotb.test()
async def t_random_mix(dut):
    """A long random run: speculative and plain orders, commits and aborts at random edges, orders back to back or with gaps, window pressure, refusals."""
    b = Bench(dut)
    await b.start()
    rng = b.rng = random.Random(7)
    await b.configure(rand_conn(rng), snd_nxt=0xFFFFF000, snd_una=0xFFFFF000, snd_wnd=400, rcv_nxt=1, rcv_wnd=100, ip_id=0xFFF0)
    seen = {}
    for i in range(500):
        r = rng.random()
        spec = rng.random() < 0.5
        ca = rng.choice([None, 0, 1, 2, 5, 9, 13, 14, 15, 16]) if spec else rng.choice([None, 3])
        ab = rng.choice([None, None, None, 0, 1, 3, 7, 13, 14, 15, 16]) if r < 0.4 else None
        if rng.random() < 0.15:
            await b.set_state(snd_una=b.model.snd_nxt - rng.choice([0, 59, 118]) & 0xFFFFFFFF, snd_wnd=rng.choice([58, 59, 118, 177, 400]))
        if rng.random() < 0.15:
            await b.set_state(rcv_nxt=rng.getrandbits(32), rcv_wnd=rng.getrandbits(16))
        if rng.random() < 0.2:
            await b.idle(rng.randrange(1, 20))
        e = await b.order(orders.random_order(rng), spec=spec, commit_at=ca, abort_at=ab, min_k=17)
        out = settle(b, e)
        seen[out] = seen.get(out, 0) + 1
        if out == "refused3" and rng.random() < 0.7:
            await b.set_state(snd_una=b.model.snd_nxt, snd_wnd=rng.choice([118, 400]))        # the peer acknowledged and reopened the window
    await b.check_counters("random mix")
    assert {"sent", "aborted", "noverdict", "cancel0"} <= set(seen) and any(k.startswith("refused") for k in seen), seen
    REC["random_mix_outcomes"] = seen


# ---- end to end: the software owner and the software exchange around the real block
class RtlBus:
    def __init__(self, b: Bench):
        self.b = b

    async def write(self, addr: int, val: int) -> None:
        await self.b.wr(addr, val)

    async def read(self, addr: int) -> int:
        return await self.b.rd(addr)


class RtlNet(Net):
    """Net with the real block: its frames go to the exchange (a poisoned one is dropped, as the receiver's MAC would), its records to the owner."""

    def __init__(self, b: Bench, **kw):
        super().__init__(bus=RtlBus(b), **kw)
        self.b, self.fwd, self.rec_i, self.poisoned = b, 0, 0, 0
        self.stop = False
        b.hooks.append(self._hook)

    def _hook(self) -> None:
        b = self.b
        while self.fwd < len(b.frames):
            fr = b.frames[self.fwd]
            self.fwd += 1
            if fr["poison"]:
                self.poisoned += 1
            else:
                self.world.send("ex", fr["bytes"])
        while self.rec_i < len(b.recs):
            self.owner.on_hw_record(b.recs[self.rec_i])
            self.rec_i += 1
        self.now = b.cyc
        self.world.step_to(b.cyc)
        self.ex.poll(b.cyc)

    async def wait(self) -> int:
        await self.b.tick()
        return self.b.cyc

    async def service_loop(self) -> None:
        while not self.stop:
            await self.b.tick()
            await self.owner.service(self.b.cyc)


async def e2e_start(dut, **kw):
    b = Bench(dut)
    await b.start()
    net = RtlNet(b, **kw)
    await net.start(stale_limit=0)
    cocotb.start_soon(net.service_loop())
    return b, net


def hw_payload(frame: bytes, dest: str, idx: int) -> bool:
    return dest == "ex" and tcpref.parse(frame).payload.startswith(b"\x00\x39U")


async def send_orders(b: Bench, refs, spacing: int = 30, **kw) -> list[int]:
    """Present orders with strictly increasing numbers; returns the numbers of those the block sent unpoisoned (the others were refused or aborted)."""
    sent = []
    for r in refs:
        n0 = len(b.recs)
        await b.fire({"ref": r, "qty": 100 + r, "sym": "AAA", "px": 1_000_000 + r}, **kw)
        if len(b.recs) > n0:
            sent.append(r)
        await b.idle(spacing)
    return sent


def check_session(b: Bench, net: RtlNet, sent: list[int], extra_bytes_ok: bool = True) -> None:
    """The invariants of every end-to-end run: one gapless sequence space across both senders, the exchange has every byte once and in order, every sent
    order was answered, nothing outstanding, no sequence disagreement between software and hardware."""
    o, ex = net.owner, net.ex
    log = sorted(o.sent_log, key=lambda x: (x[0] - o.iss) & 0xFFFFFFFF)
    nxt = (o.iss + 1) & 0xFFFFFFFF                      # after the SYN
    for seq, d in log:
        assert seq == nxt, f"gap or overlap in the sequence space at {seq}, expected {nxt}"
        nxt = (seq + len(d)) & 0xFFFFFFFF
    assert nxt == o.snd_nxt
    assert bytes(ex.stream_in) == b"".join(d for _, d in log), "the exchange's stream differs from what was sent"
    assert [x["userref"] for x in o.responses] == sent and all(x["type"] == "A" for x in o.responses)
    assert [x["userref"] for x in ex.orders] == sent and ex.dup_orders == 0
    assert o.snd_una == o.snd_nxt and not o.rtx and not o.errors, (o.snd_una, o.snd_nxt, o.rtx, o.errors)
    hw_segments = [d for _, d in log if d.startswith(b"\x00\x39U")]
    assert len(hw_segments) == len(sent) == o.hw_sends == len(b.recs)


@cocotb.test()
async def t_e2e_session(dut):
    """Handshake, login, hand-over, twelve orders, replies, acknowledgements flowing back into the block's window registers."""
    b, net = await e2e_start(dut, hb=10 ** 6)
    assert net.owner.hw_armed and net.ex.logged_in
    sent = await send_orders(b, range(1, 13), spacing=40)
    await b.idle(300)
    check_session(b, net, sent)
    assert len(sent) == 12 and net.owner.stats["retransmits"] == 0 and net.poisoned == 0
    assert await b.rd(SND_UNA) == net.owner.snd_una == net.owner.snd_nxt and await b.rd(SND_NXT) == net.owner.snd_nxt
    assert await b.rd(RCV_NXT) == net.owner.rcv_nxt
    cnt = await b.counters()
    assert cnt["sent"] == 12 and cnt["poison"] == 0
    REC["e2e_session"] = {"orders": 12, "exchange_replies": len(net.owner.responses), "software_pure_acks": net.owner.stats["pure_acks"], "clocks": b.cyc}


@cocotb.test()
async def t_e2e_dropped_segment_retransmitted_by_software(dut):
    """The network loses the fourth fast-path segment: the exchange sees a gap and duplicates acknowledgements; the owner's timer retransmits from the record."""
    seen = {"n": 0}

    def drop(frame, dest, idx):
        if hw_payload(frame, dest, idx):
            seen["n"] += 1
            return seen["n"] == 4
        return False
    b, net = await e2e_start(dut, hb=10 ** 6, drop=drop)
    sent = await send_orders(b, range(1, 9), spacing=40)
    await b.idle(2500)
    check_session(b, net, sent)
    assert len(net.world.dropped) == 1 and net.owner.stats["retransmits"] >= 1 and net.ex.stats["out_of_order"] >= 1
    REC["e2e_drop"] = {"retransmits": net.owner.stats["retransmits"], "exchange_out_of_order": net.ex.stats["out_of_order"], "dup_acks_at_owner": net.owner.stats["dup_acks"]}


@cocotb.test()
async def t_e2e_heartbeats_take_and_give_back(dut):
    """Idle spells make the software send client heartbeats: it disarms the block, takes SND.NXT, sends, hands it back. Orders on both sides of each."""
    b, net = await e2e_start(dut, hb=600)
    sent = []
    for burst in range(3):
        sent += await send_orders(b, range(100 * burst + 1, 100 * burst + 4), spacing=60)
        await b.idle(2000)
    await b.idle(300)
    check_session(b, net, sent)
    assert net.owner.takeovers >= 4 and net.ex.client_hbs >= 4 and net.owner.server_hbs >= 2
    assert await b.rd(SND_NXT) == net.owner.snd_nxt
    REC["e2e_heartbeat"] = {"takeovers": net.owner.takeovers, "client_heartbeats_at_exchange": net.ex.client_hbs, "server_heartbeats_at_owner": net.owner.server_hbs}


@cocotb.test()
async def t_e2e_aborted_orders_never_reach_the_peer(dut):
    """Speculative orders, every third aborted: the poisoned frames are dropped by the receiver's MAC, the peer's TCP state is untouched, the sequence space has no hole."""
    b, net = await e2e_start(dut, hb=10 ** 6)
    sent = []
    for r in range(1, 19):
        ab = 4 if r % 3 == 0 else None
        sent += await send_orders(b, [r], spacing=25, spec=True, commit_at=None if ab else 3, abort_at=ab)
    await b.idle(400)
    check_session(b, net, sent)
    assert net.poisoned == 6 and len(sent) == 12 and net.ex.stats["out_of_order"] == 0 and net.ex.stats["bad_checksum"] == 0
    assert net.owner.snd_nxt == net.ex.rcv_nxt
    REC["e2e_abort"] = {"aborted": net.poisoned, "sent": len(sent), "exchange_out_of_order": net.ex.stats["out_of_order"]}


@cocotb.test()
async def t_e2e_small_window_refuses_then_recovers(dut):
    """The exchange advertises 150 bytes: two orders fit in flight. Orders presented faster than the acknowledgements are refused and counted in hardware."""
    b, net = await e2e_start(dut, hb=10 ** 6, ex_window=150)
    sent = await send_orders(b, range(1, 21), spacing=4)
    await b.idle(500)
    sent2 = await send_orders(b, range(21, 25), spacing=100)
    await b.idle(500)
    check_session(b, net, sent + sent2)
    cnt = await b.counters()
    assert cnt["ref_win"] >= 5 and cnt["ref_win"] + len(sent) + len(sent2) == 24 and len(sent2) == 4
    REC["e2e_window"] = {"presented": 24, "sent": len(sent) + len(sent2), "refused_window": cnt["ref_win"]}


@cocotb.test()
async def t_e2e_login_rejected_never_arms(dut):
    """A wrong password: the exchange refuses the login; the owner never hands the connection over, and orders are refused as not armed."""
    b = Bench(dut)
    await b.start()
    net = RtlNet(b, hb=10 ** 6)
    net.owner.password = "WRONG"
    try:
        await net.start()
    except AssertionError as e:
        assert "login rejected" in str(e)
    else:
        raise AssertionError("the login should have been rejected")
    await b.fire({"ref": 1, "qty": 1, "sym": "AAA", "px": 1})
    cnt = await b.counters()
    assert cnt["ref_arm"] == 1 and cnt["sent"] == 0 and not net.owner.hw_armed


def write_records():
    out = os.environ.get("B119_RECORD")
    if out and REC:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "bench_sim.json").write_text(json.dumps(REC, indent=2, sort_keys=True, default=str) + "\n")


@cocotb.test()
async def t_zz_write_records(dut):
    write_records()
