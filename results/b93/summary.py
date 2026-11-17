#!/usr/bin/env python3
"""Collect the brief 93 records into results/b93/summary.json; `--check` fails if the committed file is out of date.

Latency of a block = clocks x max(closed period, 2.0 ns), the 87/89 convention (out of context there is no clock buffer,
so no clock is quoted faster than 2.0 ns). The integration clocks are simulation at the 8 ns core clock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
FLOOR = 2.0
PARTS = ("k26", "a7")
SUBJ = ["gbt_comb", "gbt_pe", "gbt_pe2", "lg_small_comb", "lgs_pe", "lgs_pe2", "ml_feat", "ml_feat_pre"]


def ooc(part: str, name: str) -> dict | None:
    f = R / "ooc" / part / f"{name}.json"
    if not f.exists():
        return None
    r = json.loads(f.read_text())
    b = r.get("at_closed_clock")
    if not b:
        return {"closed_ns": None}
    d = {"closed_ns": r["closed_at_ns"], "quoted_ns": max(r["closed_at_ns"], FLOOR), "lut": b["lut"], "ff": b["ff"],
         "bram_tiles": b["bram_tiles"], "dsp": b["dsp"], "wns_ns": b["wns_ns"], "whs_ns": b["whs_ns"], "wpws_ns": b["wpws_ns"],
         "wrapper_flip_flops": r.get("wrapper_flip_flops")}
    for k in ("early_path_delay_ns", "late_path_delay_ns"):
        if k in b:
            d[k] = b[k]
    return d


def integ(arm: str, pre: int) -> dict | None:
    f = R / f"integration_{arm}_pre{pre}_latency.json"
    if not f.exists():
        return None
    m = json.loads(f.read_text())["modes"]
    s, a = m["speculative_model_on"], m["safe_model_on"]
    g = "model gate (rule fire -> decision)"
    return {"gate_added_clocks": s["stages_cycles"][g], "tick_to_decision_clocks": s["tick_to_decision"],
            "price_to_first_byte_speculative_clocks": s["decision_to_first_byte"],
            "price_to_first_byte_safe_clocks": a["decision_to_first_byte"],
            "class_valid_clocks_after_instrument_field": s["class_valid_clocks_after_instrument_field"],
            "class_valid_clocks_before_rule_fire": s["class_valid_clocks_before_rule_fire"]}


def build() -> dict:
    out = {"convention": __doc__.strip().splitlines()[2], "ooc": {p: {n: ooc(p, n) for n in SUBJ} for p in PARTS}, "integration": {}}
    for arm in ("gbt", "lgs"):
        for pre in range(4):
            out["integration"][f"{arm}_pre{pre}"] = integ(arm, pre)
    f = R / "speculation.json"
    if f.exists():
        out["speculation"] = json.loads(f.read_text())["arms"]
    return out


def main() -> int:
    s = build()
    p = R / "summary.json"
    if "--check" in sys.argv:
        if not p.exists() or json.loads(p.read_text()) != s:
            print("results/b93/summary.json is out of date: run python3 results/b93/summary.py")
            return 1
        print("results/b93/summary.json is current")
        return 0
    p.write_text(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
