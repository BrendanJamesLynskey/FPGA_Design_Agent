#!/usr/bin/env python3
"""Brief 136: assemble results/b136/what_if.json (the machine-readable form of docs/what_if_decisions.md) from the scenario records in this folder.

    python3 results/b136/build_what_if.py
Prose fields (decision, alternative, agent_response) are the same text as the document, shortened; numbers come from the JSON records, never typed here."""
from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parent
load = lambda n: json.loads((D / n).read_text())
mut = load("mutants_ppm.json")
ct = load("cut_through.json")
lt = load("latency_targets.json")
eye = load("eye_target.json")

# scenario 1: classify each mutant by which ppm points catch it (functional verdict: a frame lost or changed, or the overflow counter above 0)
NARROW = ["ppm+100", "ppm-100"]
FULL = ["ppm+0", "ppm+100", "ppm-100", "ppm+300", "ppm-300"]
rows = []
for m in mut["mutants"]:
    p = m.get("points", {})
    caught = {k: bool(p[k]["functional_fail"]) for k in FULL if k in p}
    twin = {k: bool(p[k]["twin_mismatch"]) for k in FULL if k in p}
    strict = {k: caught[k] or twin[k] for k in caught}          # the stricter oracle: also any difference from the Python twin (catches an idle block inside a frame, which the frame parser tolerates)
    c_narrow = any(caught.get(k) for k in NARROW)
    c_full = any(caught.values())
    c_zero = bool(caught.get("ppm+0"))
    s_narrow, s_full = any(strict.get(k) for k in NARROW), any(strict.values())
    rows.append(dict(name=m["name"], why=m.get("why"), status=m["status"], caught_functional=caught, differs_from_twin=twin,
                     caught_by_narrow_set_plus_100=c_narrow, caught_by_full_set=c_full, caught_at_zero_ppm=c_zero,
                     escapes_narrow_set=(c_full and not c_narrow),
                     caught_strict=strict, strict_caught_by_narrow_set=s_narrow, strict_caught_by_full_set=s_full, strict_caught_at_zero_ppm=bool(strict.get("ppm+0")),
                     strict_escapes_narrow_set=(s_full and not s_narrow)))

s1 = dict(frames_per_point=mut["frames_per_point"], mutants=rows,
          escapes_narrow_set=[r["name"] for r in rows if r["escapes_narrow_set"] and r["name"] != "unmutated"],
          caught_by_both=[r["name"] for r in rows if r["caught_by_narrow_set_plus_100"] and r["name"] != "unmutated"],
          caught_by_neither=[r["name"] for r in rows if not r["caught_by_full_set"] and r["name"] != "unmutated"],
          strict_escapes_narrow_set=[r["name"] for r in rows if r["strict_escapes_narrow_set"] and r["name"] != "unmutated"],
          strict_caught_by_neither=[r["name"] for r in rows if not r["strict_caught_by_full_set"] and r["name"] != "unmutated"],
          control_unmutated_clean=not any(next(r for r in rows if r["name"] == "unmutated")["caught_functional"].values()))

out = dict(schema="fda.b136.what_if/1", date="2026-11-21", delegated_by="owner decision 23 (2026-11-21 14:34): the planner decides, recorded as the planner's, not a human approval",
           scenarios=[
    dict(id=1, requirement="B96-F-OFFSET", recommendation="test +-100 and +-300 ppm", alternative="keep only +-100 ppm (802.3 per end)", measured=s1,
         agent_response="keep +-300 ppm in the plan unless the narrow set also catches every seeded bug; name the bugs that escape; ask for the long run before accepting"),
    dict(id=2, requirement="127 late-verdict policy", recommendation="STRICT", alternative="cut-through default", measured=ct,
         agent_response="accept; risk counts unverified orders as live exposure, caps them in flight, offers start-at-verdict; report the share with the assumed frame-error grid labelled assumed"),
    dict(id=3, requirement="B96-F-LEAN-CKSUM-TCP", recommendation="30 words (the build's payload)", alternative="32 words (the RTL registers' capacity)",
         measured=dict(builds_at_32=True, proof_text_changed=False, axioms_unchanged=True, rtl_equations_correct_for_all_ones_payload=dict(words_0_to_32=True, words_33_to_39=False),
                       first_counterexample=dict(words=33, rtl_checksum="0xafb2", internet_checksum="0xaf92"), rtl_has_a_length_input=False, record="results/b136/lean/run_lean.log"),
         agent_response="take 32, record that the bound is two registers' capacity, new approval needed, formal/lean unchanged by this brief"),
    dict(id=4, requirement="latency targets E <= 16, tick-to-trade <= 20 clocks", recommendation="regression bounds", alternative="targets", measured=lt,
         agent_response="ask which definition; mark current builds failing the board target; keep old bounds; run lat_all3_bypass first; loop timing is the one item that can reach 20 (prediction)"),
    dict(id=5, requirement="B96-F-LEAN-GRAY-DECODE", recommendation="gray_sample accepted by the planner", alternative="human rejects it as too weak (mid-glitch samples)",
         measured=dict(statement="gray_sample_bitwise: every bit of g is the old or the new bit of the code => decode is the old or the new count", builds=True, axioms=["propext", "Classical.choice", "Quot.sound"],
                       two_step_counterexample=dict(width=3, counts=[3, 5], mixed_value="0b011", decodes_to=2), record="results/b136/lean/Stronger.lean, run_lean.log"),
         agent_response="offer the bitwise statement; ask the RTL model for a per-bit skew bound below one source clock; do not claim safety from the proof alone"),
    dict(id=6, requirement="B96-P-EYE", recommendation="bound 0.5 UI", alternative="0.75 UI", measured=eye,
         agent_response="do not call 0.75 passed or failed on this grid; rescan the edges finer and repeated at 1e-9 (owner's board session)"),
], not_measured=["no board", "no Vivado", "frame-error rate and packet lengths of a real feed", "the RTL at 33 words", "the circuit's bit skew", "scenario 1 runs one bench length (see mutants_ppm.json frames_per_point)"])
(D / "what_if.json").write_text(json.dumps(out, indent=1) + "\n")
print("functional: narrow escapes", s1["escapes_narrow_set"], "neither", s1["caught_by_neither"]); print("strict: narrow escapes", s1["strict_escapes_narrow_set"], "neither", s1["strict_caught_by_neither"])
