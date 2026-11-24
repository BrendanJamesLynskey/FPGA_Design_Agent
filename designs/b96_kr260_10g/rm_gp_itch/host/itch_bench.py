"""The host's driver of the ITCH path (brief 127, build rm_gp_itch): a PLAN of register operations that runs unchanged on the whole-core simulation (sim/tb_itch_core.sv reads the plan as a
script) and on the board (a Transport with rd/wr, host/b127_board.py), and the checks of what comes back against brief 110's model.

A plan is a list of operations: ("W", addr, value), ("R", addr, tag), ("D", ns), ("L",) wait for the link, ("POLL", addr, mask, value, timeout_ms) wait until a register matches (the simulation
script turns it into a fixed wait). Nothing here is adaptive on a read, so the same plan is a valid script. Every register address comes from regmap_itch.CFG; every counter's place in the
counter window from regmap_itch.STAT_NAMES.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import COUNTERS, Cfg, Model
from designs.b96_kr260_10g.rm_gp_itch import regmap_itch as R
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H

ADDR = {n: R.CFG_BASE + 4 * i for i, n, *_ in R.CFG}
STAT = {n: R.STAT_BASE + 4 * i for i, n in enumerate(R.STAT_NAMES)}
CMD_BASE = 0x018                           # base map CMD register: bit 2 takes the snapshot (also of the ITCH counter window)
CTRL = dict(en=1, arm=2, kill=4, spec=8, halt=16, strict=32)
CMD = dict(clr_cnt=1, clr_flags=2, clr_book=4, clr_pos=8, clr_ref=16, rp_start=32, tcp_load=64, lat_clr=128, cap_clr=256, rp_stop=512, commit=1024)
TIMING_DEPENDENT = ("spec", "abort", "late_abort", "rej_busy")
HS_NS = 1000                               # time for a register write to cross to the core clock and a counter snapshot to cross back, with margin


def cw(addr_name: str) -> int:
    return ADDR[addr_name]


@dataclass
class Plan:
    ops: list = field(default_factory=list)
    reads: list = field(default_factory=list)       # tags in order

    def w(self, addr: int, v: int) -> "Plan":
        self.ops.append(("W", addr, v & 0xFFFFFFFF)); return self

    def r(self, addr: int, tag: str) -> "Plan":
        self.ops.append(("R", addr, tag)); self.reads.append(tag); return self

    def d(self, ns: int) -> "Plan":
        self.ops.append(("D", ns)); return self

    def link(self) -> "Plan":
        self.ops.append(("L",)); return self

    def poll(self, addr: int, mask: int, value: int, timeout_ms: int) -> "Plan":
        self.ops.append(("POLL", addr, mask, value, timeout_ms)); return self

    def mark(self, text: str) -> "Plan":
        self.ops.append(("P", text)); return self

    def script(self) -> str:
        """The plan as the testbench's script (POLL becomes a wait of its timeout, at most 200 us)."""
        out = []
        for op in self.ops:
            k = op[0]
            if k == "W":
                out.append(f"W {op[1]:03x} {op[2]:08x}")
            elif k == "R":
                out.append(f"R {op[1]:03x}")
            elif k == "D":
                out.append(f"D {op[1]}")
            elif k == "L":
                out.append("L")
            elif k == "POLL":
                out.append(f"D {min(op[4] * 1000, 200_000)}")
            elif k == "P":
                out.append(f"P {op[1]}")
        out.append("E")
        return "\n".join(out) + "\n"

    def run(self, t, sleep=time.sleep) -> dict:
        """Execute on a Transport (rd, wr) and return {tag: value} for the reads in order; D waits ns (at least 1 ms of host time), POLL polls until the register matches."""
        res = {}
        for op in self.ops:
            k = op[0]
            if k == "W":
                t.wr(op[1], op[2])
            elif k == "R":
                res[op[2]] = t.rd(op[1])
            elif k == "D":
                sleep(max(op[1] * 1e-9, 0.0005))
            elif k == "POLL":
                end = time.time() + op[4] / 1000
                while (t.rd(op[1]) & op[2]) != op[3] and time.time() < end:
                    sleep(0.005)
            elif k == "L":
                end = time.time() + 5
                while time.time() < end and (t.rd(0x014) & 0x203) != 0x203:
                    sleep(0.02)
        return res


def decode_log(plan: Plan, log: str) -> dict:
    """The values of the plan's reads from the testbench's `RD <addr> <data>` lines, in order."""
    rd = [(int(l.split()[1], 16), int(l.split()[2], 16)) for l in log.splitlines() if l.startswith("RD ")]
    assert len(rd) == len(plan.reads), f"{len(rd)} reads in the log, {len(plan.reads)} in the plan"
    return {tag: v for tag, (a, v) in zip(plan.reads, rd)}


# ---------------------------------------------------------------------------------------------------- building blocks of a plan
def configure(p: Plan, cfg: Cfg, *, spec=False, strict=False, feed_ip="192.168.58.10", feed_port=5810, tcp_seq=1, tcp_ack=1, en=True, rp_loops=0) -> Plan:
    """Write the configuration registers (the order is not significant: the limits are staged and the IT_CMD at the end commits them in one clock, brief 188), then the clears and TCP_LOAD."""
    ctrl = (CTRL["en"] if en else 0) | (CTRL["arm"] if cfg.arm else 0) | (CTRL["kill"] if cfg.kill else 0) | (CTRL["spec"] if spec else 0) | (CTRL["halt"] if cfg.halt_on_gap else 0) | (CTRL["strict"] if strict else 0)
    p.w(ADDR["IT_CTRL"], ctrl)
    for n, v in (("IT_THR", cfg.thr), ("IT_QTY", cfg.qty), ("IT_MAXQTY", cfg.max_qty), ("IT_MAXPOS", cfg.max_pos), ("IT_BAND", cfg.band), ("IT_PXOFF", cfg.px_off), ("IT_MINQTY", cfg.minqty)):
        p.w(ADDR[n], v)
    p.w(ADDR["IT_ORDF0"], ord(cfg.tif) | (ord(cfg.display) << 8) | (ord(cfg.capacity) << 16) | (ord(cfg.ise) << 24))
    p.w(ADDR["IT_ORDF1"], ord(cfg.cross) | (ord(cfg.custtype) << 8))
    for i in range(4):
        w = int.from_bytes(proto.alpha(cfg.watch[i], 8), "big")
        p.w(ADDR[f"IT_WATCH{i}_LO"], w & 0xFFFFFFFF).w(ADDR[f"IT_WATCH{i}_HI"], w >> 32)
    p.w(ADDR["IT_FEED_IP"], int.from_bytes(H.ip_bytes(feed_ip), "big")).w(ADDR["IT_FEED_PORT"], feed_port)
    p.w(ADDR["IT_TCP_SEQ"], tcp_seq).w(ADDR["IT_TCP_ACK"], tcp_ack).w(ADDR["RP_CFG"], rp_loops)
    p.d(HS_NS)
    p.w(ADDR["IT_CMD"], CMD["tcp_load"] | CMD["clr_cnt"] | CMD["clr_flags"] | CMD["clr_book"] | CMD["clr_pos"] | CMD["clr_ref"] | CMD["cap_clr"] | CMD["commit"])
    p.d(HS_NS * 4)             # the book is ready again some 300 clocks after CLR_BOOK
    return p


def load_replay(p: Plan, image: list[int]) -> Plan:
    for a, w in enumerate(image):
        p.w(ADDR["RP_WADDR"], a).w(ADDR["RP_WLO"], w & 0xFFFFFFFF).w(ADDR["RP_WHI"], w >> 32).d(400)
    p.d(HS_NS)
    return p


def snapshot(p: Plan) -> Plan:
    p.w(CMD_BASE, 0x4).d(HS_NS)
    return p


def read_stats(p: Plan, prefix="") -> Plan:
    snapshot(p)
    for i, n in enumerate(R.STAT_NAMES):
        p.r(R.STAT_BASE + 4 * i, prefix + n)
    return p


def read_capture(p: Plan, slots: int = 8, prefix="") -> Plan:
    for slot in range(slots):
        for e in (12, *range(12)):
            p.w(ADDR["CAP_ADDR"], (slot << 4) | e).d(HS_NS)
            snapshot(p)
            p.r(STAT["cap.lo"], f"{prefix}cap{slot}.{e}.lo").r(STAT["cap.hi"], f"{prefix}cap{slot}.{e}.hi").r(STAT["cap.echo"], f"{prefix}cap{slot}.{e}.echo")
    return p


def start_replay(p: Plan, wait_ms: int, frames: int) -> Plan:
    p.w(ADDR["IT_CMD"], CMD["rp_start"]).d(HS_NS)
    p.poll(STAT["rp.stat"], 0x100, 0, wait_ms)       # replay not busy (the simulation waits instead)
    return p


# ---------------------------------------------------------------------------------------------------- checks
def captured_frames(res: dict, prefix="") -> list[dict]:
    """The frames of the capture ring as {slot, valid, fcs_ok, length, tail (bytes 24 up to and including the FCS)}."""
    out = []
    for slot in range(8):
        e = f"{prefix}cap{slot}.12"
        if f"{e}.lo" not in res:
            break
        meta = res[f"{e}.lo"] | (res[f"{e}.hi"] << 32)
        if f"{prefix}cap{slot}.12.echo" in res:
            assert res[f"{prefix}cap{slot}.12.echo"] == (slot << 4) | 12, "capture echo"
        words = []
        for k in range(12):
            assert res[f"{prefix}cap{slot}.{k}.echo"] == (slot << 4) | k, "capture echo"
            words.append(res[f"{prefix}cap{slot}.{k}.lo"] | (res[f"{prefix}cap{slot}.{k}.hi"] << 32))
        out.append({"slot": slot, "valid": (meta >> 17) & 1, "fcs_ok": (meta >> 16) & 1, "length": meta & 0xFFFF, "tail": b"".join(w.to_bytes(8, "little") for w in words)})
    return out


def counters_vs_model(res: dict, model: Model, skip=TIMING_DEPENDENT, prefix="") -> dict:
    """{counter: (hardware, model)} for every counter of brief 110's path that differs (timing dependent ones excluded)."""
    return {n: (res[f"{prefix}itch.{n}"], model.cnt[n]) for n in COUNTERS if n not in skip and res[f"{prefix}itch.{n}"] != model.cnt[n]}


def order_frames_vs_model(res: dict, model: Model, *, my_mac=H.DEFAULTS["my_mac"], venue_mac=H.DEFAULTS["venue_mac"], my_ip=H.DEFAULTS["my_ip"], venue_ip=H.DEFAULTS["venue_ip"],
                          sport=H.DEFAULTS["sport"], dport=H.DEFAULTS["order_port"], seq0=1, ack=1, prefix="") -> dict:
    """The good (FCS ok) captured order frames, in the ring's order, against the model's order frames, byte for byte from byte 24 (the first 24 bytes are classified by the receiver, not kept).
    Only the last 8 frames the receiver saw are in the ring: when the model decided more orders, compare the LAST ones (and say so)."""
    by_slot = {c["slot"]: c for c in captured_frames(res, prefix)}
    n = res[f"{prefix}us.cap_n"]                                   # frames the ring has seen; frame f is in slot f % 8, the ring keeps the last 8
    chron = [by_slot[f % 8] for f in range(max(0, n - 8), n) if f % 8 in by_slot]
    caps = [c for c in chron if c["valid"]]
    ring_good = [c for c in caps if c["fcs_ok"]]
    exp = []
    seq = seq0
    for o in model.orders:
        exp.append((seq, o["frame"]))
        seq += 59
    problems = []
    k = min(len(ring_good), len(exp))
    for c, (sq, fr) in zip(ring_good[len(ring_good) - k:], exp[len(exp) - k:]):
        full = H.tcp_stub_frame(fr, my_mac=my_mac, venue_mac=venue_mac, my_ip=my_ip, venue_ip=venue_ip, sport=sport, dport=dport, seq=sq, ack=ack)
        if c["tail"][:117 - 24 - 4 + 0] != full[24:] or c["length"] != 117:
            problems.append(f"order with sequence {sq}: captured bytes differ from the model's frame")
    return {"captured": len(caps), "good": len(ring_good), "model_orders": len(exp), "compared": k, "problems": problems}
