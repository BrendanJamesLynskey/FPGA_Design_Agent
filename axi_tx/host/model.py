"""The transaction-level model of the brief 59A transactor: runs an assembled program the way the sequencer does
(loops, AREG, random fields from the data LFSR in the same order, the scoreboard) against a model of the target, and
predicts every transaction (kind, address, data, strobes, response) and every verdict counter. It has no clock: timing
(latency, the throttle LFSRs) is the RTL's alone, so the digest, which includes latency, is compared between the RTL in
simulation and the board, never with this model.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any

from axi_tx.host import regs
from axi_tx.host.program import OP, SET_NAMES, Program

LFSR_MASK = 0x8020_0003
M32 = 0xFFFF_FFFF


def lfsr_next(s: int) -> int:
    """axi_tx_lfsr.sv: Galois, right shift, feedback 0x80200003."""
    return (s >> 1) ^ (LFSR_MASK if s & 1 else 0)


def bmask(strb: int) -> int:
    return sum(0xFF << (8 * i) for i in range(4) if strb >> i & 1)


class MemTarget:
    """The AXI BRAM Controller (and axil_mem_model): words of a 2**aw_words-word memory, aliased, all OKAY. Partly written
    words are predicted only in their written bytes (the rest is unknown), so they are compared through the scoreboard."""
    def __init__(self, aw_words: int = 11, ignore_strb: bool = False) -> None:
        self.n, self.mem, self.known, self.ignore_strb = 1 << aw_words, {}, {}, ignore_strb

    def write(self, addr: int, data: int, strb: int) -> str:
        i = (addr >> 2) % self.n
        st = 0xF if self.ignore_strb else strb
        m = bmask(st)
        self.mem[i] = (self.mem.get(i, 0) & ~m | data & m) & M32
        self.known[i] = self.known.get(i, 0) | st
        return "OKAY"

    def read(self, addr: int) -> tuple[int | None, str]:
        """A word this run has not written is unknown: block RAM keeps its contents across runs (and resets)."""
        i = (addr >> 2) % self.n
        return (self.mem[i] if self.known.get(i) == 0xF else None), "OKAY"


class PeriphTarget:
    """axil_demo_periph: ID, R0-R3, COUNT (unpredictable here), WCOUNT, BUG; SLVERR on read-only, DECERR from 0x20."""
    ID = 0x5950_4C31

    def __init__(self, bug: str = "none") -> None:
        self.r, self.wcount, self.bug = [0, 0, 0, 0], 0, regs.LITE_BUGS[bug]

    def write(self, addr: int, data: int, strb: int) -> str:
        w = (addr & 0xFFF) >> 2
        if 1 <= w <= 4:
            m = bmask(0xF if self.bug == 4 else strb)
            self.r[w - 1] = (self.r[w - 1] & ~m | data & m) & M32
            self.wcount += 1
            return "EXOKAY" if (self.bug == 5 and w == 4) else "OKAY"
        return "SLVERR" if w < 8 else "DECERR"

    def read(self, addr: int) -> tuple[int | None, str]:
        w = (addr & 0xFFF) >> 2
        if w >= 8:
            return 0, "DECERR"
        return {0: self.ID, 1: self.r[0], 2: self.r[1], 3: self.r[2], 4: self.r[3], 5: None, 6: self.wcount,
                7: self.bug}[w], "OKAY"


@dataclass
class Prediction:
    txns: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    packets: list[dict[str, int]] = field(default_factory=list)
    ended: str = "done"


def run(prog: Program, target: Any = None, max_steps: int = 2_000_000) -> Prediction:
    """Execute prog.words like axi_tx_core's sequencer. target: MemTarget / PeriphTarget (default from prog.target)."""
    if target is None:
        target = PeriphTarget(prog.lite_bug) if prog.target == "periph" else MemTarget()
    w = prog.words
    pc, stack, areg, sb_base, d = 0, [], 0, 0, 1
    sb: dict[int, tuple[int, int]] = {}
    c = {k: 0 for k in ("n_txn", "sb_checked", "sb_mism", "sb_unchecked", "exp_mism", "resp_mism", "stream_packets",
                        "stream_beats")}
    pred = Prediction()
    steps = 0

    def draw() -> int:
        nonlocal d
        v = d
        d = lfsr_next(d)
        return v

    while True:
        steps += 1
        if steps > max_steps:
            pred.ended = "step limit"
            break
        if pc >= len(w) // 4:
            pred.ended = "ran off the program"
            break
        w0, w1, w2, w3 = w[4 * pc:4 * pc + 4]
        op = w0 >> 28
        if op == OP["end"]:
            break
        if op in (OP["write"], OP["read"]):
            is_w = op == OP["write"]
            addr, data, strb = w1, w2, w0 & 0xF
            if w0 >> 8 & 1:
                addr = ((addr & ~w3) | (draw() & w3)) & ~3 & M32
            if is_w and w0 >> 7 & 1:
                data = draw()
            if is_w and w0 >> 23 & 1:
                strb = draw() & 0xF
            if w0 >> 9 & 1:
                addr, areg = areg, (areg + 4) & M32
            addr &= ~3 & M32
            if is_w:
                resp = target.write(addr, data, strb)
                got = data
            else:
                got, resp = target.read(addr)
            t = {"kind": "write" if is_w else "read", "addr": addr, "data": got, "strb": strb if is_w else None,
                 "resp": resp, "sb_mism": False, "exp_mism": False, "resp_mism": False}
            if w0 >> 6 & 1 and regs.RESP[(w0 >> 4) & 3] != resp:
                t["resp_mism"] = True
            if not is_w and w0 >> 24 & 1:
                m = bmask(w0 & 0xF)
                t["exp_mism"] = None if got is None else bool((got ^ w2) & m)
            in_win = (addr >> 12) == (sb_base >> 12)
            if w0 >> 22 & 1 and in_win and resp == "OKAY":
                i = (addr >> 2) & 0x3FF
                bv, sd = sb.get(i, (0, 0))
                if is_w:
                    m = bmask(strb)
                    sb[i] = (bv | strb, (sd & ~m | data & m) & M32)
                elif bv == 0:
                    c["sb_unchecked"] += 1
                else:
                    c["sb_checked"] += 1
                    t["sb_mism"] = None if got is None else bool((got ^ sd) & bmask(bv))
            for k in ("sb_mism", "exp_mism", "resp_mism"):
                if t[k]:
                    c[k] += 1
            c["n_txn"] += 1
            pred.txns.append(t)
            pc += 1
        elif op == OP["wait"] or op == OP["swait"] or op == OP["waitev"]:
            pc += 1
        elif op == OP["loop"]:
            stack.append([pc + 1, max(w1, 1)])
            pc += 1
        elif op == OP["endloop"]:
            if not stack:
                pred.ended = "error"
                break
            if stack[-1][1] > 1:
                stack[-1][1] -= 1
                pc = stack[-1][0]
            else:
                stack.pop()
                pc += 1
        elif op == OP["set"]:
            name = SET_NAMES.get(w0 & 0xFF)
            if name == "seed_data":
                d = w1 or 1
            elif name == "areg":
                areg = w1 & ~3 & M32
            elif name == "sb_base":
                sb_base = w1
            pc += 1
        elif op == OP["ssend"]:
            first = draw() if w0 >> 6 & 1 else w2
            n = max(w1 & 0xFFFF, 1)
            if w0 >> 5 & 1:
                pred.packets.append({"len": n, "first": first, "keep_last": w0 & 0xF, "no_last": w0 >> 4 & 1})
                c["stream_beats"] += n
                c["stream_packets"] += 0 if w0 >> 4 & 1 else 1
            pc += 1
        else:
            pred.ended = "error"
            break
    pred.counts = c
    return pred


def log_word0(kind: str, resp: str, sb_m: bool, exp_m: bool, resp_m: bool, lat: int) -> int:
    return ((2 if kind == "read" else 1) << 30) | (regs.RESP.index(resp) << 28) | (int(sb_m) << 27) | \
        (int(exp_m) << 26) | (int(resp_m) << 25) | (lat & 0xFF_FFFF)


def decode_log(entries: list[tuple[int, int, int]]) -> list[dict[str, Any]]:
    out = []
    for w0, w1, w2 in entries:
        out.append({"kind": {1: "write", 2: "read"}.get(w0 >> 30, "?"), "resp": regs.RESP[(w0 >> 28) & 3],
                    "sb_mism": bool(w0 >> 27 & 1), "exp_mism": bool(w0 >> 26 & 1), "resp_mism": bool(w0 >> 25 & 1),
                    "latency": w0 & 0xFF_FFFF, "addr": w1, "data": w2})
    return out


def digest(entries: list[tuple[int, int, int]]) -> int:
    """The RTL's digest: CRC-32 of the little-endian bytes of (w0, addr, data) of every transaction, in order."""
    b = b"".join(x.to_bytes(4, "little") for e in entries for x in e)
    return zlib.crc32(b) & M32


def compare(pred: Prediction, observed: list[dict[str, Any]]) -> dict[str, Any]:
    """The first transaction where the observed log differs from the model (unknown read data is not compared)."""
    n = min(len(pred.txns), len(observed))
    for i in range(n):
        p, o = pred.txns[i], observed[i]
        diffs = [k for k in ("kind", "addr", "resp") if p[k] != o[k]]
        if p["data"] is not None and p["data"] != o["data"]:
            diffs.append("data")
        if diffs:
            return {"match": False, "first_divergence": i, "fields": diffs, "model": p, "observed": o}
    return {"match": True, "compared": n}
