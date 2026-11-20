"""Brief 113: a synthetic Bench Feed v1 stream as 10GBASE-R words for the receive port of the whole core (tb_ml_core.sv), and the twin's expectation for every frame.

Synthetic data only: the order-flow generator of brief 87 (`lobsim.simulate`, seeded) and a stress set of random messages, plus the cases that must not move the stage: a bad FCS, a frame longer than
its IPv4 length, a message for another instrument, a two-message frame (too long to act on), a wrong UDP port, a wrong header. Output: `words.hex` (one 64-bit word a line, the Python PCS transmit model's
output, idles first so the receiver locks) and `expect.json`.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from designs.b58a_trigger.model import benchfeed as bf
from designs.b87_ml_trading.model import lobsim as L
from designs.b96_kr260_10g.model import pcs
from designs.b96_kr260_10g.rm_gp_ml.model.twin import Twin

INST = 3
OTHER_INST = 9
THR = 10002                # the rule's price threshold in the bench (the generator's ask prices sit around 10,000, so some asks are at or below it)
LEAD_WORDS = 4000          # idle words before the first frame (the bench links up after about 1,750 words; the receiver then locks within about 300)
TAIL_WORDS = 600


def orderflow_msgs(n_events: int, seed: int = 4242, inst: int = INST) -> list[bf.Msg]:
    """The 87 generator's events as one-message Bench Feed messages (see designs/b87_ml_trading/tests/b87_integ_cocotb.py::stream_msgs)."""
    r = L.simulate(seed, n_events)
    msgs, prev = [], None
    for t, (kind, side, px, size) in enumerate(r["events"]):
        pb, qb, pa, qa = (int(v) for v in r["best"][t])
        if kind == "TRADE" and prev is not None:
            s_px, s_sz = (prev[2], prev[3]) if side == 1 else (prev[0], prev[1])
            if s_sz > 1:
                msgs.append(bf.Msg(bf.TRADE, bf.ASK if side == 1 else bf.BID, inst, s_px, min(size, s_sz - 1)))
                prev = (prev[0], prev[1] - (min(size, s_sz - 1) if side == 0 else 0), prev[2], prev[3] - (min(size, s_sz - 1) if side == 1 else 0))
                continue
        if prev is None or (pb, qb) != (prev[0], prev[1]):
            msgs.append(bf.Msg(bf.ADD, bf.BID, inst, pb, qb))
        if prev is None or (pa, qa) != (prev[2], prev[3]):
            msgs.append(bf.Msg(bf.ADD, bf.ASK, inst, pa, qa))
        prev = (pb, qb, pa, qa)
    return msgs


def stress_msgs(n: int, seed: int = 87, inst: int = INST) -> list[bf.Msg]:
    """Random messages that reach the feature unit's edge cases: sizes above 255, spreads above 15, crossed and empty sides, order-flow terms that clip at +/-127; prices around the rule's 99.75."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        t = rng.choice([bf.ADD, bf.ADD, bf.MODIFY, bf.TRADE, bf.CANCEL])
        side = rng.choice([bf.BID, bf.ASK])
        px = THR + rng.choice([-40, -20, -3, -1, 0, 1, 3, 20, 40])
        sz = rng.choice([1, 5, 200, 300, 1000, 70000])
        out.append(bf.Msg(t, side, inst, px, sz))
    return out


class Gap:
    """Idle words between frames."""
    CHOICES = [2, 2, 3, 5, 12, 40, 150]

    def __init__(self, seed: int, dense: bool = True) -> None:
        self.rng = random.Random(seed)
        self.dense = dense

    def __call__(self) -> int:
        return self.rng.choice(self.CHOICES) if self.dense else 300


def build(items: list[dict], *, gap: Gap, lead: int = LEAD_WORDS, tail: int = TAIL_WORDS) -> list[tuple[int, int]]:
    """XGMII words: lead idles, then each item's frame followed by a gap of idle words, then tail idles. An item: {'frame': bytes without FCS, 'bad_fcs': bool}."""
    words = [pcs.IDLE_WORD] * lead
    for it in items:
        fw = pcs.frame_words(it["frame"])
        if it.get("bad_fcs"):
            # flip one bit of the last FCS byte (the byte before the terminate lane): the CRC no longer matches, the message fields are unchanged
            fw = list(fw)
            d, c = fw[-1]
            lane = next(i for i in range(8) if (c >> i) & 1 and ((d >> (8 * i)) & 0xFF) == pcs.TERM)
            fw[-1] = (d ^ (1 << (8 * (lane - 1))), c)
        words += fw
        words += [pcs.IDLE_WORD] * gap()
    words += [pcs.IDLE_WORD] * tail
    return words


def to_gt(words: list[tuple[int, int]]) -> list[int]:
    """The 64-bit GT words the transmit PCS model emits for the XGMII words (the gearbox pause: a word offered while adv = 0 is offered again)."""
    tx = pcs.TxPcs()
    out, i = [], 0
    while i < len(words):
        d, c = words[i]
        take = tx.adv
        out.append(tx.step(d, c))
        if take:
            i += 1
    return out


def frame_for(m: bf.Msg, seq: int, **kw) -> bytes:
    return bf.feed_frame(seq, [m], **kw)


def make_stream(seed: int = 4242, n_events: int = 300, n_stress: int = 150, veto: bool = False, dense: bool = True) -> tuple[list[int], dict]:
    """The mixed stream of the bit-exact check, with the twin's expectation for every frame the rule path accepts."""
    rng = random.Random(seed)
    msgs = orderflow_msgs(n_events, seed) + stress_msgs(n_stress, seed=seed + 1) + orderflow_msgs(150, seed + 7)
    items, kinds = [], []
    seq = 1
    for m in msgs:
        r = rng.random()
        it = {"msg": m}
        if r < 0.04:
            it.update(bad_fcs=True, kind="bad_fcs")
        elif r < 0.07:
            it.update(trailing=bytes(8), kind="long_frame")                   # frame longer than the IPv4 length: the verdict is bad
        elif r < 0.12:
            it.update(inst=OTHER_INST, kind="other_inst")
        elif r < 0.14:
            it.update(kind="two_msgs")
        elif r < 0.16:
            it.update(kind="bad_port")
        elif r < 0.17:
            it.update(kind="bad_magic")
        else:
            it.update(kind="good")
        kinds.append(it["kind"])
        mm = it["msg"]
        if it["kind"] == "other_inst":
            mm = bf.Msg(mm.type, mm.side, OTHER_INST, mm.price, mm.size)
        if it["kind"] == "two_msgs":
            fr = bf.feed_frame(seq, [mm, mm])
        elif it["kind"] == "bad_port":
            fr = bf.feed_frame(seq, [mm], dport=5900)
        elif it["kind"] == "bad_magic":
            fr = bf.feed_frame(seq, [mm], magic=0x4247)
        else:
            fr = bf.feed_frame(seq, [mm])
        if it["kind"] == "long_frame":
            fr = fr + bytes(8)
        it["frame"] = fr
        it["m"] = mm
        seq += 1
        items.append(it)
    tw = Twin(inst=INST, thr=THR, veto_mode=veto)
    exp = []
    for it in items:
        if it["kind"] in ("good", "bad_fcs", "long_frame", "other_inst"):
            good = it["kind"] in ("good", "other_inst")
            o = tw.frame(it["m"], good)
            exp.append({"kind": it["kind"], "type": it["m"].type, "side": it["m"].side, "px": it["m"].price, "sz": it["m"].size, "trk": o.trk, "feat": o.feat, "cls": o.cls, "hit": o.hit,
                        "dec": o.dec, "veto": o.veto, "order": o.order, "applied": o.applied})
    words = to_gt(build(items, gap=Gap(seed, dense)))
    summary = {"frames": len(items), "kinds": {k: kinds.count(k) for k in sorted(set(kinds))}, "observed": len(exp), "twin_counts": tw.n, "veto_mode": veto}
    return words, {"expect": exp, "summary": summary}


def write(out_dir: Path, **kw) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    words, e = make_stream(**kw)
    (out_dir / "words.hex").write_text("\n".join(f"{w:016x}" for w in words) + "\n")
    e["nw"] = len(words)
    (out_dir / "expect.json").write_text(json.dumps(e, indent=0))
    return e["summary"]


if __name__ == "__main__":
    import sys
    print(json.dumps(write(Path(sys.argv[1]), veto=(len(sys.argv) > 2 and sys.argv[2] == "veto")), indent=1))
