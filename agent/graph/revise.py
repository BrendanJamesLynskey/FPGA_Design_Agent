"""The goal-revision plan (brief 159, review item F5): ``python -m agent revise <design-dir> --goal "latency<=10clk" [--retarget <part|board>]``.

``resume`` (brief 68, goal kinds of brief 149) picks an entry stage from the WORDS of a change request. ``revise`` takes the goals as
data (:mod:`agent.graph.goals`) and decides from the design's own evidence:

1. each new goal is compared with the design's committed measurements (the handover's ``measurements:``). A goal the fresh evidence
   already meets re-runs nothing (the evidence is kept and named); a goal it fails, or that no measurement can show, enters at its
   class's stage: area and latency 1, fmax and power 3 (a new constraint and a new build, as for ``resume``);
2. ``--retarget`` to a part (or a board's part) in the SAME device family enters at stage 3 (new package pins and constraints and a new
   build; the RTL and the architecture are kept and the build's utilisation and timing gates re-check them); to another family, or
   when a family is unknown, at stage 1 (the architecture plan, primitives and family advice differ);
3. what the handover already says is stale (changed files, stale records, another Vivado release, a build-ID change) is added by
   ``pickup.entry_stage`` exactly as for ``resume``; the entry is the earliest of all reasons;
4. the plan lists, for every stage, whether it is kept or re-run and why, the goal vector before and after (with a SHA-256 of each), and
   the stage count against a full re-run (stages 0 to 9).

Not built (stated, not hidden): per-stage input hashes (the stage keys of ``docs/design_environment.md``); evidence is kept by stage position and
by the handover's own freshness checks, and the one measured build is taken as evidence for a bound (a different seed or tool version can move
a LUT count). A run starts from the new entry through ``agent.graph.pickup`` and the typed goals are written into the RUN's copy of spec.yaml
(``goals:``); the source design is never edited by ``revise``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from agent.graph import goals as G
from agent.graph import pickup
from agent.graph.document import STAGE_NAMES
from flow import handover as H

#: entry stage of a goal class the evidence does not meet (brief 149's table)
STAGE_OF_GOAL_KIND = {"area": 1, "latency": 1, "fmax": 3, "power": 3}
#: a part number's prefix -> device family (the families whose advice differs: the family matrix of the knowledge bank)
FAMILIES = (("xc7a", "artix7"), ("xc7k", "kintex7"), ("xc7z", "zynq7000"), ("xc7s", "spartan7"), ("xc7v", "virtex7"),
            ("xczu", "zynq-ultrascale+"), ("xck26", "zynq-ultrascale+"), ("xck24", "zynq-ultrascale+"),
            ("xcau", "artix-ultrascale+"), ("xcku", "kintex-ultrascale"), ("xcvu", "virtex-ultrascale"))
FULL_RERUN_STAGES = len(STAGE_NAMES)
ROOT = Path(__file__).resolve().parents[2]


class ReviseError(Exception):
    """The request cannot be planned (a bad goal, an unknown part or board); the message says what to write instead."""


def family(part: str | None) -> str | None:
    p = (part or "").lower()
    return next((f for pre, f in FAMILIES if p.startswith(pre)), None)


def sha(goals: list[G.Goal]) -> str:
    return hashlib.sha256(json.dumps([g.as_dict() for g in goals], sort_keys=True).encode()).hexdigest()[:16]


def resolve_target(arg: str) -> dict[str, str | None]:
    """``--retarget``: a part number (``xc7a200tfbg484-1``) or a board directory name under ``boards/`` (its ``board.yaml`` part)."""
    a = arg.strip()
    if re.match(r"^x[a-z0-9]{3,}[a-z0-9]*-[a-z0-9]+", a.lower()):
        return {"part": a, "board": None}
    by = ROOT / "boards" / a / "board.yaml"
    if by.is_file():
        part = (yaml.safe_load(by.read_text()) or {}).get("part")
        if part:
            return {"part": str(part), "board": a}
    raise ReviseError(f"--retarget {arg!r}: not a part number (like xc7a200tfbg484-1) and not a board directory under boards/ with a part in its board.yaml")


def current_goals(ddir: Path) -> list[G.Goal]:
    sp = ddir / "spec.yaml"
    if not sp.is_file():
        return []
    try:
        return G.load(yaml.safe_load(sp.read_text()) or {})
    except (G.GoalError, yaml.YAMLError) as e:
        raise ReviseError(f"{H.rel(sp)}: {e}")


def _clock_mhz(ddir: Path, name: str | None) -> float | None:
    sp = ddir / "spec.yaml"
    try:
        spec = yaml.safe_load(sp.read_text()) if sp.is_file() else {}
    except yaml.YAMLError:
        return None
    for c in (spec or {}).get("clocks") or []:
        if c.get("freq_mhz") and name in (None, c.get("name")):
            return float(c["freq_mhz"])
    return None


def evidence(goal: G.Goal, h: dict, fresh: dict, ddir: Path) -> dict[str, Any]:
    """Does the committed evidence already meet ``goal``? {status: met|not_met|unknown, why, measurement, value}. A stale or missing
    measurement is ``unknown`` (never trusted); a bound the build was not timed at is not shown by it."""
    stale = {line.split(":", 1)[0] for line in fresh.get("stale") or []}
    ms = [m for m in h.get("measurements") or [] if isinstance(m, dict)]

    def unknown(why: str) -> dict[str, Any]:
        return {"status": "unknown", "why": why, "measurement": None, "value": None}

    if goal.kind == "latency":
        lat = [m for m in ms if m.get("category") == "latency"]
        if goal.name:
            pick = [m for m in lat if m.get("key") in (goal.name, goal.name + "_clocks")] or [m for m in lat if goal.name in str(m.get("key"))]
            if len(pick) != 1:
                return unknown(f"{len(pick)} measured latencies match the name {goal.name!r}: " + (", ".join(str(m['key']) for m in lat) or "none recorded"))
            m = pick[0]
        elif len(lat) == 1:
            m = lat[0]
        else:
            return unknown(f"{len(lat)} latencies are measured ({', '.join(str(m['key']) for m in lat) or 'none'}): name one, latency.<name>")
        if str(m.get("unit")) not in ("clocks", "clk"):
            return unknown(f"measurement {m.get('id')} is in {m.get('unit')}, not clocks")
        key = m["key"]
    elif goal.kind == "fmax":
        f = _clock_mhz(ddir, goal.name)
        wns = next((m for m in ms if m.get("key") == "wns_ns"), None)
        if f is None:
            return unknown("the design's clock frequency is not in spec.yaml, so the committed timing result cannot be read as an Fmax")
        if wns is None:
            return unknown("no worst-slack measurement in the handover")
        if wns["id"] in stale:
            return unknown(f"measurement {wns['id']} is stale")
        ok = goal.met_by(f) and float(wns["value"]) >= 0
        return {"status": "met" if ok else "not_met", "measurement": wns["id"], "value": {"built_at_mhz": f, "wns_ns": wns["value"]},
                "why": (f"the committed build met timing (WNS {wns['value']} ns) at {f:g} MHz" if ok else
                        f"the committed build was timed at {f:g} MHz (WNS {wns['value']} ns); it cannot show {goal.bound:g} MHz")}
    else:
        key = G.METRICS[goal.metric]["evidence_key"]
        pick = [m for m in ms if m.get("key") == key]
        if not pick:
            return unknown(f"no measurement with key {key} in the handover")
        m = pick[0]
    if m["id"] in stale:
        return unknown(f"measurement {m['id']} is stale")
    try:
        v = float(m["value"])
    except (TypeError, ValueError):
        return unknown(f"measurement {m['id']} has no number")
    ok = goal.met_by(v)
    return {"status": "met" if ok else "not_met", "measurement": m["id"], "value": v,
            "why": f"{m.get('what', key)}: {v:g} {m.get('unit', '')} ({str(m.get('conditions', 'no conditions recorded')).split(';')[0]}) "
                   f"{'meets' if ok else 'does not meet'} {goal.text()}"}


def _group_file_reasons(rs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """One line per stage for the "file changed since the handover" reasons (a worktree can have dozens), with the count and the first three."""
    pre = "file changed since the handover: "
    files: dict[int, list[str]] = {}
    out = []
    for s, w in rs:
        if w.startswith(pre):
            files.setdefault(s, []).append(w[len(pre):])
        else:
            out.append((s, w))
    for s, fs in sorted(files.items()):
        out.append((s, f"{len(fs)} file(s) changed or added since the handover, each a stage-{s} input (first: {', '.join(fs[:3])})"))
    return out


def plan(ddir: Path, ld: dict, new_goals: list[G.Goal], retarget: str | None = None) -> dict[str, Any]:
    """The revision plan for ``ddir`` (``ld`` = ``pickup.load(ddir)``)."""
    h, fresh = ld["handover"], ld["fresh"]
    if not new_goals and not retarget:
        raise ReviseError("nothing to revise: give --goal (for example lut<=700) or --retarget <part|board>")
    before = current_goals(ddir)
    after = G.merge(before, new_goals)
    changes: list[dict[str, Any]] = []
    for g in new_goals:
        old = next((x for x in before if x.key == g.key), None)
        row: dict[str, Any] = {"goal": g.text(), "kind": g.kind, "old": old.text() if old else None}
        if old is not None and old.as_dict() == g.as_dict():
            row.update(verdict="unchanged", stage=None, why="the same goal is already in spec.yaml")
        else:
            ev = evidence(g, h, fresh, ddir)
            met = ev["status"] == "met"
            row.update(verdict="met_by_evidence" if met else ev["status"], evidence=ev,
                       stage=None if met else STAGE_OF_GOAL_KIND[g.kind],
                       why=ev["why"] if met else (ev["why"] + f"; enter at stage {STAGE_OF_GOAL_KIND[g.kind]} ({STAGE_NAMES[STAGE_OF_GOAL_KIND[g.kind]]})"))
        changes.append(row)
    rt = None
    cur_part = (h.get("target") or {}).get("part")
    if retarget:
        tgt = resolve_target(retarget)
        same_part = bool(cur_part) and str(cur_part).lower() == tgt["part"].lower()
        fa, fb = family(cur_part), family(tgt["part"])
        if same_part and not tgt["board"]:
            rt = {"to": tgt, "from_part": cur_part, "verdict": "unchanged", "stage": None, "why": "the design already targets this part"}
        elif same_part:
            rt = {"to": tgt, "from_part": cur_part, "verdict": "same_part_new_board", "stage": 3,
                  "why": f"the same part on another board: new pins and constraints, a new build; RTL kept"}
        elif fa and fa == fb:
            rt = {"to": tgt, "from_part": cur_part, "verdict": "same_family", "stage": 3, "family": fa,
                  "why": f"{cur_part} -> {tgt['part']} is inside {fa}: new package pins and constraints and a new build (stage 3); the architecture and "
                         "RTL are kept, and the build's utilisation and timing gates re-check them"}
        else:
            rt = {"to": tgt, "from_part": cur_part, "verdict": "other_family" if fa and fb else "family_unknown", "stage": 1,
                  "family": [fa, fb],
                  "why": (f"{cur_part} ({fa}) -> {tgt['part']} ({fb}) is another family: " if fa and fb else
                          f"the family of {cur_part!r} or {tgt['part']!r} is not known to this table: ") +
                         "the architecture plan, the primitives and the family advice are redone (stage 1)"}
    stages = [(c["stage"], c["kind"], c["goal"]) for c in changes if c["stage"] is not None] + \
             ([(rt["stage"], "retarget", "--retarget " + retarget)] if rt and rt["stage"] is not None else [])
    goal_stage, goal_kind = (min(stages, key=lambda x: x[0])[:2] if stages else (None, None))
    other = pickup.entry_stage(h, fresh)                         # changed files, stale records, Vivado release, build ID, continuation
    reasons = [(s, f"goal change: {w}") for s, _k, w in stages] + _group_file_reasons(other["reasons"])
    stage = min([r[0] for r in reasons], default=pickup.DOC_ONLY)
    entry = {"stage": stage, "kind": goal_kind or other.get("kind"), "reasons": reasons, "notes": other.get("notes") or []}
    re_run = list(range(stage, FULL_RERUN_STAGES)) if stage < pickup.DOC_ONLY else []
    goal_only = list(range(goal_stage, FULL_RERUN_STAGES)) if goal_stage is not None else []
    return {"design": fresh.get("design") or H.rel(ddir), "goals_before": [g.as_dict() for g in before], "goals_after": [g.as_dict() for g in after],
            "goal_vector_sha": {"before": sha(before), "after": sha(after)}, "changes": changes, "retarget": rt,
            "goal_stage": goal_stage, "entry": {**entry, "reasons": [{"stage": s, "why": w} for s, w in reasons]},
            "stages": [{"stage": i, "name": STAGE_NAMES[i], "action": "re-run" if i in re_run else "kept"} for i in range(FULL_RERUN_STAGES)],
            "stages_rerun": len(re_run), "stages_rerun_by_the_goal_alone": len(goal_only), "full_rerun_stages": FULL_RERUN_STAGES,
            "evidence_kept": [STAGE_NAMES[i] for i in range(FULL_RERUN_STAGES) if i not in re_run],
            "_after": after}


def public(p: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in p.items() if not k.startswith("_")}


def write_goals(design: Path, goals: list[G.Goal], retarget: dict[str, Any] | None = None, old_part: str | None = None) -> list[str]:
    """Write ``goals`` into the RUN's copy of spec.yaml (comments and every other line kept); with a retarget, the part string is replaced in
    spec.yaml and build.yaml of the copy. Returns the files written."""
    sp = design / "spec.yaml"
    sp.write_text(G.set_block(sp.read_text(), goals))
    out: list[str] = []
    if retarget and old_part and retarget.get("part"):
        for f in ("spec.yaml", "build.yaml"):
            p = design / f
            if p.is_file() and old_part in (t := p.read_text()):
                p.write_text(re.sub(r"(?<![\w-])" + re.escape(old_part) + r"(?![\w-])", retarget["part"], t))
                out.append(f)
    return out if "spec.yaml" in out else ["spec.yaml"] + out


def add_parser(sub) -> None:
    p = sub.add_parser(
        "revise", help="brief 159: change a design's goals (typed, with numbers) or its part, and re-run only what the change makes stale",
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
        description=(
            "Revise a design with a handover (python -m agent revise designs/<name> --goal 'lut<=700' [--goal ...] [--retarget <part|board>] [--dry-run]).\n"
            "The plan compares each goal with the design's committed measurements. A goal the fresh evidence already meets re-runs nothing; one it\n"
            "fails (or no measurement can show) enters at its class's stage: area and latency 1, fmax and power 3. A retarget inside one device\n"
            "family enters at stage 3, to another family at stage 1. Whatever the handover already says is stale is added, as for resume.\n\n"
            "What you could guess wrong:\n"
            "  * a goal is <metric>[.<name>]<op><number><unit> with the direction fixed by the metric (lut, ff, bram, dsp, power, latency: <= or <;\n"
            "    fmax: >= or >). '=' is refused. fmax needs MHz or GHz, power W or mW, latency clk (or clocks, cycles): a bare number is an\n"
            "    error, nanoseconds are refused. latency.<name> and fmax.<clock> pick one; no name means the design's only measured latency or\n"
            "    its first clock.\n"
            "  * 'met by evidence' means one committed build's number meets the bound. It is not a promise for another seed or tool version, and\n"
            "    power is Vivado's vectorless estimate, not a board measurement. A stale measurement counts as no evidence. fmax is met only when the\n"
            "    committed build was timed at a clock at least that fast and met timing; the tool never extrapolates an Fmax from slack.\n"
            "  * a goal change alone never edits the source design. The goals go into the run's copy of spec.yaml (goals:). With nothing to re-run\n"
            "    the plan says so and writes nothing.\n"
            "  * stage 0 is not entered for a goal: the typed goals are not a behaviour change. A changed file or stale record the handover\n"
            "    reports can still pull the entry earlier (the reasons list says which); on a worktree with extra files that is common.\n"
            "  * a retarget runs the new part's constraints at stage 3 without a new architecture approval; the KB's family advice is read from the new\n"
            "    part. It has been planned in the dry runs only: no live retarget run has been made yet.\n"
            "  * --dry-run prints the plan and exits 0; a goal that cannot be read, or an unknown part, exits 2 with what to write instead."))
    p.add_argument("design", type=Path, help="a design directory with handover.yaml and AGENT.md (spec.md and spec.yaml to run it)")
    p.add_argument("--goal", action="append", default=[], metavar="GOAL",
                   help="a typed goal, repeatable: lut<=700, ff<=900, bram<=2, dsp<=0, fmax>=150MHz, power<=0.5W, latency<=22clk, latency.echo<=22clk")
    p.add_argument("--retarget", metavar="PART_OR_BOARD", help="a part number (xc7a200tfbg484-1) or a board directory under boards/")
    p.add_argument("--dry-run", action="store_true", help="print the plan and stop (no run, no files written)")
    p.add_argument("--source", default="agent revise --goal", help="the source recorded in each goal (default: %(default)s)")
