"""Compare one run's result record with an example's reference runs (brief 195). Pure functions: no file, no model, no tool.

Three groups, kept apart because they promise different things:

``deterministic``  tool results for identical RTL (the bench's per-test verdicts, the Vivado build's resources, slack and build stamp; not the build ID, which covers the design's path and so differs between run directories). Compared field by field
                   **only against a reference whose RTL hash is the same**; a match is shown with the hash. A mismatch with the same RTL is a finding about the
                   tools or the setup, never about the model. When no reference has the same RTL the group says so and lists no verdict.
``varies``         what depends on the model's own sampling: the RTL, the number of repair loops, tokens, cost, wall time. Shown as the reference
                   minimum, median and maximum with the new value marked inside or outside; with few references "outside" means "not seen before", not "wrong".
``outcome``        what matters to the user: the hidden tests, the agent's own gates, and resources and slack against the reference spread (the spread of
                   the references, whatever their RTL).
"""

from __future__ import annotations

import statistics
from typing import Any

SCHEMA = "fda-example-result/1"

#: field -> (label, unit). Tool results that must repeat for identical RTL.
DETERMINISTIC = {
    "build_stamp": ("build stamp (hash of the sources and constraints)", ""), "lut": ("LUTs", ""), "ff": ("flip-flops", ""), "dsp": ("DSP slices", ""), "bram36": ("block RAM (36 Kb)", ""),
    "wns_ns": ("worst setup slack", "ns"), "whs_ns": ("worst hold slack", "ns"), "vivado_version": ("Vivado version", ""),
}
#: field -> (label, unit, how many digits). What varies with the model.
VARIES = {
    "rtl_lines": ("lines of RTL", "", 0), "repair_visits": ("repair loops (stage visits beyond one each)", "", 0), "agent_turns": ("agent turns", "", 0),
    "tokens": ("tokens (all calls)", "", 0), "cost_usd": ("cost", "USD", 2), "wall_s": ("wall time", "s", 0),
}
#: outcome fields compared against the spread of all references: resources and slack.
SPREAD = {"lut": ("LUTs", ""), "ff": ("flip-flops", ""), "dsp": ("DSP slices", ""), "bram36": ("block RAM (36 Kb)", ""), "wns_ns": ("worst setup slack", "ns"), "whs_ns": ("worst hold slack", "ns")}

LIMITS = (
    "Claude Code on a subscription takes no temperature and no seed, so the model's output cannot be pinned: the RTL, the number of repair loops, tokens, cost and wall time differ from run to run, and this page does not hide that.",
    "The model name is pinned (claude-sonnet-5-5) but the provider can update what that name serves; each result records the model id the calls reported, and a reference older than a provider update may be out of date.",
    "The cost is the plan's estimate (Claude Code reports a figure for the subscription), not a bill. Wall time includes waiting for a heavy slot only if the run waited inside it; it is recorded from the run's own start.",
    "Tool results repeat only for the same RTL: the same Vivado version and sources give the same build ID, resources and slack (docs/reproducibility.md); a different RTL gives different numbers and that is not a failure.",
)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def spread(vals: list[Any]) -> dict[str, Any] | None:
    xs = [x for x in (_num(v) for v in vals) if x is not None]
    if not xs:
        return None
    return {"min": min(xs), "median": statistics.median(xs), "max": max(xs), "n": len(xs)}


def _where(v: Any, sp: dict[str, Any] | None) -> str:
    x = _num(v)
    if x is None or sp is None:
        return "no value"
    if x < sp["min"]:
        return "below the reference range"
    if x > sp["max"]:
        return "above the reference range"
    return "inside the reference range"


def rtl_hash(r: dict[str, Any]) -> str | None:
    return (r.get("tool_results") or {}).get("rtl_sha256")


def compare(run: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    """The comparison of ``run`` with ``refs`` (each a result record, same schema). Never raises on a missing field: a field a record lacks is "no value"."""
    if run.get("schema") != SCHEMA:
        raise ValueError("not an example result record")
    tr, vr, oc = run.get("tool_results") or {}, run.get("varies") or {}, run.get("outcome") or {}
    out: dict[str, Any] = {"example": run.get("example"), "run_id": run.get("run_id"), "references": len(refs), "like_for_like": setup_diff(run, refs)}
    # deterministic: only against references with the same RTL hash
    h = rtl_hash(run)
    same = [r for r in refs if h and rtl_hash(r) == h]
    det: dict[str, Any] = {"rtl_sha256": h, "matching_references": [r.get("run_id") for r in same], "rows": []}
    if not h:
        det["note"] = "this run has no RTL hash (it did not produce RTL), so no tool result can be compared"
    elif not same:
        det["note"] = ("no reference run wrote the same RTL, so the tool results are not comparable and none is judged: the RTL text varies with the model (the group below), "
                       "and different RTL builds to different numbers. To see the tools repeat, run `python -m agent example tools <name>` (it re-runs the hidden bench on a stored reference RTL, with no model call).")
    for k, (label, unit) in DETERMINISTIC.items():
        row: dict[str, Any] = {"field": k, "label": label, "unit": unit, "run": tr.get(k)}
        if same:
            vals = [(r.get("run_id"), (r.get("tool_results") or {}).get(k)) for r in same]
            row["references"] = vals
            known = [v for _, v in vals if v is not None]
            row["verdict"] = ("no value" if tr.get(k) is None or not known else "match (same RTL hash)" if all(v == tr.get(k) for v in known)
                              else "MISMATCH with the same RTL: a finding about the tools or the setup, not the model")
        out_row_ok = True
        det["rows"].append(row)
        del out_row_ok
    tests = tr.get("bench_tests") or {}
    if same and tests:
        diffs = [t for t in tests if any(((r.get("tool_results") or {}).get("bench_tests") or {}).get(t) not in (None, tests[t]) for r in same)]
        det["rows"].append({"field": "bench_tests", "label": "hidden bench, test by test", "run": tests, "verdict": "match (same RTL hash)" if not diffs else f"MISMATCH with the same RTL in: {', '.join(diffs)}"})
    out["deterministic"] = det
    # varies
    var = []
    for k, (label, unit, nd) in VARIES.items():
        sp = spread([(r.get("varies") or {}).get(k) for r in refs])
        var.append({"field": k, "label": label, "unit": unit, "digits": nd, "run": vr.get(k), "reference": sp, "where": _where(vr.get(k), sp)})
    var.append({"field": "rtl_same", "label": "the RTL text", "run": h, "reference": sorted({rtl_hash(r) for r in refs if rtl_hash(r)}), "where": "identical to a reference" if same else "different from every reference (expected)"})
    out["varies"] = var
    # outcome
    ref_pass = [(r.get("outcome") or {}).get("hidden_pass") for r in refs]
    o: dict[str, Any] = {"hidden_pass": oc.get("hidden_pass"), "tests": f"{oc.get('tests_passed')}/{oc.get('tests_total')}",
                         "references_passed": f"{sum(1 for p in ref_pass if p is True)}/{len(ref_pass)}",
                         "internal_pass": oc.get("internal_pass"), "references_internal": f"{sum(1 for r in refs if (r.get('outcome') or {}).get('internal_pass') is True)}/{len(refs)}", "stop": oc.get("stop")}
    o["verdict"] = ("hidden tests pass, as in every reference" if oc.get("hidden_pass") is True and all(p is True for p in ref_pass)
                    else "hidden tests pass; not every reference did" if oc.get("hidden_pass") is True
                    else "hidden tests did NOT pass" + ("; no reference passed either" if not any(p is True for p in ref_pass) else f"; {sum(1 for p in ref_pass if p is True)} of {len(ref_pass)} references did"))
    rows = []
    for k, (label, unit) in SPREAD.items():
        sp = spread([(r.get("tool_results") or {}).get(k) for r in refs])
        rows.append({"field": k, "label": label, "unit": unit, "run": tr.get(k), "reference": sp, "where": _where(tr.get(k), sp)})
    o["spread"] = rows
    out["outcome"] = o
    out["limits"] = list(LIMITS)
    return out


def setup_diff(run: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Which parts of the pinned setup differ between the run and the references (the comparison is like for like only when none does)."""
    keys = ("claude_cli_version", "claude_cli_sha256", "cc_model", "oracle_cc_model", "vivado_version", "kb_commit", "prompts_manifest_sha256", "verif_level", "harness_arm", "stop_after", "cc_effort", "profile")
    s = run.get("setup") or {}
    diffs = {}
    for k in keys:
        seen = sorted({str((r.get("setup") or {}).get(k)) for r in refs})
        if seen and (len(seen) > 1 or str(s.get(k)) != seen[0]):
            diffs[k] = {"run": s.get(k), "references": seen}
    return {"same": not diffs and not s.get("unpinned_waived"), "differences": diffs, "waived": s.get("unpinned_waived") or []}


def reference_summary(refs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the example page shows before any run: the outcome counts and the spreads of the references."""
    n = len(refs)
    return {"n": n, "hidden_pass": f"{sum(1 for r in refs if (r.get('outcome') or {}).get('hidden_pass') is True)}/{n}",
            "internal_pass": f"{sum(1 for r in refs if (r.get('outcome') or {}).get('internal_pass') is True)}/{n}",
            "wall_s": spread([(r.get('varies') or {}).get('wall_s') for r in refs]), "cost_usd": spread([(r.get('varies') or {}).get('cost_usd') for r in refs]),
            "distinct_rtl": len({rtl_hash(r) for r in refs if rtl_hash(r)}), "build_ids": sorted({str((r.get('tool_results') or {}).get('build_id')) for r in refs if (r.get('tool_results') or {}).get('build_id')})}
