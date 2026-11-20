#!/usr/bin/env python3
"""Offline replay for brief 104B (no model call): the splitter plus the combiner applied to the *model's own options* of the fifteen recorded 104A back-test runs, scored with the
unchanged flow/options/backtest.py. 'before' is the 104A combiner alone on the same options (``splitter=False``); 'after' adds the splitter. Needs the private knowledge checkout:

    python3 results/104B_split/replay.py <checkout>/results_private/b104a_combiner/runs 

Public output (replay_results.json, REPLAY.md) holds structured fields only (ids, stages, ranges, scores, reasons), never an option's free text."""
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
RUNS = [(s, c, a, k) for s, cases in (("P1", {"b96_10g_pre97": "AB", "c16_montgomery_200mhz": "A"}), ("P2", {"b96_10g_pre97": "AB"})) for c, arms in cases.items() for a in arms for k in (1, 2, 3)]
NAMES = ("agent_cdc", "hand_ref", "agent_both", "all3")


def scored(rec_opts, case, truth):
    return B.score({"status": "options", "options": rec_opts}, truth)


ALL = 1000      # "every valid combination": the cap lifted


def main(runs: Path) -> int:
    cache: dict[str, tuple] = {}
    res = {"schema": "fda-split-replay/1", "combiner_cap": K.MAX_COMBINED, "available_cap": ALL, "note": "splitter and combiner applied to the model's own options of the recorded 104A runs; no model call", "runs": [], "summary": {}}
    for s, case, arm, k in RUNS:
        name = f"{s}__{case}__{arm}__{k}"
        fx = BT / case
        if case not in cache:
            cache[case] = (A.analyse(fx, build_dir=fx / "evidence"), managed.load(fx), B.load_truth(BT / "truth" / f"{case}.json"))
        an, proj, truth = cache[case]
        rec = json.loads((runs / name / "strategy.json").read_text())["current"]
        blind = bool(rec.get("blind"))
        model = [dict(o) for o in rec["options"] if o.get("origin", "model") == "model"]
        out = {}
        for label, kw in (("before", {"splitter": False}), ("after", {}), ("avail_before", {"splitter": False, "cap": ALL}), ("avail_after", {"cap": ALL})):
            r = {"options": json.loads(json.dumps(model))}
            K.apply(r, an, proj, goal=rec["goal"], blind=blind, **kw)
            sc = scored(r["options"], case, truth)
            origin = {o["id"]: o.get("origin", "model") for o in r["options"]}
            out[label] = (r, sc, origin)
        r, sc, origin = out["after"]
        item = {"run": name, "set": s, "case": case, "arm": arm, "k": k,
                "model_options": [{"id": o["id"], "stages": o["touches_stages"], "gain": [o["gain"]["low"], o["gain"]["high"]]} for o in model],
                "splitter": r.get("splitter"),
                "parts": [{"id": o["id"], "from": o["split_from"], "stages": o["touches_stages"], "gain": [o["gain"]["low"], o["gain"]["high"]], "scope": o["scope"]["components"], "needs_owner_approval": o["risk"]["needs_owner_approval"]}
                          for o in r["options"] if o.get("origin") == "splitter"],
                "combined": [{"id": o["id"], "from": o["combined_from"], "stages": o["touches_stages"], "gain": [o["gain"]["low"], o["gain"]["high"]], "basis": o["gain"]["basis"]} for o in r["options"] if o.get("origin") == "combiner"],
                "before": {kk: out["before"][1].get(kk) for kk in ("found_named", "found_all", "in_range")}, "after": {kk: sc.get(kk) for kk in ("found_named", "found_all", "in_range")}}
        if "variants" in sc:
            item["variants_before"] = {n: out["before"][1]["variants"][n]["found"] for n in NAMES}
            item["available_before"] = {n: out["avail_before"][1]["variants"][n]["found"] for n in NAMES}
            item["available_after"] = {n: out["avail_after"][1]["variants"][n]["found"] for n in NAMES}
            item["variants_after"] = {n: ({"found": True, "option": v["option"], "origin": origin.get(v["option"]), "gain": v["gain"], "in_range": v["in_range"], "over": v["over"]} if (v := sc["variants"][n])["found"] else {"found": False, "best_overlap": v.get("best_overlap")}) for n in NAMES}
        else:
            item["changes_after"] = {n: {kk: c.get(kk) for kk in ("found", "option", "gain", "in_range", "over")} for n, c in sc["changes"].items()}
            item["changes_before"] = {n: c["found"] for n, c in out["before"][1]["changes"].items()}
        res["runs"].append(item)
    keys = []
    for r in res["runs"]:
        if (r["set"], r["case"], r["arm"]) not in keys:
            keys.append((r["set"], r["case"], r["arm"]))
    md = ["# Replay of the splitter and combiner on the 104A runs' own options (brief 104B)", "",
          f"No model call. The model's options of each recorded 104A run (the combiner's and splitter's options removed), then the 104A combiner alone (before) and the splitter plus the combiner (after, combiner cap {K.MAX_COMBINED}); the unchanged scoring. Runs found / 3 per arm.", "",
          "| set / case / arm | agent_cdc | hand_ref | agent_both | all3 | in range (after) | parts per run | combined per run |", "|---|---|---|---|---|---|---|---|"]
    tot = {n: [0, 0, 0] for n in NAMES}     # before, after, in_range (after) over the 12 b96 runs
    av = {n: [0, 0] for n in NAMES}         # available (cap lifted): before, after
    for key in keys:
        rs = [r for r in res["runs"] if (r["set"], r["case"], r["arm"]) == key]
        if key[1] == "b96_10g_pre97":
            cells = []
            for n in NAMES:
                b = sum(1 for r in rs if r["variants_before"][n])
                a = sum(1 for r in rs if r["variants_after"][n]["found"])
                ir = sum(1 for r in rs if r["variants_after"][n].get("in_range"))
                av[n][0] += sum(1 for r in rs if r["available_before"][n])
                av[n][1] += sum(1 for r in rs if r["available_after"][n])
                tot[n][0] += b
                tot[n][1] += a
                tot[n][2] += ir
                cells.append(f"{b} -> {a}")
            res["summary"]["/".join(key)] = {n: {"before": sum(1 for r in rs if r["variants_before"][n]), "after": sum(1 for r in rs if r["variants_after"][n]["found"]),
                                                  "in_range_after": sum(1 for r in rs if r["variants_after"][n].get("in_range")), "origins_after": sorted({r["variants_after"][n]["origin"] for r in rs if r["variants_after"][n]["found"]})} for n in NAMES}
            md.append(f"| {'/'.join(key)} | " + " | ".join(cells) + f" | {sum(r['after']['in_range'] for r in rs)} variant-hits | {[len(r['parts']) for r in rs]} | {[len(r['combined']) for r in rs]} |")
        else:
            res["summary"]["/".join(key)] = {"changes_found_before": [sum(r["changes_before"].values()) for r in rs], "changes_found_after": [sum(1 for c in r["changes_after"].values() if c["found"]) for r in rs]}
            md.append(f"| {'/'.join(key)} (closure: changes found before / after) | {res['summary']['/'.join(key)]['changes_found_before']} | {res['summary']['/'.join(key)]['changes_found_after']} | | | | {[len(r['parts']) for r in rs]} | {[len(r['combined']) for r in rs]} |")
    res["totals_b96_12_runs"] = {n: {"before": tot[n][0], "after": tot[n][1], "in_range_after": tot[n][2]} for n in NAMES}
    res["available_totals_b96_12_runs"] = {n: {"before": av[n][0], "after": av[n][1]} for n in NAMES}
    md += ["", "Available (every valid combination listed, the cap of 4 lifted; the same scoring on those options; before -> after): " + "; ".join(f"{n} {av[n][0]} -> {av[n][1]}" for n in NAMES),
           "", "Totals over the 12 b96 runs, as offered under the cap of 4 (found before -> after; in range after): " + "; ".join(f"{n} {tot[n][0]} -> {tot[n][1]} ({tot[n][2]} in range)" for n in NAMES)]
    (HERE / "replay_results.json").write_text(json.dumps(res, indent=1) + "\n")
    (HERE / "REPLAY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
