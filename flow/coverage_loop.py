#!/usr/bin/env python3
"""Coverage-directed stimulus at V3 (brief 218, part 1): read the holes, ask the tests role for sequences that reach them, rerun, stop.

What "today's V3" does: when a V3 check fails, the gate's text names the unhit bins, cover properties and lines, and the *next stage-2 visit*
(which also repeats lint, the simulation, the standards check and the first synthesis build) hands them to the tests role with everything
else that failed. A stage-2 visit is expensive and shared, and there are six of them.

What this adds, behind ``--coverage-loop on`` (off is today's behaviour): inside one gate evaluation, when V2 has passed and V3 fails only on
*evidence the tests can change* (functional bins, cover properties, line, toggle, mutation survivors), the harness runs rounds of

    holes -> one tests-role repair call with just the holes -> rerun the V3 evidence -> holes again

and stops on a **plateau** (no hole closed in ``PLATEAU_ROUNDS`` rounds in a row), on **convergence** (no holes) or on a **budget** (a round
limit, or the run's own meter). Every round is a line of ``build/verif/coverage_loop.jsonl`` with the holes closed, the holes that appeared and
what the round cost, so "bins closed per unit of usage" is a column and not a guess.

The code here is pure (no model, no simulator): hole parsing, the plateau rule, the round record and the brief the role is shown. The driver
takes its three side effects (the role call, the evidence rerun, the gate read) as functions, so it runs the same in a test and in a run.

Independence: the Verifier never reads the RTL (``agent/graph/roles.py``). The brief therefore shows a line or toggle hole as the gate already
does (file:line and the signal), and says what the spec and the model say about it; it never pastes RTL text.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

SCHEMA = "fpga-force/coverage-loop/v1"
LOG_REL = ("build", "verif", "coverage_loop.jsonl")
MAX_ROUNDS = 3             # rounds per gate evaluation
PLATEAU_ROUNDS = 2         # rounds in a row that close no hole: stop (the brief: "no new bins in two rounds")
BRIEF_LIMIT = 40           # holes named in one brief; the rest are counted

#: the V3 checks whose failure the tests role can change by writing more or different stimulus
TEST_OWNED = ("functional_bins_pct", "functional_bins_unhit", "cover_properties_pct", "cover_properties_unhit", "line_pct", "toggle_pct",
              "mutation_score_pct")
#: V3 checks that are not about stimulus (a loop cannot help them): seeds, failing seeds, waivers, CDC
NOT_STIMULUS = ("seeds_run", "all_seeds_pass", "waivers_without_reason")

KINDS = ("bin", "cover", "line", "toggle", "branch", "mutant")


# ---- holes ----------------------------------------------------------------------------------------------------------------------------
def _hole(kind: str, key: str, text: str) -> dict[str, str]:
    return {"kind": kind, "key": f"{kind}:{key}", "text": text}


def holes_of(verif: dict[str, Any] | None, mutation: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Every open hole of a V3 evaluation, as ``{kind, key, text}``, from the output of ``flow.verif_gates`` (``verif``) and the mutation
    result. ``key`` is stable between rounds, so two rounds can be compared. Waived items are not in the gate's lists, so not here."""
    out: list[dict[str, str]] = []
    v3 = (((verif or {}).get("stages") or {}).get("V3") or {}).get("checks") or {}
    for b in (v3.get("functional_bins_unhit") or {}).get("value") or []:
        out.append(_hole("bin", str(b), f"functional bin {b} was never hit"))
    for c in (v3.get("cover_properties_unhit") or {}).get("value") or []:
        out.append(_hole("cover", str(c), f"cover property {c} was never reached"))
    unhit = (verif or {}).get("code_coverage_unhit") or {}
    for kind in ("line", "toggle", "branch"):
        for g in unhit.get(kind) or []:
            what = {"line": "line never executed", "toggle": "signal bit never changed", "branch": "branch never taken"}[kind]
            out.append(_hole(kind, str(g), f"{what}: {g}"))
    mut = mutation if mutation is not None else (verif or {}).get("mutation")
    for t in (mut or {}).get("survivor_text") or []:
        out.append(_hole("mutant", str(t), f"mutant survived (no test failed): {t}"))
    for t in (mut or {}).get("timed_out_text") or []:
        out.append(_hole("mutant", "timeout:" + str(t), f"mutant timed out, counts as not killed: {t}"))
    return out


def stimulus_only(verif: dict[str, Any] | None) -> bool:
    """True when V2 is reached and the failed V3 checks are all ones the tests can change. A loop is useless when V3 fails on the seed count,
    a failing seed, a waiver without a reason or the CDC checks: those go to the ordinary repair visit."""
    if not verif or (verif.get("reached") or "") < "V2":
        return False
    checks = ((verif.get("stages") or {}).get("V3") or {}).get("checks") or {}
    failed = [k for k, c in checks.items() if not c.get("pass")]
    return bool(failed) and all(k in TEST_OWNED for k in failed)


def diff(before: list[dict[str, str]], after: list[dict[str, str]]) -> dict[str, list[str]]:
    """``closed`` (in ``before``, not in ``after``) and ``opened`` (new in ``after``), by key."""
    b, a = {h["key"] for h in before}, {h["key"] for h in after}
    return {"closed": sorted(b - a), "opened": sorted(a - b)}


def counts(holes: list[dict[str, str]]) -> dict[str, int]:
    return {k: sum(h["kind"] == k for h in holes) for k in KINDS if any(h["kind"] == k for h in holes)}


# ---- the stop rule ----------------------------------------------------------------------------------------------------------------------
def stop_reason(rounds: list[dict[str, Any]], max_rounds: int = MAX_ROUNDS, plateau: int = PLATEAU_ROUNDS) -> str | None:
    """Why the loop stops after ``rounds`` (the records so far), or None to go on. ``converged``: no hole left; ``plateau``: the last
    ``plateau`` rounds each closed nothing; ``rounds``: the round limit. Convergence is tested first, the limit last."""
    if rounds and not rounds[-1]["holes_after"]:
        return "converged"
    if len(rounds) >= plateau and all(not r["closed"] for r in rounds[-plateau:]):
        return "plateau"
    if len(rounds) >= max_rounds:
        return "rounds"
    return None


# ---- the brief the tests role is shown ------------------------------------------------------------------------------------------------
HOW = {
    "bin": "add a directed or constrained-random sequence that makes the bench's coverage model sample the bin (the bin's name says which "
           "cross to fill; the testplan names it)",
    "cover": "drive the design into the state the cover property describes; if the property can never be true, say so in the testplan "
             "waiver with the reason instead of leaving it",
    "line": "write a sequence that makes the spec's behaviour for this case happen (the signal named is in the design, which you cannot read: "
            "work from the spec and the model)",
    "toggle": "drive a stimulus that moves this signal's bits (wide values, both polarities, the extremes the spec allows)",
    "branch": "exercise the case the spec describes for the other branch",
    "mutant": "the design was changed here and every test still passed: add a check or a stimulus the changed behaviour would fail "
              "(compare the model's value with the design's, on a case the spec says matters)",
}


def brief(holes: list[dict[str, str]], round_no: int, limit: int = BRIEF_LIMIT, history: list[dict[str, Any]] | None = None) -> str:
    """The text added to the tests role's repair call (code, not a private prompt). Names the holes of this round, what each kind
    asks for, and what earlier rounds closed or did not."""
    lines = [f"COVERAGE ROUND {round_no}. V0 to V2 pass. The V3 evidence has {len(holes)} open hole(s); a run of the whole bench against the "
             f"design shows them below. Write stimulus (cocotb sequences in tests/ or verif/) that reaches them. Do not change the "
             f"assertions, the model or the testplan thresholds to make a hole go away; a waiver needs a reason a reviewer would accept."]
    by: dict[str, list[dict[str, str]]] = {}
    for h in holes:
        by.setdefault(h["kind"], []).append(h)
    shown = 0
    for kind in KINDS:
        hs = by.get(kind)
        if not hs:
            continue
        lines += ["", f"{kind} holes ({len(hs)}): {HOW[kind]}"]
        for h in hs:
            if shown >= limit:
                break
            lines.append(f"- {h['text']}")
            shown += 1
    if len(holes) > shown:
        lines.append(f"(+{len(holes) - shown} more: see build/verif/coverage_loop.jsonl and the gate's coverage_detail)")
    if history:
        lines += ["", "Earlier rounds: " + "; ".join(f"round {r['round']} closed {len(r['closed'])} and opened {len(r['opened'])}"
                                                    for r in history[-3:]) + ". A hole that survived them needs a different idea, not the same sequence."]
    return "\n".join(lines) + "\n"


# ---- the record -------------------------------------------------------------------------------------------------------------------------
def log_path(design: Path) -> Path:
    return design.joinpath(*LOG_REL)


def record_round(design: Path, rec: dict[str, Any]) -> None:
    p = log_path(design)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def read_log(design: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(l) for l in log_path(design).read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


# ---- the driver -------------------------------------------------------------------------------------------------------------------------
def run_loop(design: Path, *, read_holes: Callable[[], list[dict[str, str]]], ask_tests: Callable[[str, int], dict[str, Any]],
             rerun: Callable[[], None], max_rounds: int = MAX_ROUNDS, plateau: int = PLATEAU_ROUNDS,
             clock: Callable[[], float] = time.monotonic, spent: Callable[[], float] | None = None,
             halt: Callable[[], str | None] | None = None) -> dict[str, Any]:
    """Run rounds until the stop rule says stop. The three effects are passed in:

    * ``read_holes()``: the open holes now (the V3 evidence as it stands);
    * ``ask_tests(brief, round_no)``: one tests-role repair call; returns ``{"ok": bool, "files": [...], "error": str}`` (``ok`` False when the
      role could not run: a budget stop, which ends the loop with that reason);
    * ``rerun()``: the V3 evidence run again (Verilator coverage, then the mutation run);
    * ``halt()`` (optional): called after ``rerun``; a reason string ends the loop at once (the new stimulus broke V0 to V2: the ordinary repair
      visit owns that, not another round).

    ``spent()`` (optional) is the run's cumulative cost reading (tokens or dollars from the meter); a round records the difference. Returns the
    summary ``{rounds, stop, holes_start, holes_end, closed_total}``; each round is also appended to ``build/verif/coverage_loop.jsonl``."""
    holes = read_holes()
    start = holes
    rounds: list[dict[str, Any]] = []
    stop: str | None = None if holes else "converged"
    while stop is None:
        n = len(rounds) + 1
        t0, c0 = clock(), (spent() if spent else None)
        resp = ask_tests(brief(holes, n, history=rounds), n) or {}
        if not resp.get("ok", True):
            stop = "tests_role: " + str(resp.get("error") or "did not run")[:200]
            rec = {"schema": SCHEMA, "round": n, "holes_before": [h["key"] for h in holes], "holes_after": [h["key"] for h in holes],
                   "closed": [], "opened": [], "wall_s": round(clock() - t0, 1), "usage": None, "files": [], "stop": stop}
            record_round(design, rec)
            rounds.append(rec)
            break
        rerun()
        why = halt() if halt else None
        if why:
            stop = why
            rec = {"schema": SCHEMA, "round": n, "holes_before": [h["key"] for h in holes], "holes_after": [h["key"] for h in holes], "closed": [],
                   "opened": [], "wall_s": round(clock() - t0, 1), "usage": (round(spent() - c0, 4) if spent and c0 is not None else None),
                   "files": list(resp.get("files") or []), "stop": stop}
            record_round(design, rec)
            rounds.append(rec)
            break
        after = read_holes()
        d = diff(holes, after)
        rec = {"schema": SCHEMA, "round": n, "holes_before": [h["key"] for h in holes], "holes_after": [h["key"] for h in after],
               "closed": d["closed"], "opened": d["opened"], "counts_before": counts(holes), "counts_after": counts(after),
               "wall_s": round(clock() - t0, 1), "usage": (round(spent() - c0, 4) if spent and c0 is not None else None),
               "files": list(resp.get("files") or [])}
        holes = after
        stop = stop_reason(rounds + [rec], max_rounds, plateau)
        rec["stop"] = stop
        record_round(design, rec)
        rounds.append(rec)
    closed_total = len({k for r in rounds for k in r["closed"]} & {h["key"] for h in start})
    return {"schema": SCHEMA, "rounds": len(rounds), "stop": stop, "holes_start": len(start), "holes_end": len(holes),
            "closed_of_start": closed_total, "opened_total": sum(len(r["opened"]) for r in rounds),
            "usage": (round(sum(r["usage"] or 0 for r in rounds), 4) if spent else None)}


def summary_line(s: dict[str, Any]) -> str:
    return (f"coverage loop: {s['rounds']} round(s), stopped on {s['stop']}; holes {s['holes_start']} -> {s['holes_end']} "
            f"({s['closed_of_start']} of the first {s['holes_start']} closed, {s['opened_total']} opened)")


_ROUND_NUM = re.compile(r"^COVERAGE ROUND (\d+)\b")


def round_of_brief(text: str) -> int | None:
    m = _ROUND_NUM.match(text)
    return int(m.group(1)) if m else None
