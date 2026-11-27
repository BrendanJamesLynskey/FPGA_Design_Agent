"""Brief 230, records first (no new runs): how many stage visits in the recorded agent runs failed on
``post_synth_no_unconstrained_endpoints``, and which of the endpoints in each failing report the new tools would have written
(known_pre.xdc / known_post.xdc) or flagged before synthesis (FDA-CON-14/15) or left to the model.

Usage: python scan_records.py <out_dir> <worktree-root> [<worktree-root> ...]   (a run lives at <root>/runs/<id>/<design>/)
A run is read from its trace.jsonl (stage visits) and build/tool_results/NNN_gates.json (gate output of each gates call); the
console event with the matching step number gives the time, which puts the call inside a stage visit. Duplicated records (the
same run copied into several worktrees) are counted once, by run id.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
from flow import known_constraints as KC  # noqa: E402

GATE = "post_synth_no_unconstrained_endpoints"
CLAUSE = re.compile(r"(register pins with no clock|unconstrained internal endpoints|input ports with no input delay|output ports with no output delay)\s*\((\d+)\):\s*([^;]*)")


def visits(run: Path):
    ev = [json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines() if line.strip()]
    start: dict[tuple[int, int], float] = {}
    out = []
    steps = {}
    for e in ev:
        if e["event"] == "console":
            steps[e["step"].split("_")[0]] = e["t"]
        elif e["event"] == "stage_start":
            start[(e["n"], e["visit"])] = e["t"]
        elif e["event"] == "stage_end" and (e.get("n"), e.get("visit")) in start:
            out.append({"n": e["n"], "visit": e["visit"], "t0": start[(e["n"], e["visit"])], "t1": e["t"], "passed": e.get("passed")})
    return out, steps


def gate_results(design: Path):
    rows = []
    for f in sorted((design / "build" / "tool_results").glob("*_gates.json")):
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        out = str(d.get("output", ""))
        if not out.lstrip().startswith(("STALE", "gates:")):
            continue
        rows.append((f.name.split("_")[0], out))
    return rows


def classify_endpoint(kind: str, name: str, ctx: "KC.Ctx", jtag_heads: set[str], usr_heads: set[str]) -> str:
    head = name.split("/")[0]
    base = re.sub(r"\[[^\]]*\]$", "", name)
    if kind in ("register pins with no clock", "unconstrained internal endpoints"):
        if head in usr_heads:
            return "written: usr_cclk clock (known_pre.xdc)"
        if head in jtag_heads:
            return "written: jtag_tck clock (known_pre.xdc)"
        return "model: no tool knows this clock source"
    if kind == "output ports with no output delay":
        if ctx.board_slow(base):
            return "written: placeholder delay + false path (known_post.xdc)"
        return "flagged before synthesis: FDA-CON-14 with the line to add"
    if ctx.board_slow(base):
        return "written: placeholder delay + false path (known_post.xdc)"
    return "flagged before synthesis: FDA-CON-14 with the line to add"


def main() -> int:
    out_dir = Path(sys.argv[1])
    roots = [Path(r) for r in sys.argv[2:]]
    seen: dict[str, tuple[Path, Path]] = {}
    for root in roots:
        for rec in sorted((root / "runs").glob("*/")):
            ds = [d for d in rec.iterdir() if d.is_dir() and (d / "build" / "tool_results").is_dir()]
            if ds and rec.name not in seen:
                seen[rec.name] = (root, ds[0])
    rows, per_run, no_trace = [], [], []
    tot_visits = tot_fail = 0
    cats: dict[str, int] = {}
    for rid, (root, design) in sorted(seen.items()):
        try:
            ctx = KC.Ctx(design, root)
        except Exception:
            ctx = None
        jt = {p.split("/")[0] for _, p in ctx.instances_of(["BSCANE2"])} if ctx else set()
        us = {p.split("/")[0] for _, p in ctx.instances_of(["USR_ACCESSE2"])} if ctx else set()
        gates = gate_results(design)
        if not (root / "runs" / rid / "trace.jsonl").is_file():
            # an older run (the 209 pilot) has no trace: count gates calls that failed the gate, not stage visits
            bad = [(n, o) for n, o in gates if f"FAIL {GATE}" in o]
            tally: dict[str, int] = {}
            for _, out in bad:
                m = re.search(r"check_timing: (.*)", out)
                for kind, count, names in CLAUSE.findall(m.group(1) if m else ""):
                    shown = [x.strip() for x in names.split(",") if x.strip() and "more" not in x]
                    more = re.search(r"\.\.\. (\d+) more", names)
                    t2: dict[str, int] = {}
                    for nme in shown:
                        c = classify_endpoint(kind, nme, ctx, jt, us) if ctx else "unclassified"
                        t2[c] = t2.get(c, 0) + 1
                    if more and shown:
                        c = classify_endpoint(kind, shown[0], ctx, jt, us) if ctx else "unclassified"
                        t2[c] = t2.get(c, 0) + int(more.group(1))
                    for c, k in t2.items():
                        tally[c] = tally.get(c, 0) + k
            no_trace.append({"run": rid, "design": design.name, "gates_calls": len(gates), "gates_calls_failing_the_gate": len(bad), "endpoint_classes": tally,
                             "all_written_or_flagged": not any(c.startswith(("model", "unclassified")) for c in tally)})
            continue
        vs, steps = visits(root / "runs" / rid)
        n_fail = 0
        for v in vs:
            inside = [(n, o) for n, o in gates if n in steps and v["t0"] <= steps[n] <= v["t1"]]
            if not inside:
                continue
            tot_visits += 1
            bad = [(n, o) for n, o in inside if f"FAIL {GATE}" in o]
            last_bad = bool(inside) and f"FAIL {GATE}" in inside[-1][1] and v["passed"] is False
            if not bad:
                continue
            n_fail += 1
            tot_fail += 1
            out = bad[-1][1]
            m = re.search(r"check_timing: (.*)", out)
            line = m.group(1) if m else ""
            clauses = CLAUSE.findall(line)
            row = {"run": rid, "design": design.name, "stage": v["n"], "visit": v["visit"], "failed_visit": v["passed"] is False,
                   "last_gate_call_failed": last_bad, "clauses": []}
            for kind, count, names in clauses:
                shown = [x.strip() for x in names.split(",") if x.strip() and "more" not in x]
                tally: dict[str, int] = {}
                for nme in shown:
                    c = classify_endpoint(kind, nme, ctx, jt, us) if ctx else "unclassified"
                    tally[c] = tally.get(c, 0) + 1
                more = re.search(r"\.\.\. (\d+) more", names)
                if more and shown:      # the report lists the first 40 names only; the rest are assumed to follow the first name's class
                    first = classify_endpoint(kind, shown[0], ctx, jt, us) if ctx else "unclassified"
                    tally[first] = tally.get(first, 0) + int(more.group(1))
                for c, k in tally.items():
                    cats[c] = cats.get(c, 0) + k
                row["clauses"].append({"kind": kind, "count": int(count), "classes": tally})
            row["fully_written_or_flagged"] = all(not c.startswith(("model", "unclassified")) for cl in row["clauses"] for c in cl["classes"])
            row["fully_written_by_tools"] = all(c.startswith("written") for cl in row["clauses"] for c in cl["classes"])
            rows.append(row)
        per_run.append({"run": rid, "design": design.name, "visits_with_gates": sum(1 for v in vs if any(n in steps and v['t0'] <= steps[n] <= v['t1'] for n, _ in gates)), "visits_failing_gate": n_fail})
    res = {"gate": GATE, "runs_with_build_results": len(seen), "stage_visits_with_a_gates_call": tot_visits, "stage_visits_failing_the_gate": tot_fail,
           "failing_visits_fully_written_by_tools": sum(1 for r in rows if r["fully_written_by_tools"]),
           "failing_visits_fully_written_or_flagged": sum(1 for r in rows if r["fully_written_or_flagged"]),
           "endpoint_classes_total": cats, "per_run": per_run, "runs_without_trace_gates_calls": no_trace, "failing_visits": rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records_scan.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("failing_visits", "per_run")}, indent=1))
    print(len(per_run), "runs with a trace")
    for r in per_run:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
