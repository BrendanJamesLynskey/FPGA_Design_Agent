"""Brief 214: cost routing by stage, and k-way attempts when a stage is stuck. Both are off by default (``--routing off``, ``--kway 0``).

**The routing table** (:data:`ROUTING_TABLE`) says which tier of model a sub-agent call uses, by role, stage and *kind of visit*. The tiers
are :data:`TIERS`: ``standard`` is today's model for the role (whatever the model table resolves; never changed by this module), ``cheap``
and ``strong`` are other Anthropic models on the ``claude_code`` endpoint kind. With ``--routing off`` every call is ``standard``: the
table is documentation only. With ``--routing on`` a call takes its row's tier, and **escalation** applies on top: when the same
failure has been seen on two visits of a stage, the next visit of that stage uses the ``strong`` tier whatever the row says, until the failure
changes or the stage passes. Every call records the tier, the reason and the model it used (``role_usage.jsonl``) and every change from
``standard`` is also a ``route`` event in ``routing_events.jsonl``.

Only the ``claude_code`` kind is routed: its tiers are plain model names. A role on a chat endpoint (Deep Agents over OpenRouter or the
API) keeps its table model and the call records ``routing: skipped (kind ...)``. Opus is never reachable through the API kind or OpenRouter
(owner rule); here ``strong`` is Opus only on ``claude_code`` (the Max plan), exactly as the ``cvdp`` role profile already does.

**k-way attempts** (:func:`select_candidate`): when a stage has failed on two visits, the third visit runs k independent attempts at the
stage's work, each from the same starting files (a snapshot of the design taken before the first attempt, restored before each one; the
attempts run one after another, each in a clean copy of that snapshot, so one attempt cannot see another's edits), evaluates each
with the stage's own gates, keeps the best and logs every candidate (``kway.jsonl``). The selector prefers a verdict the Designer did not
write: a failing independent check (the fresh-stimulus regrade, the independent spec-only bench) ranks a candidate
below, a passing one above; only then the number of gates passed, then the fewest findings, then the lowest LUT count. A selection
decided by the Designer's own gates alone is labelled so (brief 226: own-check selection gained 1.3 points where an independent check
gained 10.8).

Pure functions and small file helpers, so CI tests them with recorded results and no model.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

ROUTING_MODES = ("off", "on")

#: tier -> the claude_code settings it stands for. ``None``: leave the role's resolved spec as it is (today's behaviour).
TIERS: dict[str, dict[str, Any] | None] = {
    "standard": None,
    "cheap": {"model": "claude-haiku-5-5", "effort": "low"},
    "strong": {"model": "claude-opus-5-5", "effort": "medium"},
}

#: Visit kinds, from what the visit has to do. ``write``: a fresh write of the role's files. ``repair``: a repair of an owned failure.
#: ``repair_lint``: a repair whose every failure is a lint or design-standards finding (mechanical: a syntax, port or naming fix).
KINDS = ("write", "repair", "repair_lint")

#: (role, stage name or "*", kind or "*", tier, why). First match wins; no match is ``standard``. Active only with ``--routing on``.
#: This is the proposal the brief 214 measurement tests, not a recommendation: the defaults stay ``standard`` until the numbers say otherwise.
ROUTING_TABLE: tuple[tuple[str, str, str, str, str], ...] = (
    ("rtl", "rtl-design-creation", "repair_lint", "cheap",
     "a lint or design-standards repair is a mechanical edit the finding names; a repeat escalates to strong (below)"),
    ("rtl", "rtl-design-creation", "repair", "standard", "a simulation or verification mismatch needs the model that reads the spec best"),
    ("rtl", "rtl-design-creation", "write", "standard", "the first write of the RTL"),
    ("rtl", "board-and-device-planning", "*", "standard", "architecture: the Designer role as configured (a strong tier is measured by escalation only)"),
    ("model", "*", "*", "standard", "the blind golden model: a spec reading, kept on the configured model"),
    ("tests", "*", "*", "standard", "the Verifier: kept on the configured model"),
    ("clarify", "*", "*", "standard", "the Clarifier: a spec reading, kept on the configured model"),
)
ESCALATE_AFTER = 2           # the same failure on this many visits of a stage: the next visit is strong
KWAY_AT_VISIT = 3            # the visit (counted from 1) on which k attempts run: after two failed visits
KWAY_ROUNDS = 1              # k-way rounds per stage per run
KWAY_STAGES = (2,)           # the stages that may run k attempts: the stage-2 gates are cheap (lint, simulate, standards; no Vivado)

_LINT_TAGS = ("[lint]", "[design standards]")


def visit_kind(role: str, reasons: list[str] | None, repair: bool) -> str:
    """The kind of this call from its failure texts (``stage2_plan``'s reasons, each starting ``[lint]``, ``[design standards]``, ...)."""
    if not repair:
        return "write"
    rs = [r for r in (reasons or []) if r]
    if rs and all(r.lstrip().startswith(_LINT_TAGS) for r in rs):
        return "repair_lint"
    return "repair"


def table_tier(role: str, stage: str, kind: str, table: tuple = ROUTING_TABLE) -> tuple[str, str]:
    """The tier and the row's reason for a call. The first row that matches the role, stage and kind wins."""
    for r, s, k, tier, why in table:
        if r == role and s in ("*", stage) and k in ("*", kind):
            return tier, why
    return "standard", "no row"


def failure_signature(fails: list[str] | None, sig: str | None = None, gates: list[str] | None = None) -> str:
    """A signature of a stage's failure. Stage 2 already has one (``state['sig']``: the owners and failing gates); it is used when given. Otherwise
    (brief 246, the follow-up of 214) the failing GATE NAMES, sorted, when the stage recorded them: the same gates failing again is the same failure
    however the gate's text or its numbers changed (214 measured the text-based form never repeating on a bounced stage-1 loop). With neither, the
    failure text with numbers, hex values and spacing ignored."""
    if sig:
        return str(sig)
    if gates:
        return "gates:" + "|".join(sorted(set(str(g) for g in gates)))
    text = " | ".join(str(f) for f in (fails or []))
    text = re.sub(r"0x[0-9a-fA-F]+|\d+", "#", text)
    return re.sub(r"\s+", " ", text).strip()[:300]


class FailureStreak:
    """Per stage: how many consecutive visits began with the same failure. ``see(n, sig)`` is called once at the start of each visit of stage
    ``n`` with the signature of the failure that brought the run there ("" for a first visit); the stage's streak is the count of the
    latest signature's consecutive equal entries."""

    def __init__(self) -> None:
        self.hist: dict[int, list[str]] = {}

    def see(self, n: int, sig: str) -> int:
        h = self.hist.setdefault(int(n), [])
        h.append(sig)
        return self.streak(n)

    def streak(self, n: int) -> int:
        h = self.hist.get(int(n)) or []
        if not h or not h[-1]:
            return 0
        k = 0
        for s in reversed(h):
            if s != h[-1]:
                break
            k += 1
        return k

    def failed_visits(self, n: int) -> int:
        """Visits of stage ``n`` so far that began from a failure (every visit but a first one that began clean)."""
        return sum(1 for s in (self.hist.get(int(n)) or []) if s)


def route(spec: dict[str, Any], role: str, stage: str, kind: str, streak: int, kind_of_endpoint: str) -> dict[str, Any]:
    """The routed call: ``{spec, tier, reason, escalated, changed, skipped}``. ``spec`` is the role's resolved ``{harness, model, effort}``."""
    tier, why = table_tier(role, stage, kind)
    escalated = streak >= ESCALATE_AFTER
    if escalated:
        tier, why = "strong", f"the same failure on {streak} consecutive visits of this stage"
    out = {"tier": tier, "reason": why, "escalated": escalated, "kind": kind, "streak": streak, "base_model": spec.get("model"), "base_effort": spec.get("effort")}
    if kind_of_endpoint != "claude_code":
        return {**out, "spec": dict(spec), "changed": False, "skipped": f"kind {kind_of_endpoint}"}
    t = TIERS[tier]
    if t is None or (t["model"] == spec.get("model") and t.get("effort") == spec.get("effort")):
        return {**out, "spec": dict(spec), "changed": False, "skipped": None}
    return {**out, "spec": {**spec, "model": t["model"], "effort": t["effort"]}, "changed": True, "skipped": None}


# --- k-way attempts ---------------------------------------------------------------------------------------------------------------------------

SKIP_DIRS = ("build", "__pycache__", ".pytest_cache")


def snapshot_design(design: Path, dest: Path) -> list[str]:
    """Copy the design directory to ``dest`` (never the build products or caches). Returns the relative file names."""
    design, dest = Path(design), Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    names: list[str] = []
    for p in sorted(design.rglob("*")):
        rel = p.relative_to(design)
        if p.is_file() and not any(x in SKIP_DIRS for x in rel.parts):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest / rel)
            names.append(str(rel))
    dest.mkdir(parents=True, exist_ok=True)
    return names


def restore_design(design: Path, src: Path) -> None:
    """Make the design directory hold exactly the snapshot's files again (a file an attempt created is removed; build products are left alone)."""
    design, src = Path(design), Path(src)
    for p in sorted(design.rglob("*"), reverse=True):
        rel = p.relative_to(design)
        if any(x in SKIP_DIRS for x in rel.parts):
            continue
        if p.is_file() or p.is_symlink():
            p.unlink()
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    for p in sorted(src.rglob("*")):
        if p.is_file():
            rel = p.relative_to(src)
            (design / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, design / rel)


def gates_passed(stage: Any, ev: dict[str, Any]) -> tuple[int, int]:
    """(gates passed, gates) of a stage on its evidence, each gate checked alone with the stage's own ``exit_check``."""
    import dataclasses

    from agent.graph.stages import exit_check
    total = len(stage.gates)
    ok = sum(1 for g in stage.gates if exit_check(dataclasses.replace(stage, gates=(g,)), ev)[0])
    return ok, total


def independent_verdict(ev: dict[str, Any]) -> tuple[str, str | None]:
    """The verdict of a check the Designer did not write, from the evidence: ``('pass'|'fail'|'none', which check)``. The checks: the
    fresh-stimulus regrade (brief 213) and the independent spec-only bench (08f), when they ran. A formal-proof verdict is not in the stage-2
    evidence yet; add it here when it is. A failing check wins over a passing one."""
    seen: list[tuple[str, str]] = []
    rg = (ev.get("regrade") or {}).get("status")
    if rg in ("pass", "fail"):
        seen.append((rg, "regrade"))
    st = ev.get("spec_test") or {}
    if st.get("verdict") in ("pass", "design_wrong"):
        seen.append(("pass" if st["verdict"] == "pass" else "fail", "spec_test"))
    for v, name in seen:
        if v == "fail":
            return "fail", name
    return (seen[0] if seen else ("none", None))


def luts_of(ev: dict[str, Any]) -> int | None:
    st = (((ev.get("gates_base") or {}).get("stages") or {}).get("post_synth") or {})
    v = (st.get("utilization") or {}).get("lut")
    return int(v) if isinstance(v, (int, float)) else None


def candidate_row(i: int, stage: Any, ev: dict[str, Any], fails: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ok, total = gates_passed(stage, ev)
    verdict, by = independent_verdict(ev)
    return {"candidate": i, "gates_passed": ok, "gates": total, "findings": len(fails or []), "luts": luts_of(ev), "independent": verdict,
            "independent_check": by, "passes": not fails, **(extra or {})}


_RANK = {"pass": 0, "none": 1, "fail": 2}


def select_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The index of the candidate kept, and why. Order: independent verdict (pass, none, fail), most gates passed, fewest findings, lowest LUTs (a
    candidate with no LUT count last), then the lowest candidate number. ``decided_by`` names the first criterion on which the best two differ;
    ``own_gates_only`` is true when no independent check ran on the best candidate (the choice then rests on the Designer's own bench and gates)."""
    if not rows:
        raise ValueError("no candidates")

    def key(r: dict[str, Any]) -> tuple:
        return (_RANK.get(r.get("independent", "none"), 1), -int(r.get("gates_passed", 0)), int(r.get("findings", 0)),
                r["luts"] if r.get("luts") is not None else 10 ** 12, int(r["candidate"]))
    ranked = sorted(rows, key=key)
    best = ranked[0]
    names = ("independent verdict", "gates passed", "findings", "LUTs", "candidate number")
    decided = "only candidate"
    if len(ranked) > 1:
        a, b = key(best), key(ranked[1])
        decided = next((names[j] for j in range(len(names)) if a[j] != b[j]), "tie")
    return {"candidate": best["candidate"], "decided_by": decided, "own_gates_only": best.get("independent", "none") == "none"}


def log_candidates(run_dir: Path, stage: str, visit: int, rows: list[dict[str, Any]], chosen: dict[str, Any]) -> None:
    """One line per candidate in ``kway.jsonl``, then one line for the choice. Never raises."""
    try:
        with (Path(run_dir) / "kway.jsonl").open("a") as f:
            for r in rows:
                f.write(json.dumps({"stage": stage, "visit": visit, **r}) + "\n")
            f.write(json.dumps({"stage": stage, "visit": visit, "chosen": chosen["candidate"], "decided_by": chosen["decided_by"],
                                "own_gates_only": chosen["own_gates_only"]}) + "\n")
    except OSError:
        pass
