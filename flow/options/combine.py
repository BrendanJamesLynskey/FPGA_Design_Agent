"""The deterministic combiner (brief 104A): code, not the model, builds the cumulative options.

The generator (a model step) offers single changes. A user who asks for "lower latency" usually wants the changes that add up, and the 104 back-test showed the
model offers disjoint singles and does not combine them. This module takes the options that **passed every check** and builds combinations of them:

* **compatible**: two options combine only if they touch no stage in common and declare no interface change to the same port of the same component. Scopes are
  already owned-only (the checker); the combined scope is the union of the components, and it is ``whole_design`` when that is every owned component.
* **gain composed by code**: for ``latency_clocks`` the stage cuts add when the stages are disjoint (stage clocks are additive on a chain that reconciles with the
  bench), so ``low`` and ``high`` are the sums, capped by the checker's own ceiling for the union. Where an earlier run of exactly that set of stages was measured
  (a ``prior_run`` fact of the analysis), the measured cut replaces the sum and the basis becomes ``measurement``. For ``lut``/``ff`` the gains add only when the
  components are disjoint. A ``wns_ns`` gain is **not composable** (the worst path limits the clock: two slack gains do not add), and neither is any pair whose
  gains cannot be bounded: they are listed with the reason and never offered. If any part is a labelled guess the whole is a guess.
* **validated like any option**: the combined option is built as a raw option and passed through ``schema.check_single``, so its flags (a change spanning two
  components, a clock crossing) are computed by the same code and the owner-approval rule is the same.
* **ranked by code, capped**: the best combination of each size, by (measured earlier, composed mid-gain, fewer components touched, no owner approval needed, order of the parts),
  then the smallest sizes and the largest, at most ``MAX_COMBINED`` in all. The rule is in :func:`rank_key`; it never reads a measured result.

The combiner reads only the analysis and the model's checked options. It never sees a back-test's truth.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from flow.options import schema

COMBINER_VERSION = "1"
MAX_COMBINED = 4
MAX_PARTS = 4
ORIGIN = "combiner"


def _mid(g: dict[str, Any]) -> float:
    return (g["low"] + g["high"]) / 2


def _stage_facts(stages: list[str], analysis: dict[str, Any]) -> list[str]:
    return [f"stage.{s}.clocks" for s in stages if f"stage.{s}.clocks" in analysis["facts"]]


def conflict(parts: list[dict[str, Any]]) -> str | None:
    """Why these options cannot be applied together, or None."""
    for a, b in itertools.combinations(parts, 2):
        common = set(a["touches_stages"]) & set(b["touches_stages"])
        if common:
            return f"options {a['id']} and {b['id']} both touch stage {', '.join(sorted(common))}: they are alternatives, not additions"
        pa = {(x["component"], x.get("port") or "") for x in a.get("interface_changes", [])}
        pb = {(x["component"], x.get("port") or "") for x in b.get("interface_changes", [])}
        if pa & pb:
            c, p = sorted(pa & pb)[0]
            return f"options {a['id']} and {b['id']} both change {p or 'a port'} of {c}: their interface changes conflict"
    return None


def compose_gain(parts: list[dict[str, Any]], analysis: dict[str, Any], *, blind: bool, scope: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    """The composed gain of ``parts`` as a raw gain dict, or ``(None, why it is not composable)``."""
    metrics = {p["gain"]["metric"] for p in parts}
    if len(metrics) != 1:
        return None, "the parts measure different quantities (" + ", ".join(sorted(metrics)) + ")"
    metric = metrics.pop()
    chain = [x["id"] for x in ((analysis.get("latency") or {}).get("stages") or [])]
    stages = sorted({s for p in parts for s in p["touches_stages"]}, key=lambda s: chain.index(s) if s in chain else len(chain))
    ids = "+".join(p["id"] for p in parts)
    if metric == "wns_ns":
        return None, "slack gains do not add: the worst path sets the clock period, so the gain of two changes is not the sum of their gains"
    if metric == "latency_clocks":
        if not stages:
            return None, "no stages are named, so the cuts cannot be shown to add"
        # disjoint stages (checked by conflict()): the cuts of separate stages on one chain add
        low, high = sum(p["gain"]["low"] for p in parts), sum(p["gain"]["high"] for p in parts)
        cap, why = schema.ceiling(metric, stages, scope, analysis, blind=blind)
        if cap is not None and high > cap:
            high = cap
        low = min(low, high)
        basis = "guess" if any(p["gain"]["basis"] == "guess" for p in parts) else "model"
        cites = sorted({c for p in parts for c in p["gain"]["cites"]} | set(_stage_facts(stages, analysis)))
        note = (f"Composed by code: the latency cuts of options {ids} add because their stages ({', '.join(stages)}) are disjoint and stage clocks add along the chain: "
                f"low = {sum(p['gain']['low'] for p in parts):g}, high = {sum(p['gain']['high'] for p in parts):g}"
                + (f", capped at {cap:g} ({why})" if cap is not None and high < sum(p['gain']['high'] for p in parts) else "")
                + ". Not a simulation of the combination: interactions between the changes are not modelled.")
        out = {"metric": metric, "low": low, "high": high, "basis": basis, "cites": [] if basis == "guess" else cites, "basis_note": note}
        # an earlier run of exactly this set of stages, measured: the measurement replaces the sum
        for pr in analysis.get("prior_runs") or []:
            if pr["metric"] == metric and set(pr["stages"]) == set(stages):
                gain = pr["gain"]
                out.update(low=gain, high=gain, basis="measurement", cites=sorted({pr["fact"], *_stage_facts(stages, analysis)}),
                           basis_note=f"Measured earlier: this exact set of stages was built and simulated in an earlier run ({pr['name']}: {pr['summary']}); the cut was {gain:g} clock(s) ({pr['fact']}). "
                                      f"The sum of the parts would have been {sum(p['gain']['low'] for p in parts):g} to {sum(p['gain']['high'] for p in parts):g}.")
                break
        return out, None
    if metric in ("lut", "ff"):
        comps = [set(p["scope"]["components"]) for p in parts]
        for a, b in itertools.combinations(range(len(parts)), 2):
            if comps[a] & comps[b]:
                return None, f"options {parts[a]['id']} and {parts[b]['id']} change the same component's {metric.upper()}s ({', '.join(sorted(comps[a] & comps[b]))}): the savings can overlap, so they are not added"
        low, high = sum(p["gain"]["low"] for p in parts), sum(p["gain"]["high"] for p in parts)
        cap, why = schema.ceiling(metric, [], scope, analysis, blind=blind)
        basis = "guess" if (any(p["gain"]["basis"] == "guess" for p in parts) or cap is None) else "model"
        if cap is not None and high > cap:
            high = cap
        cites = sorted({c for p in parts for c in p["gain"]["cites"]})
        return {"metric": metric, "low": min(low, high), "high": high, "basis": basis, "cites": [] if basis == "guess" else cites,
                "basis_note": f"Composed by code: the {metric.upper()} savings of options {ids} add because they are in different components ({', '.join(sorted({c for s in comps for c in s}))})."}, None
    return None, f"no rule composes a {metric} gain"


def _uniq(seq: list[Any]) -> list[Any]:
    out: list[Any] = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def build_raw(parts: list[dict[str, Any]], gain: dict[str, Any], owned: list[str]) -> dict[str, Any]:
    comps = sorted({c for p in parts for c in p["scope"]["components"]}, key=lambda c: owned.index(c) if c in owned else 0)
    kind = "whole_design" if set(comps) == set(owned) else "modules"
    stages = _uniq([s for p in parts for s in p["touches_stages"]])
    ids = " + ".join(p["id"] for p in parts)
    lo_it = max(p["cost"]["iterations"]["low"] for p in parts)
    hi_it = min(8, sum(p["cost"]["iterations"]["high"] for p in parts))
    return {
        "id": "C", "title": _clip("Cumulative: " + " + ".join(p["title"] for p in parts), 300),
        "scope": {"kind": kind, "components": comps},
        "approach": _clip(f"Apply options {ids} together, in this order of the chain. " + " ".join(f"[{p['id']}] {_clip(p['approach'], 150)}" for p in parts), 690),
        "techniques": [t for t in _uniq([t for p in parts for t in p.get("techniques", [])]) if isinstance(t, str)][:12],
        "touches_stages": stages, "gain": gain,
        "cost": {"iterations": {"low": lo_it, "high": max(lo_it, hi_it)}, "note": "all the parts' build-and-check rounds, the high end summed"},
        "risk": {"gates": _uniq([_clip(g, 190) for p in parts for g in p["risk"]["gates"]])[:10],
                 "contract_change": any(p["risk"]["contract_change"] for p in parts),
                 "contract_note": _clip(" ".join(p["risk"].get("contract_note") or "" for p in parts), 390),
                 "needs_eqy": any(p["risk"]["needs_eqy"] for p in parts), "needs_board": any(p["risk"]["needs_board"] for p in parts),
                 "summary": _clip("Every part's risk applies and they can interact. " + " ".join(f"[{p['id']}] {_clip(p['risk']['summary'], 200)}" for p in parts), 690)},
        "interface_changes": _uniq([x for p in parts for x in p.get("interface_changes", [])]),
    }


def rank_key(o: dict[str, Any], order: dict[str, int]) -> tuple:
    """Lower sorts first: an earlier measured set of exactly these stages first, then higher composed mid-gain, then fewer components touched, then no owner approval needed, then the model's order of the parts."""
    return (0 if o["gain"]["basis"] == "measurement" else 1, -_mid(o["gain"]), len({c for c in o["stage_components"].values() if c}) or len(o["scope"]["components"]), 1 if o["risk"]["needs_owner_approval"] else 0,
            [order[i] for i in o["combined_from"]])


def combine(options: list[dict[str, Any]], analysis: dict[str, Any], project: Any, *, goal: str | None, pinned: list[str] | None = None, blind: bool = False,
            cap: int = MAX_COMBINED) -> dict[str, Any]:
    """Build the cumulative options from the model's valid single ``options``. Returns ``{"options": [...], "considered": n, "not_composable":
    [{"from": [ids], "reason"}], "dropped": [...]}``. The options returned carry ``origin: combiner``, ``combined_from`` and no ``n`` (the caller numbers them)."""
    owned = [c.name for c in (project.owned() if project else [])]
    singles = [o for o in options if o.get("origin", "model") == "model" and o["touches_stages"] is not None][:MAX_PARTS]
    order = {o["id"]: k for k, o in enumerate(singles)}
    built: list[dict[str, Any]] = []
    not_comp: list[dict[str, Any]] = []
    seen_sets = {frozenset(o["touches_stages"]) for o in options if o["touches_stages"]}
    considered = 0
    for size in range(2, len(singles) + 1):
        for parts in itertools.combinations(singles, size):
            considered += 1
            ids = [p["id"] for p in parts]
            why = conflict(list(parts))
            if why:
                not_comp.append({"from": ids, "reason": why})
                continue
            comps = sorted({c for p in parts for c in p["scope"]["components"]})
            g, why = compose_gain(list(parts), analysis, blind=blind, scope=comps)
            if g is None:
                not_comp.append({"from": ids, "reason": why})
                continue
            stages = {s for p in parts for s in p["touches_stages"]}
            if goal == "latency" and frozenset(stages) in seen_sets:
                not_comp.append({"from": ids, "reason": "the model already offered an option touching exactly these stages"})
                continue
            raw = build_raw(list(parts), g, owned)
            opt, probs = schema.check_single(raw, "C?", analysis, project, goal=goal, pinned=pinned, blind=blind)
            if opt is None:
                not_comp.append({"from": ids, "reason": "the combination fails the option checks: " + "; ".join(probs[:2])})
                continue
            opt.update(origin=ORIGIN, combined_from=ids)
            built.append(opt)
    # rank, then the best of each size; keep the smallest sizes and the largest when more sizes than the cap
    built.sort(key=lambda o: rank_key(o, order))
    by_size: dict[int, dict[str, Any]] = {}
    for o in built:
        by_size.setdefault(len(o["combined_from"]), o)
    sizes = sorted(by_size)
    if len(sizes) > cap:
        sizes = sizes[: cap - 1] + [sizes[-1]]
    chosen = [by_size[s] for s in sizes]
    for o in built:                    # fill any remaining room with the next best, whatever the size
        if len(chosen) >= cap:
            break
        if o not in chosen:
            chosen.append(o)
    chosen.sort(key=lambda o: (len(o["combined_from"]), rank_key(o, order)))
    left_out = [{"from": o["combined_from"], "reason": f"valid, but not in the {cap} best (ranked below the best of its size or beyond the cap)"} for o in built if o not in chosen]
    return {"options": chosen, "considered": considered, "not_composable": not_comp + left_out, "version": COMBINER_VERSION, "cap": cap}


def apply(rec: dict[str, Any], analysis: dict[str, Any], project: Any, *, goal: str | None, pinned: list[str] | None = None, blind: bool = False) -> dict[str, Any]:
    """Replace the combiner's options in ``rec['options']`` by freshly built ones from the model's options, number everything and note the result in
    ``rec['combiner']``. Safe to call again after a ``--more`` or ``--edit`` (it strips the old combined options first)."""
    model_opts = [o for o in rec["options"] if o.get("origin", "model") != ORIGIN]
    for o in model_opts:
        o.setdefault("origin", "model")
    res = combine(model_opts, analysis, project, goal=goal, pinned=pinned, blind=blind)
    used = {o["id"] for o in model_opts}
    new = []
    for k, o in enumerate(res["options"], 1):
        cid = f"C{k}"
        while cid in used:
            cid += "x"
        used.add(cid)
        o["id"] = cid
        new.append(o)
    rec["options"] = model_opts + new
    for k, o in enumerate(rec["options"], 1):
        o["n"] = k
    rec["combiner"] = {"version": res["version"], "considered": res["considered"], "cap": res["cap"], "offered": [{"id": o["id"], "from": o["combined_from"]} for o in new],
                       "not_composable": res["not_composable"]}
    return rec
