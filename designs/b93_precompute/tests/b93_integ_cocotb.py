"""cocotb bench: the 58A trigger_core with a decision model behind the rule table, precomputed (ML_PRE 1-3) or not (0).

- features_and_class_match_the_twin / edge_cases: as brief 87 (the 87 twin; the model's integer twin), 400 generator
  messages and 300 edge-case messages; features and classes are compared message by message.
- bad_fcs_frames_are_processed_speculatively: every third frame has a bad FCS; features and classes still match the twin.
  (A message that has its instrument field but no price field cannot occur on the wire: the FCS bytes are passed to the
  parser as data and finish the price field. Non-commit of such a message is tested in tb/tb_feat_pre.sv.)
- stage_latency: the 58A stage timestamps with the model off and on, speculative and safe, written to $B93_INTEG_OUT.
- veto: the gate vetoes an order whose side disagrees with the class, same as brief 87.
"""
from __future__ import annotations

import json
import os

import cocotb
import numpy as np
from cocotb.triggers import ReadOnly, RisingEdge

from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import Config
from designs.b58a_trigger.tests.b58a_cocotb import Bench
from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import lobsim as L
from designs.b87_ml_trading.model.gen_rtl import MODELS
from designs.b87_ml_trading.tests.b87_integ_cocotb import FLO, INST, stream_msgs, stress_msgs
from designs.b89_lutnet_gen.lutgen import model as M89

ML_ARM = int(os.environ.get("B93_ML_ARM", "1"))
ML_PRE = int(os.environ.get("B93_ML_PRE", "0"))
LG = json.loads((MODELS.parents[1] / "b89" / "models" / "lg_small_seed2.json").read_text())
GBT = json.loads((MODELS / "gbt.json").read_text())


def predict(X):
    return (A.gbt_predict_int(GBT, X) if ML_ARM == 1 else M89.twin_predict(LG, X)).tolist()


def twin(msgs):
    """The 87 feature twin, then this arm's model (the book semantics are 58A's, as brief 87's twin)."""
    book = [0, 0, 0, 0]
    fs = L.FeatureState(0, 0, 0, 0)
    pend, feats = 0, []
    for m in msgs:
        feats.append(fs.update(*book, pend))
        pend = (1 if m.side == bf.ASK else -1) if m.type == bf.TRADE else 0
        if m.type == bf.ADD:
            if m.side == bf.BID:
                book[0], book[1] = m.price, m.size
            else:
                book[2], book[3] = m.price, m.size
        elif m.type == bf.CANCEL:
            if m.side == bf.BID:
                book[0], book[1] = 0, 0
            else:
                book[2], book[3] = 0, 0
        elif m.type == bf.TRADE:
            i = 1 if m.side == bf.BID else 3
            if m.price == book[i - 1] and book[i] != 0:
                book[i] = max(0, book[i] - m.size)
                if book[i] == 0:
                    book[i - 1] = 0
    return feats, predict(np.array(feats, dtype=np.int64))


async def watch(dut, out: list):
    """Events in clock order: i (a message's instrument field complete), p (price field complete), f (features), c."""
    g = dut.g_ml
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.m_inst_v.value):
            out.append(("i", int(dut.m_inst.value)))
        if int(dut.m_px_v.value):
            out.append(("p", 0))
        if int(g.feat_v.value):
            v = int(g.feat.value)
            out.append(("f", [(v >> lo) & ((1 << w) - 1) for lo, w in zip(FLO, L.FEATURE_BITS)]))
        if int(g.cls_v.value):
            out.append(("c", int(g.cls.value)))


def committed(seen: list):
    """Features/classes of the messages whose price field completed, in order. Events are grouped by message (an `i`
    starts a group); a group with features but no price field (the vector was computed early, then the frame stopped)
    is dropped here and counted."""
    groups, cur = [], None
    for k, x in seen:
        if k == "i":
            cur = {"f": None, "c": None, "p": False}
            groups.append(cur)
        elif cur is not None:
            if k == "p":
                cur["p"] = True
            elif k == "f":
                cur["f"] = x
            elif k == "c":
                cur["c"] = x
    done = [g for g in groups if g["p"] and g["f"] is not None]
    partial = sum(1 for g in groups if not g["p"] and g["f"] is not None)
    return [g["f"] for g in done], [g["c"] for g in done], partial


def committed_base(seen: list):
    """ML_PRE 0: the vector appears one clock after the price field; every f is a committed message."""
    return [x for k, x in seen if k == "f"], [x for k, x in seen if k == "c"], 0


async def run_frames(dut, msgs, per=8, cut_every=0):
    b = Bench(dut)
    await b.start()
    await b.config(Config(spec_en=True, bucket=100, max_pos=100000), None)
    await b.wr(0x02A, 1 | INST << 16)
    seen: list = []
    cocotb.start_soon(watch(dut, seen))
    seq = 1
    kept = []
    n = 0
    for i in range(0, len(msgs), per):
        part = msgs[i:i + per]
        fr = bf.feed_frame(seq, part)
        n += 1
        kept += part                                   # a bad-FCS frame's messages are processed speculatively
        seq += len(part)
        b.send(bf.with_fcs(fr, bad=bool(cut_every and n % cut_every == 0)), gap=200)
    await b.drain(1500)
    return seen, kept


def check(dut, seen, kept, tag):
    got = committed(seen) if ML_PRE else committed_base(seen)
    got_f, got_c, partial = got
    exp_f, exp_c = twin(kept)
    assert len(got_f) == len(kept), (tag, len(got_f), len(kept))
    bad = [i for i in range(len(kept)) if got_f[i] != exp_f[i]]
    assert not bad, (tag, bad[:3], [(got_f[i], exp_f[i]) for i in bad[:2]])
    assert got_c == exp_c, (tag, [i for i in range(len(kept)) if got_c[i] != exp_c[i]][:5])
    return exp_f, exp_c, partial


@cocotb.test()
async def features_and_class_match_the_twin(dut):
    msgs = stream_msgs(400)
    seen, kept = await run_frames(dut, msgs)
    exp_f, exp_c, _ = check(dut, seen, kept, "generator")
    dut._log.info(f"{len(kept)} messages match; classes {[exp_c.count(k) for k in range(3)]}")
    out = os.environ.get("B93_TWIN_OUT")
    if out:
        with open(out, "w") as f:
            json.dump({"ml_arm": ML_ARM, "ml_pre": ML_PRE, "messages": len(kept), "features_match": True,
                       "classes_match": True, "class_counts": [exp_c.count(k) for k in range(3)]}, f, indent=1)


@cocotb.test()
async def other_instruments_between_tracked_messages(dut):
    """Untracked messages (another instrument, its own book entry) between the tracked ones: the unit must ignore them."""
    import random
    rng = random.Random(5)
    base = stream_msgs(160)
    msgs, kept = [], []
    for m in base:
        msgs.append(m)
        kept.append(m)
        for _ in range(rng.choice([0, 1, 1, 2])):
            msgs.append(bf.Msg(rng.choice([bf.ADD, bf.TRADE]), rng.choice([bf.BID, bf.ASK]), INST + 4,
                               10000 + rng.randint(-5, 5), rng.randint(1, 300)))
    seen, _ = await run_frames(dut, msgs)
    exp_f, exp_c, _ = check(dut, seen, kept, "mixed")
    out = os.environ.get("B93_TWIN_OUT")
    if out:
        with open(out.replace(".json", "_mixed.json"), "w") as f:
            json.dump({"ml_arm": ML_ARM, "ml_pre": ML_PRE, "tracked_messages": len(kept), "untracked_messages": len(msgs) - len(kept),
                       "match_twin": True}, f, indent=1)


@cocotb.test()
async def edge_cases(dut):
    msgs = stress_msgs(300)
    seen, kept = await run_frames(dut, msgs)
    exp_f, exp_c, _ = check(dut, seen, kept, "edge")
    F = np.array(exp_f)
    reach = {"size_saturated": int((F[:, 0] == 255).sum() + (F[:, 1] == 255).sum()), "spread_15": int((F[:, 2] == 15).sum()),
             "ofi_clipped": int(((F[:, 5] == 1) | (F[:, 5] == 255)).sum()), "empty_side": int(((F[:, 0] == 0) | (F[:, 1] == 0)).sum())}
    assert all(v > 0 for v in reach.values()), reach
    out = os.environ.get("B93_TWIN_OUT")
    if out:
        with open(out.replace(".json", "_edge_cases.json"), "w") as f:
            json.dump({"ml_arm": ML_ARM, "ml_pre": ML_PRE, "messages": len(kept), "features_match": True,
                       "classes_match": True, "edge_cases_reached": reach}, f, indent=1)


@cocotb.test()
async def bad_fcs_frames_are_processed_speculatively(dut):
    """Every third frame has a bad FCS: its messages still reach the features (speculation), as in the baseline."""
    msgs = stream_msgs(240)
    seen, kept = await run_frames(dut, msgs, per=4, cut_every=3)
    check(dut, seen, kept, "badfcs")
    out = os.environ.get("B93_TWIN_OUT")
    if out:
        with open(out.replace(".json", "_badfcs.json"), "w") as f:
            json.dump({"ml_arm": ML_ARM, "ml_pre": ML_PRE, "messages": len(kept), "match_twin": True}, f, indent=1)


@cocotb.test()
async def stage_latency(dut):
    """The 58A trigger (an ADD on the ask below 100.00 fires a buy), model off and on, speculative and safe."""
    b = Bench(dut)
    await b.start()
    rules = [{"match": {"types": ["ADD"], "side": "ask", "instrument": INST, "price": {"op": "<", "value": "100.00"}},
              "action": {"order": {"side": "buy", "qty": 1, "price": {"mode": "message"}}}}]
    table = rl.table_words(rl.validate_table(rules))
    gated: list[int] = []
    rfire: list[int] = []
    clsv: list[int] = []
    instv: list[int] = []

    async def mon():
        n = 0
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            n += 1
            if int(dut.u_rules.fire_v.value):
                rfire.append(n)
            if int(dut.fire_v.value):
                gated.append(n)
            if int(dut.g_ml.cls_v.value):
                clsv.append(n)
            if int(dut.m_inst_v.value):
                instv.append(n)
    cocotb.start_soon(mon())
    res = {"ml_arm": ML_ARM, "ml_pre": ML_PRE, "clock_ns": 8, "clock_mhz": 125, "instrument": INST,
           "points": {"price_complete_in": "the clock the last price byte enters mac_rx (core side)",
                      "decision": "fire_v into the interlocks (after the gate when the model is on)",
                      "first_byte_out": "mac_tx's first preamble byte (core side)", "resolution": "one clock, 8 ns"},
           "modes": {}}
    seq = 500000
    for spec in (True, False):
        await b.config(Config(spec_en=spec, bucket=100, max_pos=100000), table)
        for en in (0, 1):
            await b.wr(0x02A, en | INST << 16)
            prime = [bf.Msg(bf.ADD, bf.BID, INST, 9900, 200), bf.Msg(bf.ADD, bf.ASK, INST, 10000, 5)]
            b.send(bf.with_fcs(bf.feed_frame(seq, prime)), gap=300)
            seq += 2
            await b.drain(300)
            base = {k: len(v) for k, v in b.events.items()}
            g0, r0 = len(gated), len(rfire)
            c0, i0 = len(clsv), len(instv)
            n0 = len(b.sfd_cycles) - 1
            fr = bf.with_fcs(bf.feed_frame(seq, [bf.Msg(bf.ADD, bf.ASK, INST, 9950, 1)]))
            seq += 1
            v0 = await b.rd(0x02C)
            b.send(fr, gap=400)
            await b.drain(600)
            ev = {k: b.events[k][base[k]] for k in b.events if len(b.events[k]) > base[k]}
            px_in = b.byte_cycles[n0 + 1][8 + 57]
            kept = "first" in ev
            r = {"model_enabled": bool(en), "class": await b.rd(0x02B), "vetoed": (await b.rd(0x02C)) - v0,
                 "order_kept": kept,
                 "stages_cycles": {"mac_rx + feed_rx (price byte in -> msg_px_v)": ev["px"] - px_in,
                                   "rules (msg_px_v -> rule fire)": ev["fire"] - ev["px"],
                                   "model gate (rule fire -> decision)": gated[g0] - rfire[r0]},
                 "tick_to_decision": ev["fire"] - px_in + gated[g0] - rfire[r0]}
            if en:
                r["class_valid_clocks_after_instrument_field"] = clsv[c0] - instv[i0]
                r["class_valid_clocks_before_rule_fire"] = rfire[r0] - clsv[c0]
            if kept:
                r["stages_cycles"]["interlocks (decision -> grant)"] = ev["grant"] - ev["fire"] - (gated[g0] - rfire[r0])
                r["stages_cycles"]["order_ctl (grant -> tx_start)"] = ev["start"] - ev["grant"]
                r["stages_cycles"]["mac_tx (tx_start -> first preamble byte)"] = ev["first"] - ev["start"]
                r["decision_to_first_byte"] = ev["first"] - px_in
            res["modes"][f"{'speculative' if spec else 'safe'}_model_{'on' if en else 'off'}"] = r
            if not en:
                assert r["stages_cycles"]["model gate (rule fire -> decision)"] == 0, r
    dut._log.info(json.dumps(res, indent=1))
    for k, r in res["modes"].items():
        if r["model_enabled"]:
            g = r["stages_cycles"]["model gate (rule fire -> decision)"]
            assert g == (1 if ML_PRE == 0 and ML_ARM in (1, 4) else 0), (k, r)
    out = os.environ.get("B93_INTEG_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(res, f, indent=1)


@cocotb.test()
async def veto_when_the_model_disagrees(dut):
    b = Bench(dut)
    await b.start()
    seq, got, vetoes = 700000, [], 0
    for side, bside, px in (("sell", "bid", 9950), ("buy", "ask", 9950)):
        rules = [{"match": {"types": ["ADD"], "side": bside, "instrument": INST,
                            "price": {"op": ">" if side == "sell" else "<", "value": "99.00" if side == "sell" else "100.00"}},
                  "action": {"order": {"side": side, "qty": 1, "price": {"mode": "message"}}}}]
        await b.config(Config(spec_en=True, bucket=100, max_pos=100000), rl.table_words(rl.validate_table(rules)))
        for en in (1, 0):
            await b.wr(0x02A, en | INST << 16)
            b.send(bf.with_fcs(bf.feed_frame(seq, [bf.Msg(bf.ADD, bf.BID, INST, 9900, 200),
                                                   bf.Msg(bf.ADD, bf.ASK, INST, 10000, 5)])), gap=300)
            seq += 2
            await b.drain(300)
            n_first, v0 = len(b.events["first"]), await b.rd(0x02C)
            trig = bf.Msg(bf.ADD, bf.BID if side == "sell" else bf.ASK, INST, px, 1)
            b.send(bf.with_fcs(bf.feed_frame(seq, [trig])), gap=400)
            seq += 1
            await b.drain(600)
            cls = await b.rd(0x02B)
            r = {"side": side, "en": en, "class": cls, "vetoed": await b.rd(0x02C) - v0,
                 "sent": len(b.events["first"]) - n_first}
            got.append(r)
            agree = cls == (2 if side == "buy" else 0)
            if en:
                assert r["sent"] == int(agree) and r["vetoed"] == int(not agree), r
                vetoes += r["vetoed"]
            else:
                assert r["sent"] == 1 and r["vetoed"] == 0, r
    dut._log.info(f"veto test: {got}")
    assert vetoes >= 1, got
