"""The joint closure planner: one diagnosis of every violation of a build, and one set of fixes that do not conflict.

One routed checkpoint reports timing, utilisation, power, DRC and methodology (``flow/build.tcl``); the closure loop
reads them together (:func:`violations`), and :func:`plan` picks at most one strategy per unmet goal so that the set:

- prefers hard resources (DSP48E1, block RAM, SRL, carry chain) over general-purpose logic among the strategies the
  reports support (the playbook ranks them first; see ``closure_playbook.applicable``);
- never spends a resource that is over its budget, or one whose headroom is below a reserve, on another goal's fix;
- never adds power while the power goal is unmet, or takes slack away (``wns: -``) while timing is unmet or tight;
- never pairs two fixes that push the same hard resource (DSP, BRAM) or a tight resource in opposite directions;
- goes back to the earliest stage any chosen fix changes. A fix at ``spec`` or ``architecture`` is not applied by the
  loop: the plan then holds only that stage's fixes, and the loop hands the design back to that stage (the re-entry
  state of ``agent/graph/pickup.py``: ``stage``, ``note``, ``note_role``, ``owners``).

Every attempt is recorded by :func:`action_record` as one JSON line in the schema ``fda.closure_action/1``: design tags,
report features before, the actions chosen and skipped (with reasons), the result after (per goal), and its cost. These
records are the training and evaluation data for choosing closure strategies (docs/closure_loop.md, "Action log").
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from agent.graph import closure_playbook as pb

SCHEMA = "fda.closure_action/1"
GOALS_ACT = ("G2", "G3", "G4", "CHK")
#: a met resource keeps at least this much headroom after another goal's fix (else the fix is skipped as conflicting)
RESERVE = {"lut": 128, "ff": 64, "bram_tile": 0.5, "dsp": 1}
#: below this setup slack (ns), a fix that usually costs slack is not combined with others
WNS_RESERVE_NS = 0.3
_RES = ("lut", "ff", "bram_tile", "dsp")


def violations(dg: dict[str, Any] | None, vec: dict[str, Any]) -> list[dict[str, Any]]:
    """Every violation of one build, from the goal vector and the routed reports: one row per problem, each with its
    goal, kind, the measured value and the target."""
    out: list[dict[str, Any]] = []
    if vec.get("G1", {}).get("met") is False:
        out.append({"goal": "G1", "kind": "function", "value": vec["G1"]["value"], "target": "all pass"})
    g2 = vec.get("G2") or {}
    if g2.get("met") is False and isinstance(g2.get("value"), dict):
        v = g2["value"]
        if (v.get("wns_ns") or 0) < 0:
            out.append({"goal": "G2", "kind": "setup", "value": v["wns_ns"], "target": 0.0,
                        "endpoints": v.get("failing_endpoints")})
        if (v.get("whs_ns") or 0) < 0:
            out.append({"goal": "G2", "kind": "hold", "value": v["whs_ns"], "target": 0.0})
        if g2.get("detail"):
            out.append({"goal": "G2", "kind": "timing_constraints", "value": g2["detail"], "target": "clean"})
    for k, r in pb.over_budget(vec).items():
        out.append({"goal": "G3", "kind": f"over_{k}", "value": (vec["G3"]["value"] or {}).get(k),
                    "target": (vec["G3"]["target"] or {}).get(k), "ratio": r})
    syn = (dg or {}).get("synth") or {}
    if syn.get("latches"):
        out.append({"goal": "G3", "kind": "latch", "value": syn["latches"][:5], "target": "none"})
    if syn.get("ram_in_registers"):
        out.append({"goal": "G3", "kind": "ram_in_registers", "value": syn["ram_in_registers"][:5], "target": "none"})
    g3 = vec.get("G3") or {}
    if g3.get("met") is False and "plan" in str(g3.get("detail") or ""):
        out.append({"goal": "G3", "kind": "plan_mapping", "value": str(g3["detail"])[:300], "target": "as planned"})
    g4 = vec.get("G4") or {}
    if g4.get("met") is False and isinstance(g4.get("value"), dict):
        out.append({"goal": "G4", "kind": "power", "value": g4["value"], "target": g4.get("target")})
    for k in ("drc", "methodology"):
        for r in ((dg or {}).get(k) or {}).get("rules") or []:
            if r.get("severity") in ("Error", "Critical Warning"):
                out.append({"goal": "CHK", "kind": f"{k}:{r['rule']}", "value": r["count"], "target": 0,
                            "severity": r["severity"], "description": r.get("description", "")[:160]})
    return out


def _tight(vec: dict[str, Any]) -> dict[str, str]:
    """Resources the plan must not spend: ``over`` (over budget) or ``reserve`` (headroom below the reserve)."""
    out = {k: "over" for k in pb.over_budget(vec) if k in _RES}
    for k in _RES:
        room = pb._headroom(vec, k)
        if k not in out and room is not None and room < RESERVE[k]:
            out[k] = "reserve"
    return out


def _wns(vec: dict[str, Any]) -> float | None:
    v = (vec.get("G2") or {}).get("value")
    return v.get("wns_ns") if isinstance(v, dict) else None


def conflict(s: pb.Strategy, goal: str, vec: dict[str, Any], chosen: list[pb.Strategy]) -> str | None:
    """Why ``s`` (for ``goal``) cannot join the plan, or None. Checked against the goal vector and the fixes chosen."""
    tight = _tight(vec)
    for r, sign in s.predicted.items():
        if sign != "+" or r not in _RES:
            continue
        if r in tight:
            return f"it adds {r}, which is {'over budget' if tight[r] == 'over' else 'below its reserve'}"
    if s.predicted.get("power") == "+" and goal != "G4" and (vec.get("G4") or {}).get("met") is False:
        return "it adds power while the power goal is unmet"
    if s.predicted.get("wns") == "-" and goal != "G2":
        w = _wns(vec)
        if (vec.get("G2") or {}).get("met") is False or (w is not None and w < WNS_RESERVE_NS):
            return f"it usually costs slack and the setup slack is {w} ns"
    for c in chosen:
        for r in _RES:
            a, b = s.predicted.get(r), c.predicted.get(r)
            if a and b and a != b and (r in tight or r in ("dsp", "bram_tile")):
                return f"it moves {r} the other way from {c.id}" + (f", and {r} is tight" if r in tight else "")
    return None


def plan(vec: dict[str, Any], dg: dict[str, Any] | None, spec: dict[str, Any] | None,
         plan_fails: list[str] | None = None, exhausted: set[tuple[str, str]] | frozenset = frozenset(),
         max_actions: int = 3) -> dict[str, Any]:
    """The joint plan for one iteration: ``{actions: [{id, cls, goal, stage, hard, why}], skipped: [...],
    target_stage, violations, goals_without_strategy}``. Unmet goals are taken worst first (normalised shortfall);
    ``exhausted`` holds (goal, class) pairs the stall rule has given up."""
    viol = violations(dg, vec)
    unmet = sorted([g for g in GOALS_ACT if (vec.get(g) or {}).get("met") is False],
                   key=lambda g: -((vec[g].get("shortfall") or 0)))
    chosen: list[tuple[pb.Strategy, str, str]] = []
    skipped: list[dict[str, Any]] = []
    without: list[str] = []
    for g in unmet:
        cands = [(s, why) for s, why in pb.applicable(g, dg or {}, vec, spec, plan_fails)
                 if s.phase in ("ready", "gated") and (g, s.cls) not in exhausted]
        pick = None
        for s, why in cands:
            if s.phase == "gated" and not why:
                continue
            c = conflict(s, g, vec, [x[0] for x in chosen])
            if c:
                skipped.append({"id": s.id, "goal": g, "why": c})
                continue
            if any(x[0].id == s.id for x in chosen):          # one strategy serving two goals: listed once
                pick = "dup"
                break
            pick = (s, why, g)
            break
        if pick is None:
            without.append(g)
        elif pick != "dup":
            chosen.append(pick)
        if len(chosen) >= max_actions:
            break
    stage = min((pb.STAGE_NUMBER[s.stage] for s, _, _ in chosen), default=pb.STAGE_NUMBER["rtl"])
    target = pb.STAGES[stage]
    if stage < pb.STAGE_NUMBER["rtl"]:          # back to spec or architecture: only that stage's fixes; the rest re-run after
        for s, _, g in chosen:
            if pb.STAGE_NUMBER[s.stage] != stage:
                skipped.append({"id": s.id, "goal": g, "why": f"deferred: the plan goes back to {target} first"})
        chosen = [x for x in chosen if pb.STAGE_NUMBER[x[0].stage] == stage]
    return {"actions": [{"id": s.id, "cls": s.cls, "goal": g, "stage": s.stage, "hard": s.hard, "why": why,
                         "predicted": dict(s.predicted)} for s, why, g in chosen],
            "skipped": skipped, "target_stage": target, "violations": viol, "goals_without_strategy": without}


def reentry(p: dict[str, Any]) -> dict[str, Any] | None:
    """For a plan that goes back to the spec or the architecture: the agent graph's re-entry state (the shape of
    ``agent.graph.pickup.prepare``), else None."""
    st = p.get("target_stage")
    if st not in ("spec", "architecture"):
        return None
    n = pb.STAGE_NUMBER[st]
    text = "; ".join(f"{a['goal']}: {pb.BY_ID[a['id']].title} ({a['why'][:200]})" for a in p["actions"])
    note = f"CLOSURE LOOP: the joint closure plan needs a change at the {st} stage: {text}"
    return {"stage": n, "note": note, "note_role": "clarify" if n == 0 else "rtl",
            "owners": {"rtl": [note]} if n == 1 else {}}


# --- the action log (training and evaluation data) -----------------------------------------------------------------

def design_tags(spec: dict[str, Any] | None, files: dict[str, str] | None, case: str | None = None) -> dict[str, Any]:
    """What kind of design this is, from spec.yaml and the RTL text (no build needed)."""
    spec = spec or {}
    files = {k: v for k, v in (files or {}).items() if not k.endswith(".xdc")}
    text = "\n".join(files.values())
    clocks = [c.get("freq_mhz") for c in spec.get("clocks") or []]
    return {"case": case, "top": spec.get("top"), "part": spec.get("part", "xc7a100tcsg324-1"),
            "clocks_mhz": clocks, "budget_given": sorted((spec.get("budget") or {}).keys()),
            "rtl_files": len(files or {}), "rtl_lines": text.count("\n"),
            "multiplies": len(re.findall(r"[\w\)\]]\s*\*\s*[\w\(\$]", re.sub(r"//[^\n]*|\(\*[^\n]*?\*\)", "", text))),
            "memories": len(re.findall(r"\]\s*\w+\s*\[\s*0?\s*:", text)),
            "ram_style": sorted(set(re.findall(r'ram_style\s*=\s*"(\w+)"', text))),
            "rtl_sha256": hashlib.sha256(text.encode()).hexdigest()[:16]}


def report_features(dg: dict[str, Any] | None, vec: dict[str, Any]) -> dict[str, Any]:
    """The numbers a strategy choice can be learned from: timing path shape, utilisation against budget and part,
    power by type, check counts."""
    dg = dg or {}
    t = dg.get("timing") or {}
    f = dg.get("setup_features") or {}
    u = dg.get("utilization") or {}
    p = dg.get("power") or {}
    comp = p.get("components") or {}
    bud = (vec.get("G3") or {}).get("target") or {}
    out = {"wns_ns": t.get("wns_ns"), "whs_ns": t.get("whs_ns"), "tns_ns": t.get("tns_ns"),
           "failing_endpoints": t.get("failing_endpoints"), "period_ns": t.get("period_ns"),
           **{f"path_{k}": f.get(k) for k in ("logic_levels", "carry_chain", "carry_runs", "lut_levels", "max_fanout",
                                               "route_pct", "dsp_on_path", "bram_on_path", "lut_arith", "cross_clock")},
           **{k: u.get(k) for k in (*_RES, "iob", "carry4")},
           **{f"{k}_budget_ratio": (round(float(u[k] or 0) / float(bud[k]), 4) if u.get(k) is not None and bud.get(k) else None)
              for k in _RES},
           **{f"{k}_part_ratio": (round(float(u[k] or 0) / float(u[f"{k}_available"]), 5)
                                  if u.get(k) is not None and u.get(f"{k}_available") else None) for k in _RES},
           "power_total_w": p.get("total_w"), "power_dynamic_w": p.get("dynamic_w"), "junction_c": p.get("junction_c"),
           **{"power_" + re.sub(r"\W+", "_", k.strip().lower()).strip("_") + "_w": v for k, v in comp.items()
              if not k.startswith(" ") and k not in ("Total",)},
           "latches": len((dg.get("synth") or {}).get("latches") or []),
           "ram_in_registers": len((dg.get("synth") or {}).get("ram_in_registers") or []),
           **{f"{k}_{s}": ((dg.get(k) or {}).get(s)) for k in ("drc", "methodology") for s in ("errors", "critical_warnings")}}
    return out


def goal_state(vec: dict[str, Any]) -> dict[str, Any]:
    return {g: {"met": (vec.get(g) or {}).get("met"), "shortfall": (vec.get(g) or {}).get("shortfall")}
            for g in ("G1", *GOALS_ACT)}


def action_record(*, run: str, iteration: int, tags: dict[str, Any], dg_before: dict[str, Any] | None,
                  vec_before: dict[str, Any], joint: dict[str, Any], decision: str, reason: str, outcome: str,
                  improved: list[str], worsened: list[str],
                  dg_after: dict[str, Any] | None, vec_after: dict[str, Any], early: dict[str, Any] | None,
                  usd: float, tokens: int, build_seconds: float | None, synth_seconds: float | None) -> dict[str, Any]:
    """One row of ``closure_actions.jsonl`` (schema ``fda.closure_action/1``). ``outcome`` is one of ``accepted``,
    ``built_reverted`` (built, judged and undone), ``early_reject``, ``g1_fail``, ``no_change``, ``clock_edit`` and
    ``loopback``; ``improved`` / ``worsened`` are the controller's own judgement (the goals that moved, with its
    tolerances), so a reverted change can still show which goal it helped."""
    return {"schema": SCHEMA, "run": run, "iter": iteration, "design": tags,
            "features": report_features(dg_before, vec_before), "goals_before": goal_state(vec_before),
            "violations": [{k: v for k, v in x.items() if k in ("goal", "kind", "value", "target", "ratio")}
                           for x in joint.get("violations") or []],
            "actions": joint.get("actions") or [], "skipped": joint.get("skipped") or [],
            "target_stage": joint.get("target_stage"),
            "result": {"decision": decision, "outcome": outcome, "reason": reason[:400], "worsened": list(worsened), "early_reject": bool(early and early.get("reject")),
                       "early": early, "goals_after": goal_state(vec_after), "improved": list(improved),
                       "features_after": report_features(dg_after, vec_after) if dg_after else None},
            "cost": {"usd": round(usd, 6), "tokens": tokens, "build_seconds": build_seconds, "synth_seconds": synth_seconds}}
