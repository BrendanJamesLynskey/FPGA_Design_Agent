"""The rules an options document must satisfy (brief 104), and the fields code computes instead of the model.

The generator (a model) proposes; this module disposes. It checks, with no model call:

* the shape of the document (``fda-options/1``) and its text limits;
* **every number cites a source**: a gain is ``model`` (arithmetic on cited analysis facts), ``measurement`` (cites a recorded earlier
  change) or ``guess`` (labelled, shown as a guess); each cited id must exist in the analysis, and the file behind it is shown;
* a gain cannot exceed what the analysis bounds it by (the clocks of the stages it touches; the LUTs of the components in scope; the
  clock period for slack);
* **scopes respect ownership**: only owned components, the stages touched live inside the scope, whole-design means every owned component;
* a change that crosses a boundary between components, or that the option says changes a port, is **flagged as a contract change** by code
  (the model cannot clear the flag), and needs the owner's approval unless the manifest already approves it (brief 102);
* what is not touched, the CLI scope and the cost (iterations times the recorded build time) are computed here, not taken from the model.

``classify_request`` decides, before any model call, whether the request is clear enough: an ambiguous or unsupported request gives a
question and no options.
"""

from __future__ import annotations

import math
import re
from typing import Any

from agent.core import managed

SCHEMA = "fda-options/1"
GOALS = {
    "latency": re.compile(r"latenc|tick[- ]to[- ]trade|fewer clocks|clock cycles|wire[- ]to[- ]wire|response time|reaction time|round[- ]trip", re.I),
    "timing": re.compile(r"fmax|frequency|clock rate|\bmhz\b|\bghz\b|timing|slack|\bwns\b|critical path|close timing|meet timing|setup violation|higher clock|faster clock|speed grade", re.I),
    "area": re.compile(r"smaller|\barea\b|\blut|resources?|utili[sz]ation|footprint|\bfit\b|fewer (?:luts|registers|flip)|reduce size|shrink", re.I),
    "power": re.compile(r"power|\bwatts?\b|energy|thermal|\bcooler\b", re.I),
}
VAGUE = re.compile(r"\b(faster|speed(?:\s|-)?up|quicker|performance|better|improve|optimi[sz]e|more efficient)\b", re.I)
UNSUPPORTED = re.compile(r"throughput|bandwidth|gbps|\bfps\b|frames per second|accuracy|snr|\bdsp quality\b|sample rate|noise|reliab|\bmtbf\b", re.I)
METRICS = {"latency_clocks": "clocks", "wns_ns": "ns", "lut": "LUT", "ff": "FF", "power_w": "W"}
GOAL_METRICS = {"latency": {"latency_clocks"}, "timing": {"wns_ns"}, "area": {"lut", "ff"}, "power": {"power_w"}}
BASES = ("model", "measurement", "guess")
#: which fact ids can be the basis of a model gain in each metric
RELEVANT = {"latency_clocks": re.compile(r"^(stage\.[^.]+\.(clocks|removable)|latency\.)"), "wns_ns": re.compile(r"^(timing\.|clock\.|stage\.[^.]+\.slack_ns)"),
            "lut": re.compile(r"^res\."), "ff": re.compile(r"^res\."), "power_w": re.compile(r"^power\.")}
RELEVANT_TEXT = {"latency_clocks": "stage.<id>.clocks, stage.<id>.removable or latency.*", "wns_ns": "timing.*, clock.* or stage.<id>.slack_ns", "lut": "res.*", "ff": "res.*",
                 "power_w": "power.*"}
OPTION_KEYS = {"id", "title", "scope", "approach", "techniques", "touches_stages", "gain", "cost", "risk", "interface_changes"}
GAIN_KEYS = {"metric", "low", "high", "basis", "cites", "basis_note"}
RISK_KEYS = {"gates", "contract_change", "contract_note", "needs_eqy", "needs_board", "summary"}
MAX_TEXT = 700
MIN_OPTIONS, MAX_OPTIONS = 2, 4


def classify_request(request: str, project: managed.Project | None, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{"status": "ok", "goal", "pinned": [...]}`` or ``{"status": "question", "reason", "question"}``. No model call.

    * No text, a goal the analysis cannot serve, two different goals, or a vague one ("faster", "better") is a question.
    * A request naming components pins the scope to them; naming only frozen ones, or an ambiguous alias, is a question."""
    text = (request or "").strip()
    if not text:
        return _q("ambiguous", "What should improve: lower latency (fewer clocks from input to output), a higher clock rate (timing closure), a smaller design (LUTs and flip-flops), or lower power?")
    goals = [g for g, rx in GOALS.items() if rx.search(text)]
    if UNSUPPORTED.search(text) and not goals:
        return _q("unsupported", "That is not something the analysis measures yet (it covers latency, timing, area and power). "
                                 "Which of those should improve, and by how much?")
    if len(goals) > 1:
        return _q("ambiguous", f"The request mentions {' and '.join(goals)}, and they pull different ways. Which one comes first?")
    if not goals:
        if VAGUE.search(text):
            return _q("ambiguous", f"\"{text}\": faster in which sense? Lower latency (fewer clocks from input to output), a higher clock rate (timing closure), or smaller or lower-power? "
                                   "The options differ for each.")
        return _q("unsupported", "I cannot tell which metric this means. The analysis covers latency, timing, area and power; which should improve?")
    goal = goals[0]
    pinned: list[str] = []
    if project is not None:
        res = managed.resolve_request(project, text)
        if res.question and not res.question.startswith("the request does not say which"):
            return _q("ambiguous", res.question)
        if res.scope is not None and res.scope.source == "resolved":
            pinned = list(res.scope.components)
    if analysis is not None:
        if goal == "latency" and not analysis.get("latency"):
            return _q("no_data", "This design has not declared its latency chain (no latency_stages.yaml), so options for lower latency would be guesses. "
                                 "Declare the chain, or ask for timing, area or power instead.")
        if goal == "timing" and not (analysis.get("timing") or {}):
            return _q("no_data", "There is no timing report for this design (no build). I can offer to build it once, read-only afterwards; or ask for something that needs no build.")
        if goal == "area" and not (analysis.get("resources") or {}).get("total"):
            return _q("no_data", "There is no utilisation report for this design (no build). I can offer to build it once; or ask for latency or timing.")
        if goal == "power":
            return _q("unsupported", "Power is not analysed yet: no per-module power in the records this tool reads. Latency, timing and area are supported.")
    return {"status": "ok", "goal": goal, "pinned": pinned}


def _q(reason: str, question: str) -> dict[str, Any]:
    return {"status": "question", "reason": reason, "question": question}


# --- the check --------------------------------------------------------------------------------------------------------

def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _text(x: Any, limit: int = MAX_TEXT) -> bool:
    return isinstance(x, str) and 0 < len(x.strip()) <= limit


def ceiling(metric: str, stages: list[str], scope: list[str], analysis: dict[str, Any], *, blind: bool = False) -> tuple[float | None, str]:
    """The most a change of this kind in this scope can gain, from the analysis alone, and why. ``blind`` (the stage file's removable
    hints withheld from the model) bounds a latency cut by the stage's own clocks instead."""
    facts = analysis["facts"]
    if metric == "latency_clocks":
        tot = 0
        for s in stages:
            f = facts.get(f"stage.{s}.clocks")
            r = facts.get(f"stage.{s}.removable")
            if f is None:
                continue
            tot += f["value"] if (blind or r is None) else r["value"]
        total = facts.get("latency.total_clocks")
        cap = min(tot, total["value"]) if total else tot
        return float(cap), ("the clocks of the touched stages" if blind else "the removable clocks of the touched stages, per the stage file") + f" ({cap})"
    if metric in ("lut", "ff"):
        tot, seen = 0, False
        for c in scope:
            f = facts.get(f"res.{c}.{metric}")
            if f is not None:
                tot += f["value"]
                seen = True
        return (float(tot), f"the {metric.upper()}s in the scoped components ({tot})") if seen else (None, "no per-module figure to bound it")
    if metric == "wns_ns":
        p = facts.get("timing.period_ns") or facts.get("latency.period_ns")
        period = p["value"] if p else None
        return (float(period), f"one clock period ({period} ns)") if period else (None, "no clock period known")
    return None, "no bound known"


def check_options(doc: Any, analysis: dict[str, Any], project: managed.Project | None, *, goal: str | None = None, pinned: list[str] | None = None,
                  blind: bool = False, min_options: int = MIN_OPTIONS) -> dict[str, Any]:
    """Validate and complete a generator document. Returns ``{"status", "question", "options" (valid, completed), "rejected"
    ([{id, problems}]), "notes" (document-level), "repairable" (problems a second model call could fix)}``. Never raises on bad input."""
    out: dict[str, Any] = {"status": "options", "question": None, "options": [], "rejected": [], "notes": [], "repairable": []}
    if not isinstance(doc, dict):
        out["status"] = "invalid"
        out["notes"].append("the document is not a JSON object")
        out["repairable"].append("the reply must be one JSON object")
        return out
    if doc.get("status") == "question":
        q = doc.get("question")
        if _text(q, 600):
            out.update(status="question", question=q.strip())
            return out
        out["status"] = "invalid"
        out["repairable"].append("status question needs a question string")
        return out
    if doc.get("status") != "options" or not isinstance(doc.get("options"), list):
        out["status"] = "invalid"
        out["repairable"].append("status must be 'options' with a list of options, or 'question' with a question")
        return out
    owned = [c for c in (project.owned() if project else [])]
    owned_names = [c.name for c in owned]
    visible = {c.name: c for c in (project.components if project else []) if c.ownership != "excluded"}
    stage_by_id = {s["id"]: s for s in ((analysis.get("latency") or {}).get("stages") or [])}
    facts = analysis["facts"]
    ids_seen: set[str] = set()
    for i, raw in enumerate(doc["options"]):
        oid = raw.get("id") if isinstance(raw, dict) and isinstance(raw.get("id"), str) else f"#{i + 1}"
        probs: list[str] = []
        opt = _check_one(raw, oid, analysis, project, owned_names, visible, stage_by_id, facts, goal, pinned or [], blind, probs)
        if oid in ids_seen:
            probs.append(f"duplicate option id {oid}")
        ids_seen.add(oid)
        if probs or opt is None:
            out["rejected"].append({"id": oid, "problems": probs})
            out["repairable"] += [f"{oid}: {p}" for p in probs]
        else:
            out["options"].append(opt)
    n = len(out["options"])
    if n < min_options:
        out["notes"].append(f"{n} valid option(s); {min_options} to {MAX_OPTIONS} are expected")
        out["repairable"].append(f"only {n} valid option(s); offer {min_options} to {MAX_OPTIONS}")
    if len(out["options"]) > MAX_OPTIONS:
        out["notes"].append(f"{len(out['options'])} options offered; kept the first {MAX_OPTIONS}")
        out["options"] = out["options"][:MAX_OPTIONS]
    kinds = {o["scope"]["kind"] for o in out["options"]}
    if min_options > 1 and len(owned_names) >= 2 and out["options"] and not ({"whole_design"} & kinds and ({"modules", "subsystem"} & kinds)):
        out["notes"].append("the analysis supports both a narrow and a broad option, but the set has only " + ("broad ones" if "whole_design" in kinds else "narrow ones"))
        out["repairable"].append("include at least one narrow option (individual modules) and one broad option (the whole design)")
    # renumber what survived (ids stay stable within the document)
    for k, o in enumerate(out["options"], 1):
        o["n"] = k
    if not out["options"]:
        out["status"] = "invalid"
    return out


def _check_one(raw: Any, oid: str, analysis: dict[str, Any], project: managed.Project | None, owned_names: list[str], visible: dict[str, managed.Component],
               stage_by_id: dict[str, dict[str, Any]], facts: dict[str, dict[str, Any]], goal: str | None, pinned: list[str], blind: bool,
               probs: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        probs.append("an option must be a JSON object")
        return None
    for k in sorted(set(raw) - OPTION_KEYS):
        probs.append(f"unknown key {k!r}")
    for k in ("title", "approach"):
        if not _text(raw.get(k)):
            probs.append(f"{k} must be a non-empty string of at most {MAX_TEXT} characters")
    # scope: ownership, kind, pinned
    sc = raw.get("scope")
    comps: list[str] = []
    kind = None
    if not isinstance(sc, dict) or sc.get("kind") not in ("whole_design", "subsystem", "modules") or not isinstance(sc.get("components"), list) or not sc["components"]:
        probs.append("scope must be {kind: whole_design|subsystem|modules, components: [names]}")
    else:
        kind = sc["kind"]
        comps = [c for c in sc["components"] if isinstance(c, str)]
        for c in comps:
            if c not in visible:
                probs.append(f"scope names {c!r}, which is not a component of this project")
            elif visible[c].ownership != "owned":
                probs.append(f"scope names {c!r}, which is {visible[c].ownership}: it cannot be edited, so it cannot be in a scope")
        if len(set(comps)) != len(comps):
            probs.append("scope lists a component twice")
        if kind == "whole_design" and set(comps) != set(owned_names):
            probs.append(f"a whole_design scope is every owned component ({', '.join(owned_names)})")
        if kind in ("modules", "subsystem") and owned_names and set(comps) == set(owned_names) and len(owned_names) > 1:
            probs.append("this scope is every owned component: call it whole_design")
        if pinned and not set(comps) <= set(pinned):
            probs.append(f"the request names {', '.join(pinned)}: the scope must stay inside them")
    # stages
    ts = raw.get("touches_stages", [])
    if not isinstance(ts, list) or not all(isinstance(x, str) for x in ts):
        probs.append("touches_stages must be a list of stage ids")
        ts = []
    stage_comps: dict[str, str | None] = {}
    for s in ts:
        st = stage_by_id.get(s)
        if st is None:
            probs.append(f"touches_stages names {s!r}, which is not a stage of the latency chain in the analysis")
            continue
        stage_comps[s] = st.get("component")
        c = st.get("component")
        if c is not None and c in visible and visible[c].ownership != "owned":
            probs.append(f"stage {s} lives in {c}, which is {visible[c].ownership}: it cannot be edited")
        elif c is not None and comps and c not in comps:
            probs.append(f"stage {s} lives in {c}, which is outside the option's scope ({', '.join(comps)})")
        elif c is None and st["kind"] != "structure":
            probs.append(f"stage {s} has no known component, so no scope can cover it")
    if goal == "latency" and not ts:
        probs.append("a latency option names the stages it touches (touches_stages)")
    techniques = raw.get("techniques", [])
    if not (isinstance(techniques, list) and all(_text(t, 80) for t in techniques)):
        probs.append("techniques must be a list of short strings")
        techniques = []
    # gain
    g = raw.get("gain")
    gain_out: dict[str, Any] | None = None
    if not isinstance(g, dict):
        probs.append("gain is required: {metric, low, high, basis, cites, basis_note}")
    else:
        for k in sorted(set(g) - GAIN_KEYS):
            probs.append(f"gain: unknown key {k!r}")
        metric = g.get("metric")
        if metric not in METRICS:
            probs.append(f"gain.metric must be one of {sorted(METRICS)}")
        elif goal and metric not in GOAL_METRICS.get(goal, set(METRICS)):
            probs.append(f"gain.metric {metric} does not answer a {goal} request (use {', '.join(sorted(GOAL_METRICS[goal]))})")
        lo, hi = g.get("low"), g.get("high")
        if not (_num(lo) and _num(hi)) or lo < 0 or hi < lo:
            probs.append("gain.low and gain.high must be numbers with 0 <= low <= high (the size of the improvement)")
        basis = g.get("basis")
        if basis not in BASES:
            probs.append(f"gain.basis must be one of {BASES}")
        cites = g.get("cites", [])
        if not (isinstance(cites, list) and all(isinstance(c, str) for c in cites)):
            probs.append("gain.cites must be a list of fact ids")
            cites = []
        for c in cites:
            if c not in facts:
                probs.append(f"gain cites {c!r}, which is not a fact in the analysis")
        if basis in ("model", "measurement") and not cites:
            probs.append(f"a {basis} gain cites the facts it rests on (gain.cites); a gain with no basis is a guess, and says so")
        if basis == "model" and cites and metric in RELEVANT and not any(c in facts and RELEVANT[metric].match(c) for c in cites):
            probs.append(f"a model gain in {metric} cites at least one fact about that quantity ({RELEVANT_TEXT[metric]}); the facts cited here are about something else")
        if basis == "measurement" and cites and not any(facts[c]["origin"] == "prior_run" for c in cites if c in facts):
            probs.append("a measurement gain cites a recorded earlier change (a prior_run fact); the analysis has none for this, so use model or guess")
        if not _text(g.get("basis_note"), 500):
            probs.append("gain.basis_note states the arithmetic or the reason in a sentence")
        if metric in METRICS and _num(hi) and basis in BASES:
            cap, why = ceiling(metric, ts, comps, analysis, blind=blind)
            if cap is not None and hi > cap + 1e-9:
                probs.append(f"gain.high {hi} exceeds what the analysis allows: {why}")
            gain_out = {"metric": metric, "unit": METRICS[metric], "low": lo, "high": hi, "basis": basis, "cites": list(cites), "basis_note": str(g.get("basis_note", "")).strip(),
                        "ceiling": cap, "ceiling_basis": why,
                        "sources": sorted({facts[c]["file"] for c in cites if c in facts})}
    # risk, interface changes
    r = raw.get("risk")
    risk_in: dict[str, Any] = {}
    if not isinstance(r, dict):
        probs.append("risk is required: {gates, contract_change, contract_note, needs_eqy, needs_board, summary}")
    else:
        for k in sorted(set(r) - RISK_KEYS):
            probs.append(f"risk: unknown key {k!r}")
        risk_in = r
        if not (isinstance(r.get("gates"), list) and r["gates"] and all(_text(x, 200) for x in r["gates"])):
            probs.append("risk.gates lists what the gates must prove (a non-empty list of short strings)")
        for k in ("contract_change", "needs_eqy", "needs_board"):
            if not isinstance(r.get(k), bool):
                probs.append(f"risk.{k} must be true or false")
        if not _text(r.get("summary"), MAX_TEXT):
            probs.append("risk.summary states the main risk in a sentence or two")
    ic = raw.get("interface_changes", [])
    if not (isinstance(ic, list) and all(isinstance(x, dict) and isinstance(x.get("component"), str) and _text(x.get("change"), 300) for x in ic)):
        probs.append("interface_changes is a list of {component, port, change}")
        ic = []
    for x in ic:
        if x["component"] not in comps:
            probs.append(f"interface_changes names {x['component']!r}, outside the scope")
    cost_in = raw.get("cost")
    iters = (cost_in or {}).get("iterations") if isinstance(cost_in, dict) else None
    if not (isinstance(iters, dict) and all(isinstance(iters.get(k), int) and not isinstance(iters.get(k), bool) for k in ("low", "high")) and 1 <= iters["low"] <= iters["high"] <= 8):
        probs.append("cost.iterations is {low, high}: whole numbers of build-and-check rounds, 1 to 8")
        iters = None
    if probs or gain_out is None or kind is None or iters is None:
        return None
    # computed fields
    flags: list[str] = []
    cs = sorted({c for c in stage_comps.values() if c})
    if len(cs) >= 2:
        flags.append(f"the change spans the boundary between {' and '.join(cs)}: it moves or removes logic across a component edge, so the interface contract (ports and boundary timing) must be re-checked")
    for x in ic:
        flags.append(f"{x['component']}: {x.get('port') or 'a port'}: {x['change']}")
    cdc_stages = [s for s in ts if stage_by_id.get(s, {}).get("kind") == "cdc"]
    if cdc_stages:
        flags.append(f"stage {', '.join(cdc_stages)} is a clock-domain crossing: report_cdc and the crossing's own tests must still pass")
    contract = bool(risk_in.get("contract_change")) or bool(len(cs) >= 2 or ic)
    approved = set(project.approved_contract_changes) if project else set()
    affected = sorted(set(cs) | {x["component"] for x in ic} | (set(comps) if risk_in.get("contract_change") else set()))
    needs_owner = contract and not (affected and set(affected) <= approved)
    added = bool(len(cs) >= 2 or ic) and not risk_in.get("contract_change")
    not_touched = [{"component": c.name, "why": ("frozen: read only" if c.ownership == "frozen" else "owned, outside this option's scope")}
                   for c in (project.components if project else []) if c.name in visible and c.name not in comps]
    wall = (facts.get("build.wall_s") or {}).get("value")
    runs = {"low": iters["low"], "high": iters["high"]}
    cost = {"iterations": iters, "vivado_runs": runs,
            "wall_minutes": ({"low": round(iters["low"] * wall / 60, 1), "high": round(iters["high"] * wall / 60, 1), "basis": "iterations x the recorded build time",
                              "cite": "build.wall_s", "file": facts["build.wall_s"]["file"]} if wall else None),
            "model_usd": None, "note": (str((cost_in or {}).get("note", "")).strip()[:300] or None),
            "basis": "iterations are the generator's estimate (a guess); wall time is those times the recorded Vivado run" if wall else
                     "iterations are the generator's estimate (a guess); no recorded build time, so no wall-time figure"}
    return {"id": oid, "title": raw["title"].strip(), "scope": {"kind": kind, "components": comps, "cli": "--scope " + ",".join(comps)},
            "approach": raw["approach"].strip(), "techniques": techniques, "touches_stages": ts,
            "stage_components": {s: c for s, c in stage_comps.items()}, "gain": gain_out, "cost": cost,
            "risk": {"gates": [x.strip() for x in risk_in["gates"]], "contract_change": contract, "contract_flags": flags,
                     "contract_flag_added_by_checker": added, "needs_owner_approval": needs_owner, "contract_affected": affected,
                     "needs_eqy": bool(risk_in.get("needs_eqy")), "needs_board": bool(risk_in.get("needs_board")) or bool(cdc_stages),
                     "summary": risk_in["summary"].strip(), "contract_note": str(risk_in.get("contract_note", "")).strip()[:400]},
            "interface_changes": ic, "not_touched": not_touched,
            "hidden_components": analysis.get("hidden_components", 0)}
