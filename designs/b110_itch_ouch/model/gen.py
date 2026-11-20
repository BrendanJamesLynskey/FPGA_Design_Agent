"""Synthetic ITCH 5.0 over MoldUDP64 generator (brief 110). Seeded; no real exchange data is used or implied.

The stream starts like a trading day (System Event 'O', one Stock Directory per instrument, System Event 'S' and 'Q'), then a message
mix of adds, executions, cancels, deletes and replaces on live orders, a few messages of other types, other symbols' orders and some
that name an unknown order. Packets carry one to several messages, so messages straddle 64-bit words and packets. Impairments
(gap, duplicate, overlap, heartbeat, bad frame) are switched on by probability and are all visible to the model.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import proto
from .ref import Cfg

TICK = 100            # one cent in Price(4)
MID = 1_000_000       # 100.0000


@dataclass
class Item:
    pkt: bytes
    err: bool = False
    idle: int = 8       # idle clocks before the packet (an Ethernet frame leaves at least this many words between payloads)
    note: str = ""


class Gen:
    def __init__(self, seed: int, cfg: Cfg | None = None, session: bytes = b"SESSION001", mid: int = MID, spread_levels: int = 5,
                 locate0: int = 10, max_live: int = 40):
        self.r = random.Random(seed)
        self.cfg = cfg or Cfg()
        self.session = session
        self.mid = mid
        self.sl = spread_levels
        self.loc0 = locate0
        self.window = (1 << self.cfg.ord_aw) - 16         # live references stay within one table's worth of indices: no index collisions
        self.max_live = min(max_live, self.window // 4)
        self.seq = 1
        self.ts = 34_200_000_000_000
        self.ref = 1000 + self.r.randrange(0, 5000)
        self.live: dict[int, dict] = {}
        self.sent_other: list[int] = []

    # ---- messages
    def _t(self):
        self.ts += self.r.randrange(100, 20000)
        return self.ts

    def px(self, side: str) -> int:
        k = self.r.randrange(1, self.sl + 1)
        return self.mid + TICK * k * (1 if side == "S" else -1)

    def preamble(self) -> list[bytes]:
        c = self.cfg
        out = [proto.itch_S(0, self._t(), "O")]
        for i, w in enumerate(c.watch[:c.n_inst]):
            out.append(proto.itch_R(self.loc0 + i, self._t(), w))
        out.append(proto.itch_R(90, self._t(), "ZZZ"))
        out += [proto.itch_S(0, self._t(), "S"), proto.itch_S(0, self._t(), "Q")]
        return out

    def _inst(self):
        c = self.cfg
        return self.r.randrange(0, c.n_inst)

    def one(self) -> bytes:
        r = self.r
        c = self.cfg
        x = r.random()
        live = list(self.live)
        old = [k for k in live if k < self.ref - self.window]          # keep live orders inside the order table's index window
        if old:
            ref = old[0]
            o = self.live.pop(ref)
            return proto.itch_D(self.loc0 + o["inst"], self._t(), ref)
        if x < 0.40 or (not live and x < 0.95) or len(live) < 4:
            return self._add()
        if len(live) > self.max_live:
            x = 0.60 + r.random() * 0.1            # prune: delete
        if x < 0.55:
            return self._exec()
        if x < 0.62:
            return self._exec(price=True)
        if x < 0.72:
            return self._cancel()
        if x < 0.86:
            return self._delete()
        if x < 0.94:
            return self._replace()
        if x < 0.955:
            return proto.itch_other(r.choice("PQHYLVWKJhBINpO"[:8]), r.choice([44, 40, 25, 20, 26, 35, 12, 50]), self.loc0, self._t())
        if x < 0.975:                                    # an order of another instrument (unwatched locate)
            ref = self._newref()
            return proto.itch_A(95, self._t(), ref, r.choice("BS"), r.randrange(1, 500), "OTHER", self.mid + TICK * r.randrange(-8, 9))
        if x < 0.985:                                    # an unknown order reference of a watched instrument
            return proto.itch_D(self.loc0 + self._inst(), self._t(), 5_000_000 + r.randrange(0, 1000))
        return proto.itch_S(0, self._t(), r.choice("ES"))

    def _newref(self) -> int:
        self.ref += self.r.randrange(1, 4)
        return self.ref

    def _add(self) -> bytes:
        r, c = self.r, self.cfg
        i = self._inst()
        side = r.choice("BS")
        ref = self._newref()
        sh = r.choice([100, 100, 200, 300, 500, 1000, r.randrange(1, 2000)])
        px = self.px(side)
        self.live[ref] = {"inst": i, "side": side, "px": px, "rem": sh}
        if r.random() < 0.12:
            return proto.itch_F(self.loc0 + i, self._t(), ref, side, sh, c.watch[i], px, "MPID")
        return proto.itch_A(self.loc0 + i, self._t(), ref, side, sh, c.watch[i], px)

    def _pick(self):
        ref = self.r.choice(list(self.live))
        return ref, self.live[ref]

    def _exec(self, price: bool = False) -> bytes:
        ref, o = self._pick()
        s = self.r.randrange(1, o["rem"] + 1)
        o["rem"] -= s
        loc = self.loc0 + o["inst"]
        if o["rem"] == 0:
            del self.live[ref]
        if price:
            return proto.itch_C(loc, self._t(), ref, s, o["px"] + TICK, self.r.randrange(1, 10**9))
        return proto.itch_E(loc, self._t(), ref, s, self.r.randrange(1, 10**9))

    def _cancel(self) -> bytes:
        ref, o = self._pick()
        s = self.r.randrange(1, o["rem"] + 1)
        o["rem"] -= s
        loc = self.loc0 + o["inst"]
        if o["rem"] == 0:
            del self.live[ref]
        return proto.itch_X(loc, self._t(), ref, s)

    def _delete(self) -> bytes:
        ref, o = self._pick()
        del self.live[ref]
        return proto.itch_D(self.loc0 + o["inst"], self._t(), ref)

    def _replace(self) -> bytes:
        ref, o = self._pick()
        nref = self._newref()
        sh = self.r.choice([100, 200, 400, self.r.randrange(1, 1500)])
        px = self.px(o["side"])
        del self.live[ref]
        self.live[nref] = {"inst": o["inst"], "side": o["side"], "px": px, "rem": sh}
        return proto.itch_U(self.loc0 + o["inst"], self._t(), ref, nref, sh, px)

    def epilogue(self) -> list[bytes]:
        return [proto.itch_S(0, self._t(), "M"), proto.itch_S(0, self._t(), "E"), proto.itch_S(0, self._t(), "C")]

    # ---- packets
    def stream(self, n_msgs: int, max_per_pkt: int = 6, p_gap: float = 0.0, p_dup: float = 0.0, p_overlap: float = 0.0,
               p_hb: float = 0.02, p_err: float = 0.0, p_back: float = 0.4, preamble: bool = True) -> list[Item]:
        """Packets for about n_msgs messages. p_back: probability that a packet follows the previous one after the minimum idle gap."""
        r = self.r
        msgs = self.preamble() if preamble else []
        items: list[Item] = []
        k = 0
        todo = list(msgs)
        while k < n_msgs or todo:
            if todo:
                n = min(len(todo), r.randrange(1, max_per_pkt + 1))
                chunk, todo = todo[:n], todo[n:]
            else:
                n = r.randrange(1, max_per_pkt + 1)
                chunk = [self.one() for _ in range(n)]
                k += n
            idle = 8 if r.random() < p_back else r.randrange(9, 40)
            seq = self.seq
            note = ""
            if r.random() < p_gap:
                seq += r.randrange(1, 6)
                note = "gap"
                self.seq = seq
            pkt = proto.mold_packet(self.session, seq, chunk)
            items.append(Item(pkt, err=r.random() < p_err, idle=idle, note=note or ("err" if False else "")))
            self.seq = seq + len(chunk)
            if r.random() < p_hb:
                items.append(Item(proto.heartbeat(self.session, self.seq), idle=r.randrange(8, 20), note="hb"))
            if r.random() < p_dup:
                items.append(Item(pkt, idle=8, note="dup"))            # the same packet again
            if r.random() < p_overlap and len(chunk) >= 2:
                # a retransmission that starts inside what was already sent and carries one message more
                j = r.randrange(1, len(chunk))
                extra = self.one()
                items.append(Item(proto.mold_packet(self.session, seq + j, chunk[j:] + [extra]), idle=8, note="overlap"))
                self.seq += 1
        if preamble:
            items.append(Item(proto.mold_packet(self.session, self.seq, self.epilogue()), idle=10))
            self.seq += 3
        return items
