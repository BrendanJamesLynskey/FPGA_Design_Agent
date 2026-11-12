"""Reference model of the trading port: frames in, what must leave and every counter that must move.

Written from docs/bench_feed_v1.md, docs/rule_table.md and docs/register_map.md, not from the RTL. It is untimed:
it says which orders, undos, cancels and ARP replies leave and in what order, not when. Two things depend on time and
are handled by the tests instead: how an order from a bad frame is undone (dropped before it starts, poisoned on the
wire, or followed by a cancel: the model says "undo"; the bench accepts exactly one of the three), and the token-bucket
refill (tests use a refill period longer than the test, so the bucket only empties) and rule hold-off (0, or longer
than the test).
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

from . import benchfeed as bf

COUNTERS = [
    "rx_frames", "rx_good", "rx_bytes", "rx_fcs", "rx_runt", "rx_giant", "rx_er", "rx_bad_pre",
    "drop_l2", "drop_type", "drop_ip", "drop_csum", "drop_port", "drop_feed", "drop_arp", "arp_req",
    "pkts", "msgs", "seq_gaps", "book_mismatch", "book_range", "book_bad_type", "rule_fires", "rule_holdoff",
    "requests", "grants", "rej_kill", "rej_halt", "rej_qty", "rej_band", "rej_pos", "rej_rate",
    "suppressed", "busy", "spec_drop", "spec_poison", "spec_cancel", "kill_drop", "orders_sent", "cancels_sent",
    "arp_sent", "tx_frames", "tx_poisoned", "rx_fifo_ovf",
    "b_rx_frames", "b_rx_good", "b_rx_fcs", "b_rx_orders", "b_feed_sent", "b_tx_frames", "b_rx_fifo_ovf", "log_dropped",
    "wdog", "soft_resets",
]


@dataclass
class Config:
    my_mac: int = bf.BOARD_MAC
    my_ip: int = bf.BOARD_IP
    my_port: int = bf.BOARD_PORT
    spec_en: bool = True
    halt_on_gap: bool = False
    kill: bool = False
    max_qty: int = 100
    band: int = 500
    max_pos: int = 1000
    bucket: int = 16
    ninst: int = 256


@dataclass
class Out:
    kind: str                     # "order" or "arp"
    order: bf.Order | None = None
    undo: bool = False            # the order's trigger frame was bad: poisoned or followed by a cancel
    arp: tuple[int, int] | None = None


@dataclass
class Model:
    cfg: Config = field(default_factory=Config)
    table: list[list[int]] = field(default_factory=lambda: [[0] * 6 for _ in range(8)])
    version: int = 0
    book: dict[int, list[int]] = field(default_factory=dict)
    have_seq: bool = False
    exp_seq: int = 0
    halted: bool = False
    pos: int = 0
    tokens: int = 16
    next_id: int = 1
    hold_blocked: set[int] = field(default_factory=set)
    cnt: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNTERS, 0))
    log: list[tuple[int, int, int, int, int]] = field(default_factory=list)   # (seq, version, rule, inst, price)

    def __post_init__(self) -> None:
        self.tokens = self.cfg.bucket

    def commit(self, table: list[list[int]]) -> None:
        self.table = [list(w) for w in table]
        self.version += 1

    # ---- rules -----------------------------------------------------------------------------------------------
    def _match(self, r: int, ty: int, side: int, inst: int, px: int, bk: list[int] | None) -> bool:
        c, ins, th = self.table[r][0], self.table[r][1], self.table[r][2]
        if not c & 1 or ty not in (1, 2, 3, 4) or not (c >> ty) & 1:
            return False
        s = (c >> 5) & 3
        if (s == 1 and side != 0) or (s == 2 and side != 1):
            return False
        if not (c >> 7) & 1 and (ins & 0xFFFF) != inst:
            return False
        op = (c >> 8) & 7
        if op == 1 and not px < th: return False
        if op == 2 and not px <= th: return False
        if op == 3 and not px > th: return False
        if op == 4 and not px >= th: return False
        b = (c >> 11) & 3
        if b:
            if bk is None:
                return False
            bpx, bsz, apx, asz, _ = bk
            if b == 1:
                ok = (asz == 0 or px < apx) if side else (bsz == 0 or px > bpx)
            elif b == 2:
                ok = (bsz != 0 and px <= bpx) if side else (asz != 0 and px >= apx)
            else:
                ok = True
            if not ok:
                return False
        return True

    def _interlock(self, side: int, qty: int, px: int, ref: int | None) -> str | None:
        c = self.cfg
        mq, bd, mp = c.max_qty & 0x7FFFFFFF, c.band & 0x7FFFFFFF, c.max_pos & 0x7FFFFFFF
        npos = self.pos - qty if side else self.pos + qty
        if c.kill: return "kill"
        if self.halted: return "halt"
        if qty == 0 or qty > mq: return "qty"
        if ref is None or abs(px - ref) > bd: return "band"
        if abs(npos) > mp: return "pos"
        if self.tokens == 0: return "rate"
        self.pos = npos
        self.tokens -= 1
        return None

    # ---- one frame -----------------------------------------------------------------------------------------------
    def frame(self, data: bytes, er: bool = False) -> list[Out]:
        """Process one received frame: `data` is everything after the SFD (FCS included, or corrupted)."""
        c, k = self.cfg, self.cnt
        out: list[Out] = []
        n = len(data)
        crc_ok = zlib.crc32(data) & 0xFFFFFFFF == 0x2144DF1C if n >= 4 else False   # residue, bit-reversed form
        good = crc_ok and 64 <= n <= 1522 and not er
        k["rx_frames"] += 1
        k["rx_bytes"] += min(n, 2047)
        k["rx_good"] += good
        k["rx_fcs"] += not crc_ok
        k["rx_runt"] += n < 64
        k["rx_giant"] += n > 1522
        k["rx_er"] += er

        my_mac = c.my_mac.to_bytes(6, "big")
        my_ip = c.my_ip.to_bytes(4, "big")
        alive, is_arp, mac_us, mac_bc, bcast = True, False, True, True, False
        hdr_ok, in_msgs, cnt, seq, udp_len = False, False, 0, 0, 0
        csum = 0
        kmsg, off = 0, 0
        fields = bytearray(16)
        bk = None
        ordered = False
        slot: Out | None = None
        pend_seq = None

        def fail(why: str) -> None:
            nonlocal alive
            alive = False
            k["drop_" + why] += 1

        for b, d in enumerate(data[:2047]):
            if alive:
                word = ((data[b - 1] << 8) | d) if b else d
                if b <= 5:
                    mac_us = mac_us and d == my_mac[b]
                    mac_bc = mac_bc and d == 0xFF
                    if b == 5:
                        if not (mac_us or mac_bc):
                            fail("l2"); continue
                        bcast = not mac_us
                elif b == 13:
                    if word == 0x0806:
                        is_arp = True
                    elif word != 0x0800:
                        fail("type"); continue
                    elif bcast:
                        fail("l2"); continue
                elif is_arp:
                    if (b == 15 and word != 1) or (b == 17 and word != 0x0800) or (b == 19 and word != 0x0604) or \
                            (b == 21 and word != 1) or (38 <= b <= 41 and d != my_ip[b - 38]):
                        fail("arp"); continue
                else:
                    if b >= 15 and b <= 33 and b % 2 == 1:
                        csum += word
                        csum = (csum & 0xFFFF) + (csum >> 16)
                    if (b == 14 and d != 0x45) or (b == 21 and word & 0x3FFF) or (b == 23 and d != 17) or \
                            (30 <= b <= 33 and d != my_ip[b - 30]):
                        fail("ip"); continue
                    if b == 33 and csum != 0xFFFF:
                        fail("csum"); continue
                    if b == 37 and word != c.my_port:
                        fail("port"); continue
                    if b == 39:
                        udp_len = word
                        if word < 16:
                            fail("feed"); continue
                    if (b == 43 and word != bf.MAGIC) or (b == 44 and d != 1) or \
                            (b == 45 and (d == 0 or d > bf.MAX_MSGS or d * 16 + 16 > udp_len)):
                        fail("feed"); continue
                    if b == 45:
                        cnt = d
                    if b == 49:
                        seq = int.from_bytes(data[46:50], "big")
                        hdr_ok, in_msgs, kmsg, off = True, True, 0, 0
                        k["pkts"] += 1
                        if self.have_seq and seq != self.exp_seq:
                            k["seq_gaps"] += 1
                            if c.halt_on_gap:
                                self.halted = True
                        pend_seq = (seq + cnt) & 0xFFFFFFFF
                        continue
                    if in_msgs and b >= 50:
                        fields[off] = d
                        if off == 3:
                            inst = (fields[2] << 8) | fields[3]
                            if inst < c.ninst:
                                bk = list(self.book.get(inst, [0, 0, 0, 0, 0]))
                            else:
                                bk = None
                                k["book_range"] += 1
                        if off == 7:
                            ty, side = fields[0], fields[1] & 1
                            inst = (fields[2] << 8) | fields[3]
                            px = int.from_bytes(fields[4:8], "big")
                            mseq = (seq + kmsg) & 0xFFFFFFFF
                            slot, asked = self._decide(ty, side, inst, px, bk, mseq, ordered, slot, out)
                            ordered = ordered or asked      # one request per frame, whatever the interlocks answer
                        if off == 15:
                            self._update(fields, bk)
                            k["msgs"] += 1
                            kmsg += 1
                            if kmsg == cnt:
                                in_msgs = False
                        off = (off + 1) & 15
        # end of frame
        if slot is not None and not good:
            if c.spec_en:
                slot.undo = True                 # dropped, poisoned or cancelled, depending on timing
            else:
                out.remove(slot)                 # safe mode: never sent
                k["orders_sent"] -= 1
            k["undo_any"] = k.get("undo_any", 0) + 1
        if slot is not None and good and not c.spec_en and c.kill:
            out.remove(slot)
        if good and hdr_ok and alive and pend_seq is not None:
            self.have_seq, self.exp_seq = True, pend_seq
        if good and is_arp and alive and n - 1 >= 41:
            sha = int.from_bytes(data[22:28], "big")
            spa = int.from_bytes(data[28:32], "big")
            out.append(Out("arp", arp=(sha, spa)))
            k["arp_req"] += 1
            k["arp_sent"] += 1
        return out

    def _decide(self, ty, side, inst, px, bk, mseq, ordered, slot, out):
        k = self.cnt
        m = [self._match(r, ty, side, inst, px, bk) for r in range(8)]
        cand = [r for r in range(8) if m[r] and r not in self.hold_blocked]
        if not cand:
            if any(m):
                k["rule_holdoff"] += 1
            return slot, False
        r = cand[0]
        w = self.table[r]
        c = w[0]
        if w[5]:
            self.hold_blocked.add(r)
        k["rule_fires"] += 1
        if (c >> 19) & 1:
            self.log.append((mseq, self.version, r, inst & 0xFFF, self._price(w, px)))
        if not (c >> 13) & 1:
            return slot, False
        if ordered:
            k["suppressed"] += 1
            return slot, False
        k["requests"] += 1
        oside, qty, opx = (c >> 14) & 1, w[3], self._price(w, px)
        why = self._interlock(oside, qty, opx, self._reference(oside, bk))
        if why:
            k["rej_" + why] += 1
            return slot, True
        k["grants"] += 1
        o = Out("order", bf.Order(bf.NEW_ORDER, oside, inst, opx, qty, self.next_id))
        self.next_id += 1
        k["orders_sent"] += 1
        out.append(o)
        return o, True

    @staticmethod
    def _reference(side: int, bk: list[int] | None) -> int | None:
        """The price-band reference: the book before the triggering message (a buy against the best ask, a sell
        against the best bid; the last trade if that side is empty), never the message itself; None if there is none."""
        if bk is None:
            return None
        bpx, bsz, apx, asz, last = bk
        if side == 0 and asz:
            return apx
        if side == 1 and bsz:
            return bpx
        return last or None

    @staticmethod
    def _price(w: list[int], px: int) -> int:
        mode = (w[0] >> 15) & 3
        return w[4] if mode == 0 else px if mode == 1 else (px + w[4]) & 0xFFFFFFFF

    def _update(self, f: bytearray, bk: list[int] | None) -> None:
        k = self.cnt
        if bk is None:
            return
        ty, side = f[0], f[1] & 1
        inst = (f[2] << 8) | f[3]
        px = int.from_bytes(f[4:8], "big")
        sz = int.from_bytes(f[8:12], "big")
        if ty == 0 or ty > 4:
            k["book_bad_type"] += 1
            return
        e = list(bk)
        i = 2 if side else 0
        npx, nsz = e[i], e[i + 1]
        mism = False
        if ty == 1:
            npx, nsz = px, sz
        elif ty == 2:
            mism = npx != px
            npx, nsz = px, sz
        elif ty == 3:
            npx, nsz = 0, 0
        else:
            e[4] = px
            if npx == px and nsz != 0:
                nsz = nsz - sz if nsz > sz else 0
                if nsz == 0:
                    npx = 0
            else:
                mism = True
        e[i], e[i + 1] = npx, nsz
        self.book[inst] = e
        k["book_mismatch"] += mism


def residue_check() -> None:
    """zlib.crc32 over data+FCS of a good frame is the fixed value 0x2144DF1C (the inverted, bit-reversed 0xDEBB20E3)."""
    f = bytes(range(60))
    assert zlib.crc32(f + struct.pack("<I", zlib.crc32(f))) == 0x2144DF1C
