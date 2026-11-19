"""Back-test scoring for the options generator (brief 104). Code scores; no model ever does.

A back-test runs ``agent improve`` on a design whose answer we already know and compares the options offered with the recorded truth
(``results/104_strategy_options/backtest/truth/<case>.json``). The generator never sees the truth: the analysis is built from the fixture
directory only, which holds no later result.

Scores, per run:

* **found(variant)**: some valid option touches exactly the stages of that measured variant (``touches_stages`` as a set). ``partial``: the
  best Jaccard overlap, when no option matches exactly.
* **in_range**: the matching option's gain range contains the measured gain (``low <= measured <= high``); ``over`` is how far its high end
  is above the measurement.
* **other options**: every valid option that matches no variant is listed with its stages, so a human can judge it; code only says whether
  it passed the checks (it did, or it would not be here).
* closure cases: **found(change)**: some valid option's scope is exactly the change's components, and its gain range contains the measured
  gain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_truth(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def score_latency(rec: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    opts = rec.get("options") or []
    out: dict[str, Any] = {"status": rec.get("status"), "n_options": len(opts), "variants": {}, "matched_options": [], "other_options": []}
    used: set[str] = set()
    for name, v in truth["variants"].items():
        want = set(v["stages"])
        exact = [o for o in opts if set(o["touches_stages"]) == want and o["gain"]["metric"] == truth["metric"]]
        if exact:
            o = exact[0]
            g = o["gain"]
            used.add(o["id"])
            out["variants"][name] = {"found": True, "option": o["id"], "scope": o["scope"]["components"], "gain": [g["low"], g["high"]], "basis": g["basis"],
                                     "measured": v["measured_gain"], "in_range": g["low"] <= v["measured_gain"] <= g["high"], "over": round(g["high"] - v["measured_gain"], 3)}
        else:
            best = max(((_jaccard(set(o["touches_stages"]), want), o["id"]) for o in opts), default=(0.0, None))
            out["variants"][name] = {"found": False, "best_overlap": round(best[0], 2), "best_option": best[1], "measured": v["measured_gain"]}
    out["other_options"] = [{"id": o["id"], "title": o["title"], "stages": o["touches_stages"], "scope_kind": o["scope"]["kind"], "gain": [o["gain"]["low"], o["gain"]["high"]],
                             "basis": o["gain"]["basis"]} for o in opts if o["id"] not in used]
    named = truth.get("named_by_the_brief") or list(truth["variants"])
    out["found_named"] = sum(1 for n in named if out["variants"][n]["found"])
    out["found_all"] = sum(1 for n in truth["variants"] if out["variants"][n]["found"])
    out["in_range"] = sum(1 for n in truth["variants"] if out["variants"][n].get("in_range"))
    out["n_variants"] = len(truth["variants"])
    out["n_named"] = len(named)
    return out


def score_change(rec: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    opts = rec.get("options") or []
    out: dict[str, Any] = {"status": rec.get("status"), "n_options": len(opts), "changes": {}}
    for name, ch in truth["changes"].items():
        scoped = [o for o in opts if set(o["scope"]["components"]) == set(ch["scope"]) and o["gain"]["metric"] == truth["metric"]]
        if scoped:
            o = scoped[0]
            g = o["gain"]
            out["changes"][name] = {"found": True, "option": o["id"], "title": o["title"], "gain": [g["low"], g["high"]], "basis": g["basis"], "measured": ch["measured_gain"],
                                    "in_range": g["low"] <= ch["measured_gain"] <= g["high"], "over": round(g["high"] - ch["measured_gain"], 3),
                                    "names_carry_save": any(k in (o["approach"] + " " + " ".join(o.get("techniques") or [])).lower() for k in ("carry-save", "carry save", "csa", "3:2", "compress"))}
        else:
            out["changes"][name] = {"found": False, "measured": ch["measured_gain"]}
    out["other_options"] = [{"id": o["id"], "title": o["title"], "scope": o["scope"]["components"], "scope_kind": o["scope"]["kind"], "gain": [o["gain"]["low"], o["gain"]["high"]],
                             "basis": o["gain"]["basis"]} for o in opts]
    out["found_all"] = sum(1 for c in out["changes"].values() if c["found"])
    out["in_range"] = sum(1 for c in out["changes"].values() if c.get("in_range"))
    return out


def score(rec: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    return score_latency(rec, truth) if "variants" in truth else score_change(rec, truth)
