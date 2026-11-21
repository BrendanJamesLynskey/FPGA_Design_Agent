"""cocotb bench of brief 110's trading path with the TCP fast path behind its risk logic (rtl/itch_ouch_tcp_top.sv), against brief 110's reference model.

ITCH messages in MoldUDP64 packets go in; every order the reference model says must leave comes out as a 113-byte TCP segment whose payload is the model's 59-byte
packet, with valid checksums and gapless sequence numbers; with speculative start the orders the risk checks refuse are started and then poisoned. The latency
from the last byte of the triggering message to the first byte of the Ethernet frame is measured here (T is the clock in which the message's last word is presented).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import COUNTERS, Cfg, Model
from designs.b119_tcp_fast.model import tcpref
from designs.b119_tcp_fast.model.tcpref import Conn

PERIOD_PS = 6206
REC: dict = {}
CTRL, DMAC_HI, DMAC_LO, SMAC_HI, SMAC_LO, SIP, DIP, PORTS, TTL_MSS, SND_NXT, SND_UNA, SND_WND, RCV_NXT, RCV_WND, IP_ID, STALE_LIMIT = range(16)
MID, TK = gen.MID, gen.TICK


class Top:
    def __init__(self, dut, cfg: Cfg, spec: bool):
        self.dut, self.cfg, self.spec = dut, cfg, spec
        self.cyc = 0
        self.segs: list[dict] = []
        self._cur = None
        self.refusals: list = []

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, PERIOD_PS, unit="ps").start())
        for n in ("s_v", "s_sof", "s_eof", "s_err", "clr_cnt", "clr_flags", "clr_book", "clr_pos", "clr_ref", "sw_we"):
            getattr(d, n).value = 0
        for n in ("s_d", "s_keep", "sw_waddr", "sw_wdata", "sw_raddr"):
            getattr(d, n).value = 0
        c = self.cfg
        w = 0
        for i in range(c.n_inst):
            w |= int.from_bytes(proto.alpha(c.watch[i], 8), "big") << (64 * i)
        d.cfg_watch.value = w
        d.cfg_thr.value, d.cfg_qty.value, d.cfg_max_qty.value, d.cfg_max_pos.value = c.thr, c.qty, c.max_qty, c.max_pos
        d.cfg_band.value, d.cfg_px_off.value, d.cfg_minqty.value = c.band, c.px_off, c.minqty
        d.cfg_tif.value, d.cfg_display.value, d.cfg_capacity.value = ord(c.tif), ord(c.display), ord(c.capacity)
        d.cfg_ise.value, d.cfg_cross.value, d.cfg_custtype.value = ord(c.ise), ord(c.cross), ord(c.custtype)
        d.cfg_arm.value, d.cfg_kill.value, d.cfg_halt_on_gap.value, d.cfg_spec.value = int(c.arm), int(c.kill), int(c.halt_on_gap), int(self.spec)
        d.rst.value = 1
        for _ in range(4):
            await self.tick()
        d.rst.value = 0
        await self.tick()
        for _ in range(2000):
            if int(d.flags.value) & 0x10:
                break
            await self.tick()
        else:
            raise AssertionError("book never became ready")
        self.segs, self.refusals = [], []

    async def tick(self):
        await RisingEdge(self.dut.clk)
        await Timer(500, unit="ps")
        self.cyc += 1
        d = self.dut
        if int(d.o_v.value):
            if int(d.o_sof.value):
                self._cur = {"cyc": self.cyc, "words": [], "keep": []}
            self._cur["words"].append(int(d.o_d.value))
            self._cur["keep"].append(int(d.o_keep.value))
            if int(d.o_eof.value):
                self._cur["poison"] = bool(int(d.o_poison.value))
                self._cur["bytes"] = b"".join(x.to_bytes(8, "little")[:bin(k).count("1")] for x, k in zip(self._cur["words"], self._cur["keep"]))
                self.segs.append(self._cur)
                self._cur = None
        if int(d.refuse_v.value):
            self.refusals.append((self.cyc, int(d.refuse_code.value)))

    async def wr(self, addr, val):
        d = self.dut
        d.sw_we.value, d.sw_waddr.value, d.sw_wdata.value = 1, addr, val & 0xFFFFFFFF
        await self.tick()
        d.sw_we.value = 0

    async def connect(self, conn: Conn, snd_nxt=1000):
        await self.wr(DMAC_HI, int.from_bytes(conn.dmac[:2], "big"))
        await self.wr(DMAC_LO, int.from_bytes(conn.dmac[2:], "big"))
        await self.wr(SMAC_HI, int.from_bytes(conn.smac[:2], "big"))
        await self.wr(SMAC_LO, int.from_bytes(conn.smac[2:], "big"))
        await self.wr(SIP, conn.sip)
        await self.wr(DIP, conn.dip)
        await self.wr(PORTS, (conn.sport << 16) | conn.dport)
        await self.wr(TTL_MSS, (conn.mss << 16) | conn.ttl)
        await self.wr(SND_NXT, snd_nxt)
        await self.wr(SND_UNA, snd_nxt)
        await self.wr(SND_WND, 0xFFFF)
        await self.wr(RCV_NXT, 777)
        await self.wr(RCV_WND, 4000)
        await self.wr(IP_ID, 1)
        await self.wr(CTRL, 1)
        for _ in range(4):
            await self.tick()

    async def send(self, pkt: bytes, idle: int = 8) -> int:
        d = self.dut
        for _ in range(idle):
            await self.tick()
        ws = proto.words(pkt)
        last = self.cyc
        for i, (w, keep) in enumerate(ws):
            d.s_v.value, d.s_d.value = 1, w
            d.s_sof.value, d.s_eof.value = int(i == 0), int(i == len(ws) - 1)
            d.s_keep.value = keep if i == len(ws) - 1 else 0xFF
            last = self.cyc
            await self.tick()
        d.s_v.value = d.s_sof.value = d.s_eof.value = 0
        return last

    def counters(self) -> dict:
        v = int(self.dut.cnt.value)
        return {k: (v >> (32 * i)) & 0xFFFFFFFF for i, k in enumerate(COUNTERS)}


def small_cfg(**kw) -> Cfg:
    base = dict(thr=MID + 3 * TK, max_pos=300, max_qty=500, band=20_000)
    base.update(kw)
    return Cfg(**base)


async def scenario(dut, spec: bool, seed: int):
    cfg = small_cfg()
    t = Top(dut, cfg, spec)
    await t.start()
    conn = Conn()
    await t.connect(conn)
    m = Model(cfg)
    ts = [1000]
    seq = [1]

    def tstamp():
        ts[0] += 7
        return ts[0]

    async def send(msgs, idle=40):
        pkt = proto.mold_packet(b"SESSION001", seq[0], msgs)
        m.feed(pkt)
        seq[0] += len(msgs)
        return await t.send(pkt, idle)

    loc0 = 10
    await send([proto.itch_S(0, tstamp(), "O")] + [proto.itch_R(loc0 + i, tstamp(), cfg.watch[i]) for i in range(cfg.n_inst)])
    await send([proto.itch_A(loc0, tstamp(), 1, "B", 100, cfg.watch[0], MID - 100)])
    Ts = []
    for k in range(8):                                      # asks at or below the threshold: buy triggers; the position limit of 300 refuses the fourth on
        Ts.append(await send([proto.itch_A(loc0, tstamp(), 10 + k, "S", 100, cfg.watch[0], MID + 100 + k)], idle=60))
    for _ in range(80):
        await t.tick()
    assert len(m.orders) == 3, len(m.orders)
    good = [s for s in t.segs if not s["poison"]]
    bad = [s for s in t.segs if s["poison"]]
    assert [tcpref.parse(s["bytes"]).payload for s in good] == [o["frame"] for o in m.orders]
    assert all(tcpref.parse(s["bytes"]).ok and len(s["bytes"]) == 113 for s in good)
    assert [tcpref.parse(s["bytes"]).seq for s in good] == [1000, 1059, 1118]
    assert [tcpref.parse(s["bytes"]).ident for s in good] == [1, 2, 3]
    c = t.counters()
    assert not t.refusals and c["rej_busy"] == 0
    if spec:
        assert len(bad) == c["abort"] == 5 and c["fire"] == 3 and c["spec"] == 8, (len(bad), c)
        assert all(s["bytes"] == s["bytes"][:len(s["bytes"])] and len(s["bytes"]) <= 113 for s in bad)
    else:
        assert not bad and c["abort"] == 0
    # the clock of the first byte of the first good segment, from the clock the triggering message's last word was presented
    first = good[0]["cyc"] - Ts[0]
    return first, len(bad), c


@cocotb.test()
async def t_behind_the_risk_logic(dut):
    """Not speculative (the frame starts at the verdict) and speculative (it starts first and the refused ones are poisoned): same orders out, same bytes."""
    res = {}
    for spec in (False, True):
        first, nbad, c = await scenario(dut, spec, 1)
        res["speculative" if spec else "non_speculative"] = {"first_ethernet_byte_clocks_after_last_itch_byte": first, "poisoned_segments": nbad}
    # brief 110's stub port shows the first word of the frame 8 clocks (verdict) or 3 clocks (speculative) after the message's last byte: the headers add no latency
    assert res["non_speculative"]["first_ethernet_byte_clocks_after_last_itch_byte"] == 8
    assert res["speculative"]["first_ethernet_byte_clocks_after_last_itch_byte"] == 3
    REC["behind_risk_logic"] = res


@cocotb.test()
async def t_zz_write_records(dut):
    out = os.environ.get("B119_RECORD")
    if out and REC:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "top_sim.json").write_text(json.dumps(REC, indent=2, sort_keys=True) + "\n")
