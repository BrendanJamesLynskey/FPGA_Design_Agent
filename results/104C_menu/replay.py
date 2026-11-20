#!/usr/bin/env python3
"""Development replay for brief 104C (no model call): the model's own options of the 30 recorded runs of briefs 104A and 104B (15 each), put through a menu rule and scored with the
unchanged flow/options/backtest.py. These runs are DEVELOPMENT data: the rule was argued before this replay and was not changed after it.

    python3 results/104C_menu/replay.py <label> <out.json> <104A runs dir> <104B runs dir> [--root <worktree>]

``--root`` runs the code of another worktree (the 104B code, version 2, as the 'before' column). Per run it records the menu offered under the cap of four, whether the pair and
the triple were offered or available (cap lifted), and how many of 24 random orders of the model's options give a different menu (content only)."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

args = sys.argv[1:]
ROOT = Path(__file__).resolve().parents[2]
if "--root" in args:
    i = args.index("--root")
    ROOT = Path(args[i + 1]).resolve()
    del args[i:i + 2]
sys.path.insert(0, str(ROOT))
from agent.core import managed  # noqa: E402
from flow.options import analysis as A  # noqa: E402
from flow.options import backtest as B  # noqa: E402
from flow.options import combine as K  # noqa: E402

BT = ROOT / "results" / "104_strategy_options" / "backtest"
NAMES = ("agent_cdc", "hand_ref", "agent_both", "all3")
RUNS = [(s, c, a, k) for s, cases in (("P1", {"b96_10g_pre97": "AB", "c16_montgomery_200mhz": "A"}), ("P2", {"b96_10g_pre97": "AB"})) for c, arms in cases.items() for a in arms for k in (1, 2, 3)]


def menu_content(rec: dict) -> list:
    return sorted((o["origin"], tuple(o["touches_stages"]), tuple(o["scope"]["components"]), o["gain"]["low"], o["gain"]["high"]) for o in rec["options"] if o.get("origin", "model") != "model")


def main() -> int:
    label, out, dir_a, dir_b = args[0], Path(args[1]), Path(args[2]), Path(args[3])
    cache: dict = {}
    res = {"schema": "fda-menu-replay/1", "label": label, "combiner_version": K.COMBINER_VERSION, "note": "development data: model options of the recorded 104A and 104B runs; no model call", "runs": []}
    rng = random.Random(104)
    for src, d in (("104A", dir_a), ("104B", dir_b)):
        for s, case, arm, k in RUNS:
            name = f"{s}__{case}__{arm}__{k}"
            fx = BT / case
            if case not in cache:
                cache[case] = (A.analyse(fx, build_dir=fx / "evidence"), managed.load(fx), B.load_truth(BT / "truth" / f"{case}.json"))
            an, proj, truth = cache[case]
            rec = json.loads((d / name / "strategy.json").read_text())["current"]
            blind = bool(rec.get("blind"))
            model = [json.loads(json.dumps(o)) for o in rec["options"] if o.get("origin", "model") == "model"]

            def build(opts, **kw):
                r = {"options": json.loads(json.dumps(opts))}
                K.apply(r, an, proj, goal=rec["goal"], blind=blind, **kw)
                return r
            offered, avail = build(model), build(model, cap=1000)
            so, sa = B.score({"status": "options", "options": offered["options"]}, truth), B.score({"status": "options", "options": avail["options"]}, truth)
            base = menu_content(offered)
            diff = 0
            for _ in range(24):
                p = list(model)
                rng.shuffle(p)
                diff += menu_content(build(p)) != base
            item = {"source": src, "run": name, "case": case, "arm": arm, "n_model": len(model), "n_parts": sum(1 for o in offered["options"] if o.get("origin") == "splitter"),
                    "offered_combined": [{"stages": o["touches_stages"], "gain": [o["gain"]["low"], o["gain"]["high"]]} for o in offered["options"] if o.get("origin") == "combiner"],
                    "orders_with_a_different_menu_of_24": diff}
            if "variants" in so:
                item["offered"] = {n: so["variants"][n]["found"] for n in NAMES}
                item["in_range"] = {n: bool(so["variants"][n].get("in_range")) for n in NAMES}
                item["over"] = {n: so["variants"][n].get("over") for n in NAMES if so["variants"][n]["found"]}
                item["available"] = {n: sa["variants"][n]["found"] for n in NAMES}
            res["runs"].append(item)
    b96 = [r for r in res["runs"] if r["case"] == "b96_10g_pre97"]
    res["totals_b96"] = {src: {n: {"offered": sum(r["offered"][n] for r in b96 if r["source"] == src), "available": sum(r["available"][n] for r in b96 if r["source"] == src),
                                   "in_range_when_offered": sum(r["in_range"][n] for r in b96 if r["source"] == src and r["offered"][n])} for n in NAMES} | {"runs": sum(1 for r in b96 if r["source"] == src)} for src in ("104A", "104B")}
    res["runs_with_order_dependent_menu"] = sum(1 for r in res["runs"] if r["orders_with_a_different_menu_of_24"])
    res["runs_total"] = len(res["runs"])
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("label", "combiner_version", "totals_b96", "runs_with_order_dependent_menu", "runs_total")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
