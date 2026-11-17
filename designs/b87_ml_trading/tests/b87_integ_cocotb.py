"""cocotb bench: the 58A trigger_core with a decision model behind the rule table (ML_ARM > 0).

- ml_features_and_class_match_the_twin: a stream from our order-flow generator, as Bench Feed messages for one
  instrument; every feature vector and class the fabric computes is compared with the Python twin
  (model/lobsim.py FeatureState fed with the 58A book's semantics, then the arm's integer model).
- stage_latency_with_and_without_model: one trigger, the 58A stage timestamps, model off and on (register 0x02A),
  speculative and safe; written to $B87_INTEG_OUT.
"""
from __future__ import annotations

import json
import os

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import Config
from designs.b58a_trigger.tests.b58a_cocotb import Bench
from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import lobsim as L

ML_ARM = int(os.environ.get("B87_ML_ARM", "1"))
ARM_MODEL = {1: ("gbt", A.gbt_predict_int), 2: ("lutnet", A.lut_predict_int), 3: ("mlp", A.mlp_predict_int)}[ML_ARM]
INST = 3
FLO = [0, 8, 16, 20, 23, 28, 36]


def model():
    from designs.b87_ml_trading.model.gen_rtl import MODELS
    return json.loads((MODELS / f"{ARM_MODEL[0]}.json").read_text())


def stream_msgs(n_events: int, seed: int = 4242) -> list[bf.Msg]:
    """Generator events as Bench Feed messages: a trade becomes a TRADE at the hit side's best price (size kept below
    that side's size, so the 58A book never empties a side); any other event an ADD that sets the side's new best."""
    r = L.simulate(seed, n_events)
    msgs, prev = [], None
    for t, (kind, side, px, size) in enumerate(r["events"]):
        pb, qb, pa, qa = (int(v) for v in r["best"][t])
        if kind == "TRADE" and prev is not None:
            s_px, s_sz = (prev[2], prev[3]) if side == 1 else (prev[0], prev[1])
            if s_sz > 1:
                msgs.append(bf.Msg(bf.TRADE, bf.ASK if side == 1 else bf.BID, INST, s_px, min(size, s_sz - 1)))
                prev = (prev[0], prev[1] - (min(size, s_sz - 1) if side == 0 else 0),
                        prev[2], prev[3] - (min(size, s_sz - 1) if side == 1 else 0))
                continue
        if prev is None or (pb, qb) != (prev[0], prev[1]):
            msgs.append(bf.Msg(bf.ADD, bf.BID, INST, pb, qb))
        if prev is None or (pa, qa) != (prev[2], prev[3]):
            msgs.append(bf.Msg(bf.ADD, bf.ASK, INST, pa, qa))
        prev = (pb, qb, pa, qa)
    return msgs


def twin(msgs: list[bf.Msg]) -> tuple[list[list[int]], list[int]]:
    """The features and class the fabric should produce at each message's decision point."""
    book = [0, 0, 0, 0]                # bid px, bid sz, ask px, ask sz (58A semantics)
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
        elif m.type == bf.CANCEL:                      # 58A: the side becomes empty
            if m.side == bf.BID:
                book[0], book[1] = 0, 0
            else:
                book[2], book[3] = 0, 0
        elif m.type == bf.TRADE:
            i = 1 if m.side == bf.BID else 3
            if m.price == book[i - 1] and book[i] != 0:   # 58A: an emptied side gets price 0 too
                book[i] = max(0, book[i] - m.size)
                if book[i] == 0:
                    book[i - 1] = 0
    import numpy as np
    X = np.array(feats, dtype=np.int64)
    return feats, ARM_MODEL[1](model(), X).tolist()


async def watch(dut, out: list):
    g = dut.g_ml
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(g.feat_v.value):
            v = int(g.feat.value)
            out.append(("f", [(v >> lo) & ((1 << w) - 1) for lo, w in zip(FLO, L.FEATURE_BITS)]))
        if int(g.cls_v.value):
            out.append(("c", int(g.cls.value)))


def stress_msgs(n: int, seed: int = 87) -> list[bf.Msg]:
    """Random messages that reach the feature unit's edge cases: sizes above 255, spreads above 15, crossed and
    empty sides (a TRADE that takes a side's whole size), large order-flow terms that clip at +/-127."""
    import random
    rng = random.Random(seed)
    msgs = []
    for _ in range(n):
        t = rng.choice([bf.ADD, bf.ADD, bf.TRADE, bf.CANCEL])
        side = rng.choice([bf.BID, bf.ASK])
        px = 10000 + rng.choice([-40, -20, -3, -1, 0, 1, 3, 20, 40])
        sz = rng.choice([1, 5, 200, 300, 1000, 70000])
        msgs.append(bf.Msg(t, side, INST, px, sz))
    return msgs


@cocotb.test()
async def ml_features_match_on_edge_cases(dut):
    b = Bench(dut)
    await b.start()
    await b.config(Config(spec_en=True, bucket=100, max_pos=100000), None)
    await b.wr(0x02A, 1 | INST << 16)
    msgs = stress_msgs(300)
    seen: list = []
    cocotb.start_soon(watch(dut, seen))
    seq = 1
    for i in range(0, len(msgs), 8):
        part = msgs[i:i + 8]
        b.send(bf.with_fcs(bf.feed_frame(seq, part)), gap=200)
        seq += len(part)
    await b.drain(1500)
    exp_f, exp_c = twin(msgs)
    got_f = [x for k, x in seen if k == "f"]
    got_c = [x for k, x in seen if k == "c"]
    assert len(got_f) == len(msgs) == len(got_c), (len(got_f), len(msgs), len(got_c))
    bad = [i for i in range(len(msgs)) if got_f[i] != exp_f[i]]
    assert not bad, "; ".join(f"{i}: got {got_f[i]} want {exp_f[i]} prev {msgs[i-1]}" for i in bad[:3])
    assert got_c == exp_c
    import numpy as np
    F = np.array(exp_f)
    reach = {"size_saturated": int((F[:, 0] == 255).sum() + (F[:, 1] == 255).sum()), "spread_15": int((F[:, 2] == 15).sum()),
             "ofi_clipped": int(((F[:, 5] == 1) | (F[:, 5] == 255)).sum()), "empty_side": int(((F[:, 0] == 0) | (F[:, 1] == 0)).sum())}
    dut._log.info(f"edge cases reached: {reach}")
    assert all(v > 0 for v in reach.values()), reach
    out = os.environ.get("B87_TWIN_OUT")
    if out:
        p = out.replace(".json", "_edge_cases.json")
        with open(p, "w") as f:
            json.dump({"messages": len(msgs), "features_match": True, "classes_match": True, "edge_cases_reached": reach}, f,
                      indent=1)


@cocotb.test()
async def ml_features_and_class_match_the_twin(dut):
    b = Bench(dut)
    await b.start()
    await b.config(Config(spec_en=True, bucket=100, max_pos=100000), None)
    await b.wr(0x02A, 1 | INST << 16)
    msgs = stream_msgs(400)
    seen: list = []
    cocotb.start_soon(watch(dut, seen))
    seq = 1
    for i in range(0, len(msgs), 8):
        part = msgs[i:i + 8]
        b.send(bf.with_fcs(bf.feed_frame(seq, part)), gap=200)
        seq += len(part)
    await b.drain(1500)
    exp_f, exp_c = twin(msgs)
    got_f = [x for k, x in seen if k == "f"]
    got_c = [x for k, x in seen if k == "c"]
    assert len(got_f) == len(msgs) == len(got_c), (len(got_f), len(msgs), len(got_c))
    bad = [i for i in range(len(msgs)) if got_f[i] != exp_f[i]]
    assert not bad, (bad[:3], [(got_f[i], exp_f[i]) for i in bad[:3]])
    assert got_c == exp_c, [i for i in range(len(msgs)) if got_c[i] != exp_c[i]][:5]
    dut._log.info(f"{len(msgs)} messages: features and classes match; classes {[exp_c.count(k) for k in range(3)]}")
    out = os.environ.get("B87_TWIN_OUT")
    if out:
        with open(out, "w") as f:
            json.dump({"ml_arm": ARM_MODEL[0], "messages": len(msgs), "features_match": True, "classes_match": True,
                       "class_counts": [exp_c.count(k) for k in range(3)]}, f, indent=1)


@cocotb.test()
async def stage_latency_with_and_without_model(dut):
    """The 58A stage_latency trigger (an ADD on the ask below 100.00 fires a buy), with the model off and on. The
    book is primed with a heavy bid (an "up" book for the imbalance features) so the model is likely to agree; the
    record says whether the order was kept."""
    b = Bench(dut)
    await b.start()
    rules = [{"match": {"types": ["ADD"], "side": "ask", "instrument": INST, "price": {"op": "<", "value": "100.00"}},
              "action": {"order": {"side": "buy", "qty": 1, "price": {"mode": "message"}}}}]
    table = rl.table_words(rl.validate_table(rules))
    gated: list[int] = []        # (rule fire, decision) pairs counted in this monitor's own clock count
    rfire: list[int] = []

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
    cocotb.start_soon(mon())
    res = {"ml_arm": ARM_MODEL[0], "clock_ns": 8, "clock_mhz": 125, "instrument": INST,
           "points": {"price_complete_in": "the clock the last price byte enters mac_rx (core side)",
                      "decision": "fire_v into the interlocks (after ml_gate when the model is on)",
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
            n0 = len(b.sfd_cycles) - 1
            fr = bf.with_fcs(bf.feed_frame(seq, [bf.Msg(bf.ADD, bf.ASK, INST, 9950, 1)]))
            seq += 1
            v0 = await b.rd(0x02C)
            b.send(fr, gap=400)
            await b.drain(600)
            ev = {k: b.events[k][base[k]] for k in b.events if len(b.events[k]) > base[k]}
            bytes_c = b.byte_cycles[n0 + 1]
            px_in = bytes_c[8 + 57]
            kept = "first" in ev
            r = {"model_enabled": bool(en), "class": await b.rd(0x02B), "vetoed": (await b.rd(0x02C)) - v0,
                 "order_kept": kept,
                 "stages_cycles": {"mac_rx + feed_rx (price byte in -> msg_px_v)": ev["px"] - px_in,
                                   "rules (msg_px_v -> rule fire)": ev["fire"] - ev["px"],
                                   "model gate (rule fire -> decision)": gated[g0] - rfire[r0]},
                 "tick_to_decision": ev["fire"] - px_in + gated[g0] - rfire[r0]}
            if kept:
                r["stages_cycles"]["interlocks (decision -> grant)"] = ev["grant"] - ev["fire"] - (gated[g0] - rfire[r0])
                r["stages_cycles"]["order_ctl (grant -> tx_start)"] = ev["start"] - ev["grant"]
                r["stages_cycles"]["mac_tx (tx_start -> first preamble byte)"] = ev["first"] - ev["start"]
                r["decision_to_first_byte"] = ev["first"] - px_in
            res["modes"][f"{'speculative' if spec else 'safe'}_model_{'on' if en else 'off'}"] = r
            if not en:
                assert r["stages_cycles"]["model gate (rule fire -> decision)"] == 0, r
    dut._log.info(json.dumps(res, indent=1))
    import re
    from designs.b87_ml_trading.model.gen_rtl import OUT as GEN
    arm_file = {1: "gbt_comb", 2: "lutnet", 3: "mlp_hand"}[ML_ARM]
    lat = int(re.search(r"LATENCY = (\d+);", (GEN / f"{arm_file}.sv").read_text()).group(1))
    res["arm_latency_clocks"] = lat
    for k, r in res["modes"].items():
        if r["model_enabled"]:
            assert r["stages_cycles"]["model gate (rule fire -> decision)"] == lat, (k, r, lat)
    out = os.environ.get("B87_INTEG_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(res, f, indent=1)


@cocotb.test()
async def veto_when_the_model_disagrees(dut):
    """A buy rule and a sell rule (one at a time) on the same kind of book: with the model on, each decision arrives
    and its order is sent only if the class agrees with its side, otherwise dropped and counted (0x02C); at least one
    of the two disagrees whatever the class. With the model off the same frame always sends."""
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
