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

from designs.b110_itch_ouch.model.ref import Cfg
from designs.b119_tcp_fast.model import orders, tcpref
from designs.b119_tcp_fast.model.tcpref import Conn, FastModel

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
        await RisingEdge(self.dut.clk)
        await Timer(500, unit="ps")
        self.cyc += 1
        self.sample()

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
        for _ in range(4):
            await self.tick()
        self.model.valid = True
        assert (await self.rd(CTRL)) & 3 == 3, "armed but not valid"

    async def disarm(self):
        await self.wr(CTRL, 0)
        self.model.arm_req = False

    # ---- orders
    async def order(self, f: dict | None = None, spec: bool = False, commit_at: int | None = None, abort_at: int | None = None, wait: bool = True,
                    budget: int = 30) -> dict:
        """Present one order for one clock (go) and, at the stated offsets in edges from go, commit and abort. Returns what was expected."""
        d, m = self.dut, self.model
        f = f or orders.random_order(self.rng)
        pay = orders.payload(f["ref"], f["qty"], f["sym"], f["px"], self.cfg)
        sym = int.from_bytes(__import__("designs.b110_itch_ouch.model.proto", fromlist=["alpha"]).alpha(f["sym"], 8), "big") if isinstance(f["sym"], str) else int.from_bytes(f["sym"], "big")
        nf0, nr0 = len(self.frames), len(self.refusals)
        go_clk = self.cyc + 1
        exp = {"go_clk": go_clk, "pay": pay, "ref": m.refusal(go_clk), "seg": m.segment(pay), "snd_nxt": m.snd_nxt, "id": m.ip_id}
        n0 = self.cyc
        for k in range(budget):
            d.go.value = 1 if k == 0 else 0
            d.go_spec.value = int(spec) if k == 0 else 0
            if k == 0:
                d.f_sym.value, d.f_px.value, d.f_qty.value, d.f_ref.value = sym, f["px"], f["qty"], f["ref"]
            d.commit.value = 1 if commit_at == k else 0
            d.abort.value = 1 if abort_at == k else 0
            await self.tick()
            if k >= 16 and (not wait or int(d.busy.value) == 0):
                break
        for n in ("go", "go_spec", "commit", "abort"):
            getattr(d, n).value = 0
        for _ in range(2):
            await self.tick()
        exp["frames"] = self.frames[nf0:]
        exp["refusals"] = self.refusals[nr0:]
        exp["cycles"] = self.cyc - n0
        return exp

    async def counters(self) -> dict:
        return {name: await self.rd(CNT_BASE + i) for i, name in enumerate(tcpref.COUNTERS)}

    async def idle(self, n: int = 20):
        for _ in range(n):
            await self.tick()


def check_segment(b: Bench, exp: dict, frame: dict, advance: bool = True) -> bytes:
    """A segment that left unpoisoned: bytes equal the model's, checksums valid by the receiver's rule, 15 words, timing as designed."""
    assert not frame["poison"], "segment poisoned"
    assert frame["bytes"] == exp["seg"], f"bytes differ:\n got {frame['bytes'].hex()}\n exp {exp['seg'].hex()}"
    p = tcpref.parse(frame["bytes"])
    assert p.ok and p.payload == exp["pay"] and p.seq == exp["snd_nxt"] and p.ident == exp["id"]
    assert frame["cyc"] == exp["go_clk"] and frame["end"] == exp["go_clk"] + 14 and len(frame["words"]) == 15, (frame["cyc"], frame["end"], exp["go_clk"])
    if advance:
        b.model.complete(exp["pay"])
    return frame["bytes"]


async def reset_bench(dut, conn=None, **kw) -> Bench:
    b = Bench(dut)
    await b.start()
    await b.configure(conn or Conn(), **kw)
    return b


@cocotb.test()
async def t_smoke(dut):
    b = await reset_bench(dut)
    for _ in range(5):
        e = await b.order()
        assert len(e["frames"]) == 1, e
        check_segment(b, e, e["frames"][0])
    assert len(b.recs) == 5
    c = await b.counters()
    assert c["sent"] == 5, c
