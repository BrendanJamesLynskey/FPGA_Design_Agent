"""Reference model of the ITCH/MoldUDP64 to OUCH trading path (brief 110): untimed, event by event, exact.

The RTL is compared with this model bit for bit: the messages the Mold layer delivers, the decoded events, every top-of-book
update, every order frame, and every counter. Timing is not modelled (the testbench measures clocks); where the hardware's
behaviour depends on timing the tests keep the stream inside the region where it does not (docs/itch_ouch.md, "Rates").
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import proto

# counter order of the hardware's counter bus (rtl/itch_pkg.sv holds the same list; tests/test_b110_model.py checks it)
COUNTERS = (
    "pkt", "msg", "gap", "missing", "dup", "ovlp", "sess", "hb", "eos", "short", "trunc", "badlen", "pkt_err",
    "m_a", "m_f", "m_e", "m_c", "m_x", "m_d", "m_u", "m_s", "m_r", "m_skip", "m_bad",
    "unwatch", "omiss", "odup", "oovf", "lvovf", "lvmiss", "oover", "evdrop",
    "cand", "fire", "rej_arm", "rej_kill", "rej_gap", "rej_stale", "rej_size", "rej_pos", "rej_band", "rej_busy", "abort", "late_abort", "spec",
)
M32 = 0xFFFFFFFF
BID, ASK = 0, 1


@dataclass
class Cfg:
    n_inst: int = 4
    levels: int = 8
    ord_aw: int = 8
    watch: tuple = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH")
    thr: int = 1_000_000          # ask price at or below which a new sell order is a buy trigger (Price(4): 100.0000)
    qty: int = 100
    max_qty: int = 500
    max_pos: int = 1000
    band: int = 20_000            # a buy may be at most this far (Price(4) units) above the best bid
    px_off: int = 0               # added to the triggering order's price to give the order price
    tif: str = "3"
    display: str = "Y"
    capacity: str = "P"
    ise: str = "N"
    cross: str = "N"
    minqty: int = 0
    custtype: str = "N"
    arm: bool = True
    kill: bool = False
    halt_on_gap: bool = True


@dataclass
class Model:
    cfg: Cfg = field(default_factory=Cfg)

    def __post_init__(self):
        self.reset()

    # ---------------------------------------------------------------- state
    def reset(self):
        c = self.cfg
        self.cnt = {k: 0 for k in COUNTERS}
        self.sess_lock = False
        self.sess = b""
        self.exp = 0
        self.exp_v = False
        self.gap = False
        self.untrusted = False
        self.eos_seen = False
        self.loc = [None] * c.n_inst
        self.sys_code = 0
        self.clear_book()
        self.pos = [0] * c.n_inst
        self.next_ref = 1
        self.msgs, self.events, self.tus, self.orders = [], [], [], []

    def clear_book(self):
        c = self.cfg
        self.table = {}                                  # index -> dict(ref, inst, side, px, rem)
        self.lv = [[{}, {}] for _ in range(c.n_inst)]    # [inst][side] price -> size
        self.inexact = [False] * c.n_inst
        self.loc = [None] * c.n_inst
        self.tob = [[(0, 0, False), (0, 0, False)] for _ in range(c.n_inst)]

    def clear_counters(self):
        self.cnt = {k: 0 for k in COUNTERS}

    # ---------------------------------------------------------------- MoldUDP64
    def packet(self, pkt: bytes, err: bool = False):
        """One UDP payload. Returns the delivered messages [(seq32, length, first 36 bytes)]; the rest of the model state follows."""
        cnt = self.cnt
        out = []
        if len(pkt) >= 20:
            sess, seq, n = pkt[:10], int.from_bytes(pkt[10:18], "big"), int.from_bytes(pkt[18:20], "big")
            hbeos = n in (0, proto.EOS)
            n_eff = 0 if hbeos else n
            bad, skip = False, 0
            if self.sess_lock and sess != self.sess:
                cnt["sess"] += 1
                bad = True
            else:
                if not self.sess_lock:
                    self.sess, self.sess_lock = sess, True
                accepted = True
                if not self.exp_v:
                    self.exp, self.exp_v = (seq + n_eff) & ((1 << 64) - 1), True
                elif seq > self.exp:
                    cnt["gap"] += 1
                    cnt["missing"] = (cnt["missing"] + (seq - self.exp)) & M32
                    self.gap = True
                    self.exp = (seq + n_eff) & ((1 << 64) - 1)
                elif seq == self.exp:
                    self.exp = (seq + n_eff) & ((1 << 64) - 1)
                else:
                    delta = (self.exp - seq) & M32
                    if (self.exp >> 32) != (seq >> 32) or n_eff == 0 or delta >= n_eff:
                        cnt["dup"] += 1
                        bad, accepted = True, False
                    else:
                        skip = delta
                        self.exp = (seq + n_eff) & ((1 << 64) - 1)
                if accepted:
                    cnt["pkt"] += 1
                    if n == 0:
                        cnt["hb"] += 1
                    if n == proto.EOS:
                        cnt["eos"] += 1
                        self.eos_seen = True
            # blocks
            pos, started, done, stopped = 20, 0, 0, False
            while not hbeos and started < n and not stopped:
                if pos + 2 > len(pkt):
                    break
                L = int.from_bytes(pkt[pos:pos + 2], "big")
                started += 1
                if L < proto.MIN_BLOCK:
                    cnt["badlen"] += 1
                    stopped = True
                    break
                if pos + 2 + L > len(pkt):
                    break
                m = pkt[pos + 2:pos + 2 + L]
                idx = started - 1
                pos += 2 + L
                done += 1
                if bad:
                    continue
                if idx < skip:
                    cnt["ovlp"] += 1
                    continue
                cnt["msg"] += 1
                out.append(((seq + idx) & M32, L, m[:proto.ITCH_KEEP]))
            if not hbeos and not stopped and done < n:
                cnt["trunc"] += 1
        else:
            cnt["short"] += 1
        self.msgs += out
        return out

    # ---------------------------------------------------------------- ITCH decode and book
    def decode(self, seq: int, L: int, m: bytes):
        """Returns an event dict or None. Counters as in rtl/itch_dec.sv."""
        cnt = self.cnt
        t = chr(m[0])
        if t not in proto.ITCH_LEN:
            cnt["m_skip"] += 1
            return None
        if L != proto.ITCH_LEN[t]:
            cnt["m_bad"] += 1
            return None
        cnt["m_" + t.lower()] += 1
        be = lambda a, b: int.from_bytes(m[a:b], "big")      # noqa: E731
        ev = {"t": t, "seq": seq, "loc": be(1, 3)}
        if t == "S":
            ev["code"] = m[11]
        elif t == "R":
            ev["stock"] = bytes(m[11:19])
        elif t in "AF":
            ev |= {"ref": be(11, 19), "sell": m[19] == ord("S"), "shares": be(20, 24), "stock": bytes(m[24:32]), "px": be(32, 36)}
            if m[19] not in (ord("B"), ord("S")) or ev["shares"] == 0:
                cnt["m_bad"] += 1
                return None
        elif t in "ECX":
            ev |= {"ref": be(11, 19), "shares": be(19, 23)}
            if ev["shares"] == 0:
                cnt["m_bad"] += 1
                return None
        elif t == "D":
            ev["ref"] = be(11, 19)
        elif t == "U":
            ev |= {"ref": be(11, 19), "nref": be(19, 27), "shares": be(27, 31), "px": be(31, 35)}
            if ev["shares"] == 0:
                cnt["m_bad"] += 1
                return None
        return ev

    def inst_of(self, locate: int):
        for i, l in enumerate(self.loc):
            if l is not None and l == locate:
                return i
        return None

    def _level(self, inst, side, px, amt, add: bool, cause, cand_px=None):
        """One ladder operation followed by the top-of-book recompute: returns the tu record (always, as the hardware does)."""
        c, cnt = self.cfg, self.cnt
        d = self.lv[inst][side]
        if add:
            if px in d:
                d[px] = (d[px] + amt) & M32
            elif len(d) < c.levels:
                d[px] = amt & M32
            else:
                cnt["lvovf"] += 1
                self.inexact[inst] = True
        else:
            if px in d:
                if amt >= d[px]:
                    del d[px]
                else:
                    d[px] -= amt
            else:
                cnt["lvmiss"] += 1
        if d:
            bp = max(d) if side == BID else min(d)
            tob = (bp, d[bp], True)
        else:
            tob = (0, 0, False)
        self.tob[inst][side] = tob
        tu = {"inst": inst, "side": side, "px": tob[0], "sz": tob[1], "ok": tob[2], "cause": cause, "cause_px": px}
        self.tus.append(tu)
        return tu

    def _insert(self, ref, inst, side, px, shares):
        """Order table insert; returns True if stored."""
        c, cnt = self.cfg, self.cnt
        idx = ref & ((1 << c.ord_aw) - 1)
        e = self.table.get(idx)
        if e is not None:
            if e["ref"] == ref:
                cnt["odup"] += 1
            else:
                cnt["oovf"] += 1
                self.inexact[inst] = True
            return False
        self.table[idx] = {"ref": ref, "inst": inst, "side": side, "px": px, "rem": shares}
        return True

    def event(self, ev):
        """Apply one decoded event. Returns the decision order (dict) or None."""
        c, cnt = self.cfg, self.cnt
        self.events.append(ev)
        t = ev["t"]
        if t == "S":
            self.sys_code = ev["code"]
            return None
        if t == "R":
            for i, w in enumerate(c.watch[:c.n_inst]):
                if ev["stock"] == proto.alpha(w, 8):
                    self.loc[i] = ev["loc"]
            return None
        inst = self.inst_of(ev["loc"])
        if inst is None:
            cnt["unwatch"] += 1
            return None
        mask = (1 << c.ord_aw) - 1
        if t in "AF":
            side = ASK if ev["sell"] else BID
            if self._insert(ev["ref"], inst, side, ev["px"], ev["shares"]):
                tu = self._level(inst, side, ev["px"], ev["shares"], True, "A", ev["px"])
                return self._decide(inst, side, ev["px"], tu)
            return None
        idx = ev["ref"] & mask
        e = self.table.get(idx)
        hit = e is not None and e["ref"] == ev["ref"]
        if not hit:
            cnt["omiss"] += 1
            return None
        if t in "ECXD":
            s = None if t == "D" else ev["shares"]
            if s is None or s >= e["rem"]:
                if s is not None and s > e["rem"]:
                    cnt["oover"] += 1
                amt = e["rem"]
                del self.table[idx]
            else:
                amt = s
                e["rem"] -= s
            self._level(e["inst"], e["side"], e["px"], amt, False, "R")
            return None
        # U: delete the old order, then add the new one with the old order's instrument and side
        old = dict(e)
        del self.table[idx]
        self._level(old["inst"], old["side"], old["px"], old["rem"], False, "U")
        if self._insert(ev["nref"], old["inst"], old["side"], ev["px"], ev["shares"]):
            self._level(old["inst"], old["side"], ev["px"], ev["shares"], True, "U")
        return None

    # ---------------------------------------------------------------- decision, risk, OUCH
    def _decide(self, inst, side, px, tu):
        c, cnt = self.cfg, self.cnt
        if side != ASK or px == 0 or px > c.thr:
            return None
        cnt["cand"] += 1
        price = (px + c.px_off) & M32
        bid = self.tob[inst][BID]
        if not c.arm:
            cnt["rej_arm"] += 1
        elif c.kill:
            cnt["rej_kill"] += 1
        elif self.untrusted or (c.halt_on_gap and self.gap):
            cnt["rej_gap"] += 1
        elif self.inexact[inst]:
            cnt["rej_stale"] += 1
        elif c.qty == 0 or c.qty > c.max_qty or c.qty >= 1_000_000:
            cnt["rej_size"] += 1
        elif self.pos[inst] + c.qty > c.max_pos:
            cnt["rej_pos"] += 1
        elif not (bid[2] and price <= bid[0] + c.band):
            cnt["rej_band"] += 1
        else:
            ref = self.next_ref
            self.next_ref += 1
            self.pos[inst] += c.qty
            cnt["fire"] += 1
            o = {"ref": ref, "inst": inst, "price": price, "qty": c.qty, "frame": self.frame(ref, inst, price, c.qty)}
            self.orders.append(o)
            return o
        return None

    def frame(self, ref, inst, price, qty) -> bytes:
        c = self.cfg
        m = proto.ouch_enter(ref, "B", qty, proto.alpha(c.watch[inst], 8), price, c.tif, c.display, c.capacity, c.ise, c.cross,
                             proto.clordid(ref), c.minqty, c.custtype)
        return proto.soup_unsequenced(m)

    # ---------------------------------------------------------------- driver
    def feed(self, pkt: bytes, err: bool = False):
        """A packet through the whole model: returns the orders it produced."""
        out = []
        for seq, L, m in self.packet(pkt, err):
            ev = self.decode(seq, L, m)
            if ev is not None:
                o = self.event(ev)
                if o is not None:
                    out.append(o)
        if err:                      # the frame's verdict comes with its last word: it applies to what follows, not to the packet's own messages
            self.cnt["pkt_err"] += 1
            self.untrusted = True
        return out
