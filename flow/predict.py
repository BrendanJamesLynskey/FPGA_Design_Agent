#!/usr/bin/env python3
"""Brief 177: the `predict` stage. After each flow stage, record how likely the routed result is to meet timing.

SHADOW MODE ONLY. A prediction is logged to ``<build_dir>/predictions.jsonl`` and later scored against the real routed
outcome; it never changes a gate and never skips a build. Promotion to a gate is a later decision, to be taken once the
false-go rate (predicted pass, routed fail) has been measured on enough full designs (see results/177_qor/README.md).

    python3 -m flow.predict show  <build_dir>      # print the predictions recorded for a build
    python3 -m flow.predict score <build_dir>      # join them with the routed outcome in gates.json

Model ``rule_v0`` is an expert prior, **not fitted**: the full-design data (50 rows, one routed failure) cannot train
anything. Its confidence is always "low". Fitted models exist for out-of-context arithmetic blocks only
(tools/qor/evaluate.py) and need the target clock, which gates.json does not carry; they are not wired in here.
Low-probability predictions carry the features and the repair families the KB documents, as context for the agent's
LLM, which chooses the repair (the predictor does not).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

MODEL = "rule_v0"
BASIS = "expert prior, not fitted (results/177_qor/README.md: 49 of 50 full-design rows pass)"
LOW = 0.5          # below this a repair at the current stage is worth trying before the next stage
REPAIR_FAMILIES = ["retiming", "pipelining the worst path", "DSP packing/registering", "floorplan or placement hints (Pblock)",
                   "reduce fanout (replicate registers)", "relax or correct the constraint (only if it is wrong)"]


def _features(stage: str, r: dict[str, Any]) -> dict[str, Any]:
    st = (r.get("stages") or {}).get(stage) or {}
    t = st.get("timing") or {}
    u = st.get("utilization") or {}
    f: dict[str, Any] = {"wns_ns": t.get("wns_ns"), "whs_ns": t.get("whs_ns"), "tns_ns": t.get("tns_ns"),
                         "failing_endpoints": t.get("tns_failing_endpoints"), "endpoints": t.get("tns_total_endpoints")}
    if u.get("lut") is not None and u.get("lut_available"):
        f["lut_frac"] = round(u["lut"] / u["lut_available"], 4)
    q = (st.get("qor_assessment") or {}).get("score")
    if q is not None:
        f["amd_qor_score"] = q
    return {k: v for k, v in f.items() if v is not None}


def rule_v0(stage: str, f: dict[str, Any]) -> tuple[float | None, str]:
    wns = f.get("wns_ns")
    if wns is None:
        return None, "none"
    if stage == "post_synth":
        return (0.9 if wns >= 0.5 else 0.7 if wns >= 0 else 0.3), "low"
    if stage == "post_place":
        return (0.97 if wns >= 0 else 0.2), "low"
    if stage == "rtl":
        return None, "none"
    return None, "none"


def predict_stages(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for stage in ("post_synth", "post_place"):
        st = (r.get("stages") or {}).get(stage) or {}
        if not st.get("ran"):
            continue
        f = _features(stage, r)
        p, conf = rule_v0(stage, f)
        rec: dict[str, Any] = {"stage": stage, "model": MODEL, "basis": BASIS, "p_pass": p, "confidence": conf, "features": f,
                               "mode": "shadow"}
        if p is not None and p < LOW:
            rec["repair_context"] = {"note": "low predicted chance: consider a repair at this stage before route", "families": REPAIR_FAMILIES}
        out.append(rec)
    return out


def shadow(build_dir: Path, r: dict[str, Any]) -> list[dict[str, Any]]:
    """Write the predictions for the stages that ran (replacing the file: one build, one set). Never raises into the caller."""
    if os.environ.get("FDA_PREDICT_SHADOW") == "0":
        return []
    try:
        recs = predict_stages(r)
        Path(build_dir, "predictions.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs))
        return recs
    except Exception:       # shadow mode must never break a gate run
        return []


def score(build_dir: Path) -> dict[str, Any]:
    g = json.loads(Path(build_dir, "gates.json").read_text()) if Path(build_dir, "gates.json").exists() else None
    recs = [json.loads(x) for x in Path(build_dir, "predictions.jsonl").read_text().splitlines()] if Path(build_dir, "predictions.jsonl").exists() else []
    t = (g or {}).get("timing") or {}
    routed = None if t.get("wns_ns") is None else int(t["wns_ns"] >= 0 and (t.get("whs_ns") is None or t["whs_ns"] >= 0))
    rows = [{"stage": x["stage"], "p_pass": x["p_pass"], "confidence": x["confidence"], "routed_met": routed,
             "outcome": None if x["p_pass"] is None or routed is None else
             ("go_pass" if x["p_pass"] >= LOW and routed else "false_go" if x["p_pass"] >= LOW else
              "saved_fail" if not routed else "held_pass")} for x in recs]
    return {"build_dir": str(build_dir), "routed_met": routed, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("cmd", choices=["show", "score"]); ap.add_argument("build_dir", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "show":
        p = a.build_dir / "predictions.jsonl"
        print(p.read_text() if p.exists() else "no predictions recorded")
        return 0
    print(json.dumps(score(a.build_dir), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
