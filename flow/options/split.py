"""The per-stage splitter (brief 104B): code turns a bundled option into per-stage options, each bounded by the stage file.

Brief 104's generator, and 104A's combiner behind it, showed that the model offers bundles (one option that changes several stages at once, for example ``decide`` together
with ``fs_start`` and ``mac_preamble``) and never ``decide`` alone, so the combiner had no ``decide`` to add to ``cross_go``. This module derives the missing single-stage
options from the bundles, **from the stage file**, and gives them to the combiner. It reads only the analysis and the model's checked options, never a back-test's truth.

For each model option that touches two or more stages of a latency chain:

* **units**: the stages are grouped into units that must stay together (see *coupling* below); every other stage is a unit of its own.
* **per-unit bound, computed by code**: ``high`` is the checker's own ceiling for that unit's stages (the stage file's removable clocks, or the stage's clocks in a blind run,
  capped at the chain's total), and never more than the bundle itself claimed; ``low`` is what the bundle's own ``low`` forces on this unit after the other units give
  their most (``max(0, bundle low - the others' high ends)``), usually 0. A unit whose bound is 0 is dropped with the reason recorded.
* **scope**: only the components the unit's stages live in (from the stage file); only the interface changes of those components are carried over.
* **provenance**: ``origin: splitter``, ``split_from`` (the bundle's id) and ``split_bundle_gain`` (the bundle's range, which the combiner uses so that parts of one bundle
  never add up to more than the bundle claimed).
* **validated like any option**: each part is built as a raw option and passed through ``schema.check_single``; a part that fails is dropped with the reason.

Coupling (never split across it). Two stages stay in one unit when any of these holds, and the reason is recorded:

1. **the stage file says so**: a stage record may carry ``coupled_with: [stage ids]`` (read by ``flow/latency``; absent from the files of today's designs, so this rule never fires
   for them and is covered by a planted test);
2. **one interface, several stages**: the bundle declares an interface change on a component that holds two or more of the bundle's stages. One change on one port cannot be
   attributed to one of them, so they are one unit;
3. **an interface change that belongs to no stage**: the bundle declares an interface change on a component none of its stages live in (or on a component the stage file does not
   know). It cannot be given to any part, so the bundle is **not split at all**.

A bundle with one unit left is not split; the reason is recorded. Only latency options are split: a slack (``wns_ns``) gain does not divide, and no rule here divides a LUT or FF gain.
The result of every bundle, split or not, is recorded under ``rec["splitter"]``.
"""

from __future__ import annotations

import re
from typing import Any

from flow.options import schema

SPLITTER_VERSION = "1"
ORIGIN = "splitter"
MAX_PARTS = 8          # parts offered in all; chosen in the model's order of bundles, then the stage file's chain order


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _is_bundle(o: dict[str, Any]) -> bool:
    return o.get("origin", "model") == "model" and (o.get("gain") or {}).get("metric") == "latency_clocks" and len(o.get("touches_stages") or []) >= 2


class _UF:
    def __init__(self, items: list[str]) -> None:
        self.p = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.p[self.find(a)] = self.find(b)


def units_of(bundle: dict[str, Any], stage_by_id: dict[str, dict[str, Any]]) -> tuple[list[list[str]] | None, list[dict[str, Any]], str | None]:
    """``(units, coupled, why_not)``: the groups of the bundle's stages that stay together (in the stage file's chain order), the couplings found (``{stages, rule, why}``),
    or ``None`` units and the reason when the bundle cannot be split at all."""
    chain = list(stage_by_id)
    stages = sorted(dict.fromkeys(bundle["touches_stages"]), key=lambda s: chain.index(s) if s in chain else len(chain))
    unknown = [s for s in stages if s not in stage_by_id or not stage_by_id[s].get("component")]
    if unknown:
        return None, [], f"stage(s) {', '.join(unknown)} have no component in the stage file, so no scope can be given to a part"
    uf = _UF(stages)
    coupled: list[dict[str, Any]] = []
    for s in stages:                                            # rule 1: the stage file marks the coupling
        for t in stage_by_id[s].get("coupled_with") or []:
            if t in uf.p and t != s and uf.find(s) != uf.find(t):
                uf.union(s, t)
                coupled.append({"stages": sorted([s, t]), "rule": "stage_file", "why": f"the stage file marks {s} as coupled with {t}"})
    by_comp: dict[str, list[str]] = {}
    for s in stages:
        by_comp.setdefault(stage_by_id[s]["component"], []).append(s)
    for ic in bundle.get("interface_changes") or []:             # rules 2 and 3
        c = ic["component"]
        mine = by_comp.get(c, [])
        if not mine:
            return None, coupled, (f"the interface change on {c}{'.' + ic['port'] if ic.get('port') else ''} belongs to none of the bundle's stages ({', '.join(stages)}), so no part could carry it: "
                                   "it may be what ties the stages together")
        if len(mine) >= 2:
            for t in mine[1:]:
                if uf.find(mine[0]) != uf.find(t):
                    uf.union(mine[0], t)
            coupled.append({"stages": sorted(mine), "rule": "shared_interface", "why": f"one interface change on {c}{'.' + ic['port'] if ic.get('port') else ''} spans stages {', '.join(mine)}, which live in the same component"})
    groups: dict[str, list[str]] = {}
    for s in stages:
        groups.setdefault(uf.find(s), []).append(s)
    return list(groups.values()), coupled, None


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.;])\s+", text) if x.strip()]


def _mentions(sentence: str, words: list[str]) -> bool:
    return any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(w) + r"(?![A-Za-z0-9_])", sentence, re.I) for w in words if w)


def _part_raw(bundle: dict[str, Any], unit: list[str], gain: dict[str, Any], stage_by_id: dict[str, dict[str, Any]], owned: list[str], blind: bool, facts: dict[str, Any]) -> dict[str, Any]:
    comps = sorted({stage_by_id[s]["component"] for s in unit}, key=lambda c: owned.index(c) if c in owned else 0)
    kind = "whole_design" if set(comps) == set(owned) else "modules"
    words = list(unit) + comps
    mine = [x for x in _sentences(bundle["approach"]) if _mentions(x, words)]
    detail = []
    for s in unit:
        st = stage_by_id[s]
        detail.append(f"Stage {s} ({_clip(st['name'], 80)})" + ("" if blind else f", technique {st.get('technique')}") + f"; the stage file's risk of removing it: {_clip(st.get('risk_of_removing') or 'not stated', 160)}")
    approach = _clip(f"Part of option {bundle['id']}, split out by code (the model's description of the whole bundle: see {bundle['id']}). "
                     + (" ".join(mine) + " " if mine else "") + " ".join(detail), 690)
    techs = [] if blind else [t for t in dict.fromkeys(str(stage_by_id[s].get("technique")) for s in unit) if t and t != "none"]
    return {
        "id": "S", "title": _clip(f"Only {', '.join(unit)} (split from {bundle['id']}: {bundle['title']})", 300),
        "scope": {"kind": kind, "components": comps}, "approach": approach, "techniques": techs, "touches_stages": list(unit), "gain": gain,
        "cost": {"iterations": {"low": 1, "high": max(1, min(8, bundle["cost"]["iterations"]["high"]))}, "note": "one part of the bundle: its rounds are at most the bundle's"},
        "risk": {"gates": [_clip(g, 190) for g in bundle["risk"]["gates"]][:10], "contract_change": bool(bundle["risk"]["contract_change"] and not bundle["risk"].get("contract_flag_added_by_checker")),
                 "contract_note": _clip(bundle["risk"].get("contract_note") or "", 390), "needs_eqy": bundle["risk"]["needs_eqy"], "needs_board": bundle["risk"]["needs_board"],
                 "summary": _clip(f"The risk of the bundle {bundle['id']} is carried over, not re-assessed for this part: " + bundle["risk"]["summary"], 690)},
        "interface_changes": [x for x in (bundle.get("interface_changes") or []) if x["component"] in comps],
    }


def split_one(bundle: dict[str, Any], analysis: dict[str, Any], project: Any, *, goal: str | None, pinned: list[str] | None = None, blind: bool = False) -> dict[str, Any]:
    """The parts of one bundle: ``{"bundle", "parts": [checked options, provisional id "S?"], "units", "coupled", "dropped": [{stages, reason}], "not_split": reason or None}``."""
    stage_by_id = {s["id"]: s for s in ((analysis.get("latency") or {}).get("stages") or [])}
    facts = analysis["facts"]
    owned = [c.name for c in (project.owned() if project else [])]
    res: dict[str, Any] = {"bundle": bundle["id"], "parts": [], "units": [], "coupled": [], "dropped": [], "not_split": None}
    units, coupled, why = units_of(bundle, stage_by_id)
    res["coupled"] = coupled
    if units is None:
        res["not_split"] = why
        return res
    res["units"] = units
    if len(units) < 2:
        res["not_split"] = "every stage of the bundle is coupled with another: " + "; ".join(c["why"] for c in coupled)
        return res
    g = bundle["gain"]
    comps_of = lambda u: sorted({stage_by_id[s]["component"] for s in u})      # noqa: E731
    raw_caps = [schema.ceiling("latency_clocks", u, comps_of(u), analysis, blind=blind) for u in units]
    caps = [min(c if c is not None else 0.0, g["high"]) for c, _ in raw_caps]
    for k, u in enumerate(units):
        cap_why = raw_caps[k][1]
        if caps[k] <= 0:
            res["dropped"].append({"stages": u, "reason": (f"no gain can be backed: {cap_why}" if not raw_caps[k][0] else f"the bundle {bundle['id']} claims no gain (high {g['high']:g})")})
            continue
        low = max(0.0, g["low"] - sum(c for j, c in enumerate(caps) if j != k))
        low = min(low, caps[k])
        basis = "guess" if g["basis"] == "guess" else "model"
        cites = [] if basis == "guess" else [f for s in u for f in (f"stage.{s}.clocks",) + (() if blind else (f"stage.{s}.removable",)) if f in facts]
        note = _clip(f"Derived by code from option {bundle['id']} (range {g['low']:g} to {g['high']:g} clocks over stages {', '.join(bundle['touches_stages'])}). High end {caps[k]:g}: "
                     f"the least of {cap_why} and the bundle's own high end. Low end {low:g}: the bundle's low end less the most the other parts can give. Not a prediction for this part alone.", 480)
        raw = _part_raw(bundle, u, {"metric": "latency_clocks", "low": low, "high": caps[k], "basis": basis, "cites": cites, "basis_note": note}, stage_by_id, owned, blind, facts)
        opt, probs = schema.check_single(raw, "S?", analysis, project, goal=goal, pinned=pinned, blind=blind)
        if opt is None:
            res["dropped"].append({"stages": u, "reason": "the part fails the option checks: " + "; ".join(probs[:2])})
            continue
        opt.update(origin=ORIGIN, split_from=bundle["id"], split_bundle_gain=[g["low"], g["high"]])
        res["parts"].append(opt)
    if not res["parts"]:
        res["not_split"] = "no part could be backed (" + "; ".join(f"{', '.join(d['stages'])}: {d['reason']}" for d in res["dropped"][:3]) + ")"
    return res


def split(options: list[dict[str, Any]], analysis: dict[str, Any], project: Any, *, goal: str | None, pinned: list[str] | None = None, blind: bool = False,
          cap: int = MAX_PARTS) -> dict[str, Any]:
    """Split every bundle among the model's valid ``options``. Returns ``{"parts": [options with provisional ids], "split": [bundle ids that gave parts], "report": [one
    entry per bundle], "version"}``. A part whose stage set a model option or an earlier part already offers is skipped (the model's own option wins). Only latency requests are split."""
    out: dict[str, Any] = {"parts": [], "split": [], "report": [], "version": SPLITTER_VERSION, "cap": cap}
    if goal != "latency" or not (analysis.get("latency") or {}).get("stages"):
        return out
    offered = {frozenset(o["touches_stages"]) for o in options if o.get("origin", "model") == "model" and o["touches_stages"]}
    seen: set[frozenset[str]] = set()
    for b in options:
        if not _is_bundle(b):
            continue
        r = split_one(b, analysis, project, goal=goal, pinned=pinned, blind=blind)
        kept, skipped = [], []
        for p in r["parts"]:
            key = frozenset(p["touches_stages"])
            if key in offered:
                skipped.append({"stages": p["touches_stages"], "reason": "the model already offers exactly this stage set as its own option"})
            elif key in seen:
                skipped.append({"stages": p["touches_stages"], "reason": "an earlier bundle already gave a part for exactly this stage set"})
            elif len(out["parts"]) + len(kept) >= cap:
                skipped.append({"stages": p["touches_stages"], "reason": f"more than {cap} parts: the later ones are not offered"})
            else:
                seen.add(key)
                kept.append(p)
        out["parts"] += kept
        if r["parts"]:
            out["split"].append(b["id"])
        out["report"].append({"bundle": b["id"], "stages": b["touches_stages"], "units": r["units"], "coupled": r["coupled"], "not_split": r["not_split"],
                              "parts": [{"stages": p["touches_stages"], "gain": [p["gain"]["low"], p["gain"]["high"]]} for p in kept], "dropped": r["dropped"] + skipped})
    return out
