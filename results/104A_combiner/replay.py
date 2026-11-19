#!/usr/bin/env python3
"""Supplementary replay for brief 104A (see preregistration.md): apply the combiner to the single options that the twelve recorded brief-104 runs already offered, then score them
with the unchanged flow/options/backtest.py. No model is called. Needs the private knowledge checkout with results_private/b104_options/runs/ (FDA_KB_RUNS or the default sibling
checkout); the public output (replay_results.json, REPLAY.md) holds structured fields only (ids, stages, ranges, scores), never an option's free text.

    python3 results/104A_combiner/replay.py <path to results_private/b104_options/runs>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.core import managed  # noqa: E402
from flow.options import analysis as A  # noqa: E402
from flow.options import backtest as B  # noqa: E402
from flow.options import combine as K  # noqa: E402

HERE = Path(__file__).resolve().parent
BT = ROOT / "results" / "104_strategy_options" / "backtest"
CASE_ARMS = {"b96_10g_pre97": ["A", "B", "A2", "B2"], "c16_montgomery_200mhz": ["A"]}


def main(runs: Path) -> int:
    res = {"schema": "fda-combiner-replay/1", "note": "the combiner applied to the singles of the recorded brief-104 runs; no model call; not a new measurement of the generator", "runs": [], "summary": {}}
    cache: dict[str, tuple] = {}
    for case, arms in CASE_ARMS.items():
        fx = BT / case
        if case not in cache:
            cache[case] = (A.analyse(fx, build_dir=fx / "evidence"), managed.load(fx))
        an, proj = cache[case]
        truth = B.load_truth(BT / "truth" / f"{case}.json")
        for arm in arms:
            for k in (1, 2, 3):
                name = f"{case}__{arm}__{k}"
                rec = json.loads((runs / name / "strategy.json").read_text())["current"]
                blind = bool(rec.get("blind"))
                singles = [dict(o, origin="model") for o in rec["options"]]
                before = B.score({"status": rec["status"], "options": singles}, truth)
                r2 = {"options": json.loads(json.dumps(singles))}
                K.apply(r2, an, proj, goal=rec["goal"], blind=blind)
                after = B.score({"status": rec["status"], "options": r2["options"]}, truth)
                origin = {o["id"]: o["origin"] for o in r2["options"]}
                res["runs"].append({"run": name, "case": case, "arm": arm, "k": k, "singles": [{"id": o["id"], "stages": o["touches_stages"], "scope": o["scope"]["components"], "gain": [o["gain"]["low"], o["gain"]["high"]],
                                                                                              "basis": o["gain"]["basis"]} for o in singles],
                                    "combined": [{"id": o["id"], "from": o["combined_from"], "stages": o["touches_stages"], "gain": [o["gain"]["low"], o["gain"]["high"]], "basis": o["gain"]["basis"],
                                                  "needs_owner_approval": o["risk"]["needs_owner_approval"], "contract_change": o["risk"]["contract_change"]} for o in r2["options"] if o["origin"] == "combiner"],
                                    "not_composable": r2["combiner"]["not_composable"],
                                    "before": {kk: before.get(kk) for kk in ("found_named", "found_all", "in_range")}, "after": {kk: after.get(kk) for kk in ("found_named", "found_all", "in_range")},
                                    "variants_after": {n: ({**{kk: v[kk] for kk in ("found", "option", "gain", "basis", "in_range", "over") if kk in v}, "origin": origin.get(v.get("option"))} if v.get("found") else {"found": False,
                                                                                                                                                                                  "best_overlap": v.get("best_overlap")})
                                                       for n, v in after.get("variants", {}).items()} if "variants" in after else {n: {kk: c.get(kk) for kk in ("found", "option", "gain", "basis", "in_range", "over")} for n, c in after["changes"].items()}})
    for case, arms in CASE_ARMS.items():
        for arm in arms:
            rs = [r for r in res["runs"] if r["case"] == case and r["arm"] == arm]
            s = {"found_named_before": [r["before"]["found_named"] for r in rs] if case == "b96_10g_pre97" else None, "found_named_after": [r["after"]["found_named"] for r in rs] if case == "b96_10g_pre97" else None,
                 "found_all_before": [r["before"]["found_all"] for r in rs], "found_all_after": [r["after"]["found_all"] for r in rs], "in_range_after": [r["after"]["in_range"] for r in rs]}
            if case == "b96_10g_pre97":
                s["found_by_variant_after"] = {n: sum(1 for r in rs if r["variants_after"][n]["found"]) for n in ("agent_cdc", "hand_ref", "agent_both", "all3")}
                s["in_range_by_variant_after"] = {n: sum(1 for r in rs if r["variants_after"][n].get("in_range")) for n in ("agent_cdc", "hand_ref", "agent_both", "all3")}
                s["found_by_origin_after"] = {n: sorted({r["variants_after"][n].get("origin") for r in rs if r["variants_after"][n]["found"]}) for n in ("agent_cdc", "hand_ref", "agent_both", "all3")}
            res["summary"][f"{case}/{arm}"] = s
    (HERE / "replay_results.json").write_text(json.dumps(res, indent=1) + "\n")
    md = ["# Replay of the combiner on the recorded brief-104 options (brief 104A, supplementary)", "",
          "No model call: the combiner (code) applied to the single options each recorded run offered; the unchanged scoring code. Counts over three runs.", "",
          "| case / arm | named found (of 3) before | after | variants found (of 4) after | agent_cdc / hand_ref / agent_both / all3 found (runs) | in range (runs) | origin of the match |", "|---|---|---|---|---|---|---|"]
    for k, s in res["summary"].items():
        fb = s.get("found_by_variant_after")
        md.append(f"| {k} | {s['found_named_before']} | {s['found_named_after']} | {s['found_all_after']} | " + (" / ".join(str(fb[n]) for n in fb) if fb else "-") + f" | " +
                  (" / ".join(str(s['in_range_by_variant_after'][n]) for n in fb) if fb else str(s["in_range_after"])) + " | " + (json.dumps(s["found_by_origin_after"]) if fb else "-") + " |")
    (HERE / "REPLAY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
