"""Brief 113: compare one run of results/b113/ml_sim.sh (the MSG, FIRE and register lines of tb_ml_core.sv) with the twin's expectation (rm_gp_ml/model/stream.py -> expect.json).

usage: python3 results/b113/ml_check.py <log> <expect.json> <out.json> [--veto]
Checks, per frame the rule path accepts: the 38-bit feature vector, the class, the rule's hit, the decision, the veto, and the message fields the bench saw; then the order count
(FIRE lines and the transmit counter) and the stage's counters (MLV words) against the twin's counts. Exit status 1 if anything differs.
"""
import json
import re
import sys


def main() -> int:
    log, exp_p, out_p = sys.argv[1:4]
    veto_mode = "--veto" in sys.argv
    exp = json.load(open(exp_p))
    E, tc = exp["expect"], exp["summary"]["twin_counts"]
    msgs, fires, regs, mlv = [], 0, {}, {}
    for ln in open(log):
        t = ln.split()
        if not t:
            continue
        if t[0] == "MSG":
            d = {t[i]: t[i + 1] for i in range(2, len(t), 2)}
            msgs.append(d)
        elif t[0] == "FIRE":
            fires += 1
        elif t[0] == "REG":
            regs[t[1]] = int(t[2])
        elif t[0] == "MLV":
            mlv[int(t[1])] = int(t[2])
    res = {"messages_seen": len(msgs), "messages_expected": len(E), "mismatches": []}
    bad = []
    for i, (g, e) in enumerate(zip(msgs, E)):
        got = {"trk": int(g["trk"]), "feat": int(g["feat"], 16), "cls": int(g["cls"]), "hit": int(g["hit"]), "dec": int(g["dec"]), "veto": int(g["veto"]),
               "type": int(g["type"]), "side": int(g["side"]), "px": int(g["px"]), "sz": int(g["sz"])}
        want = {"trk": int(e["trk"]), "feat": e["feat"], "cls": e["cls"], "hit": int(e["hit"]), "dec": int(e["dec"]), "veto": int(e["veto"]),
                "type": e["type"], "side": e["side"], "px": e["px"], "sz": e["sz"]}
        # a message for another instrument is not classified by the stage (trk 0): the model's class and features are still shown by the fabric, the twin's too (state before the message)
        got["veto"] = got["veto"] & got["dec"]          # the fabric's veto wire is the class test alone; it matters only for a decision
        want["veto"] = want["veto"] & want["dec"]
        if not veto_mode:
            want["veto"] = 0
            got["veto"] = 0
        if got != want:
            bad.append({"i": i, "got": got, "want": want})
    res["mismatches"] = bad[:10]
    res["n_mismatch"] = len(bad)
    res["length_equal"] = len(msgs) == len(E)
    n_orders = sum(1 for e in E if e["order"])
    res["orders_expected"] = n_orders
    res["fire_lines"] = fires
    res["tx_n_order"] = regs.get("tx_n_order")
    cnt = {}
    if mlv:
        names = ["n_obs", "n_cls_down", "n_cls_flat", "n_cls_up", "n_dec", "n_veto", "n_would_veto", "n_late", "n_apply", "n_drop", "n_race"]
        cnt = {n: mlv.get(i) for i, n in enumerate(names)}
        want = {"n_obs": tc["obs"], "n_cls_down": tc["cls"][0], "n_cls_flat": tc["cls"][1], "n_cls_up": tc["cls"][2], "n_dec": tc["dec"],
                "n_veto": tc["veto"] if veto_mode else 0, "n_would_veto": 0 if veto_mode else tc["would"], "n_late": 0, "n_apply": tc["apply"], "n_drop": tc["drop"], "n_race": 0}
        res["ml_counters"] = cnt
        res["ml_counters_expected"] = want
        res["ml_counters_equal"] = cnt == want
    res["safety"] = {k: regs.get(k) for k in ("tx_poisoned", "tx_dropped", "tx_underrun", "tx_late", "tx_stale", "rx_err", "rx_ovf")}
    res["registers"] = regs
    ok = res["length_equal"] and not bad and fires == n_orders and regs.get("tx_n_order") == n_orders and (not mlv or res["ml_counters_equal"])
    res["pass"] = bool(ok)
    json.dump(res, open(out_p, "w"), indent=1)
    print(("PASS" if ok else "FAIL"), json.dumps({k: res[k] for k in ("messages_seen", "messages_expected", "n_mismatch", "orders_expected", "fire_lines", "tx_n_order")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
