#!/usr/bin/env python3
"""Brief 82P7, part 1 step 1: where each run's wall time went, per stage-2 visit, from the 82P6 records and run directories.

    python3 time_table.py --records <b82p6 records dir> --runs <runs dir> --out <dir>      # writes time_table.json and time_table.md

Sources (facts only): ``records/*.json`` (run id, wall), ``<run>/<design>/build/audit.jsonl`` (every tool call: time, role, seconds,
arguments), ``<run>/role_usage.jsonl`` (role wall time per stage and visit), ``<run>/claude_code_calls.jsonl`` (the spec-test role).
An audit call with role ``None`` is a gate evaluation made by the graph; a call with role ``rtl`` is the role's own tool call (its time
is inside that role's wall time). Stage-2 visits are the groups of audit events of the stage that start at a role call after a gate call, or at the lint call that opens a gate evaluation.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

STAGE2 = "rtl-design-creation"


def load(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() else []


def visits_of(audit: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    cur: list[dict] = []
    seen_gate = False
    for e in audit:
        if "tool" not in e or e.get("stage") != STAGE2:
            continue
        gate = e.get("role") is None
        if cur and seen_gate and (not gate or e["tool"] == "lint"):     # a role call after a gate, or a gate's first call (lint)
            out.append(cur)
            cur, seen_gate = [], False
        cur.append(e)
        seen_gate = seen_gate or gate
    if cur:
        out.append(cur)
    return out


def classify(e: dict) -> str:
    gate = e.get("role") is None
    tool, args = e["tool"], e.get("arguments") or {}
    if tool == "simulate":
        sim = args.get("sim", "auto")
        if not gate:
            return "role_simulate"
        if args.get("coverage"):
            return "gate_v3_coverage"
        return "gate_icarus_crosscheck" if sim == "icarus" else "gate_verilator"
    if tool == "build":
        return "gate_synth_calls" if gate else "role_other_tools"
    return "gate_other_tools" if gate else "role_other_tools"


def run_row(rec: dict, runs: Path) -> dict:
    rd = runs / rec["run_id"]
    design = next(p for p in rd.iterdir() if (p / "build" / "audit.jsonl").is_file())
    audit = load(design / "build" / "audit.jsonl")
    usage = load(rd / "role_usage.jsonl")
    calls = load(rd / "claude_code_calls.jsonl")
    vs = visits_of(audit)
    role_by_visit = defaultdict(float)
    for u in usage:
        if u["stage"] == STAGE2:
            role_by_visit[int(u["visit"])] += u["wall_s"]
    rows = []
    for i, ev in enumerate(vs, 1):
        agg: dict[str, float] = defaultdict(float)
        n_to = 0
        for e in ev:
            agg[classify(e)] += e.get("seconds") or 0
            if e["tool"] == "simulate" and "timed out" in str(e.get("result_summary")):
                n_to += 1
        synth = [e for e in ev if e["tool"] == "build" and e.get("role") is None]
        span = (synth[-1]["t"] - synth[0]["t"] + (synth[-1].get("seconds") or 0)) if synth else 0.0
        agg["gate_synth_wait_span"] = span      # polling for the Vivado slot is sleep time between audit calls, so the span is the cost
        rows.append({"visit": i, "role_s": round(role_by_visit.get(i, 0.0), 1), "sim_timeouts": n_to,
                     **{k: round(v, 1) for k, v in agg.items()}})
    spec_s = sum(c["wall_s"] for c in calls if c.get("role") == "spectest")
    role_total = sum(u["wall_s"] for u in usage)
    role_s2 = sum(role_by_visit.values())
    tot = {k: round(sum(r.get(k, 0.0) for r in rows), 1) for k in
           ("role_simulate", "gate_verilator", "gate_icarus_crosscheck", "gate_v3_coverage", "gate_synth_calls", "gate_synth_wait_span",
            "gate_other_tools", "role_other_tools")}
    tot["sim_timeouts"] = sum(r["sim_timeouts"] for r in rows)
    accounted = (role_total + tot["gate_verilator"] + tot["gate_icarus_crosscheck"] + tot["gate_v3_coverage"]
                 + max(tot["gate_synth_wait_span"], tot["gate_synth_calls"]) + tot["gate_other_tools"] + spec_s)
    wall = rec["wall_s"]
    return {"run": rec["run_id"][-4:], "arm": rec["arm"], "r": rec["repeat"], "wall_s": wall, "killed": bool(rec.get("hard_limit")),
            "hidden": f"{rec['score']['tests_passed']}/{rec['score']['tests']}", "stage2_visits": len(vs),
            "role_s_all": round(role_total, 1), "role_s_stage2": round(role_s2, 1), "spectest_role_s": round(spec_s, 1), **tot,
            "other_s": round(wall - accounted, 1), "per_visit": rows}


def md(rows: list[dict]) -> str:
    m = lambda s: f"{s / 60:.0f}"
    o = ["# 82P6 wall-time breakdown (minutes of the run's wall time)", "",
         "Role = all role calls (their own `simulate` calls are inside it, shown separately); Verilator, Icarus, V3 cov = the graph's gate",
         "simulations; synth = the synthesis gate (span of its calls, which includes waiting for the Vivado slot); other = the rest",
         "(spec-test benches, contract, standards, harness, startup).", "",
         "| Run | Wall | Hidden | S2 visits | Role | of which role's own sim | Spec-test role | Gate Verilator | Gate Icarus | Icarus time-outs | V3 cov | Synth gate | Other tools | Other |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        o.append(f"| {r['arm']} r{r['r']} {r['run']} | {m(r['wall_s'])}{' killed' if r['killed'] else ''} | {r['hidden']} | {r['stage2_visits']} | "
                 f"{m(r['role_s_all'])} | {m(r['role_simulate'])} | {m(r['spectest_role_s'])} | {m(r['gate_verilator'])} | "
                 f"{m(r['gate_icarus_crosscheck'])} | {r['sim_timeouts']} | {m(r['gate_v3_coverage'])} | "
                 f"{m(max(r['gate_synth_wait_span'], r['gate_synth_calls']))} | {m(r['gate_other_tools'])} | {m(r['other_s'])} |")
    tw = sum(r["wall_s"] for r in rows)
    sh = lambda k: sum(r[k] for r in rows) / tw * 100
    o += ["", f"Pooled over {len(rows)} runs ({tw / 3600:.1f} h): role {sh('role_s_all'):.0f} %, gate Verilator {sh('gate_verilator'):.0f} %, "
          f"gate Icarus {sh('gate_icarus_crosscheck'):.0f} %, V3 cov {sh('gate_v3_coverage'):.0f} %, spec-test role {sh('spectest_role_s'):.0f} %.", "",
          "## Per stage-2 visit (minutes)", "", "| Run | Visit | Role | Role's own sim | Gate Verilator | Gate Icarus | Icarus time-outs | V3 cov | Synth span |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        for v in r["per_visit"]:
            o.append(f"| {r['arm']} r{r['r']} | {v['visit']} | {m(v['role_s'])} | {m(v.get('role_simulate', 0))} | {m(v.get('gate_verilator', 0))} | "
                     f"{m(v.get('gate_icarus_crosscheck', 0))} | {v['sim_timeouts']} | {m(v.get('gate_v3_coverage', 0))} | {m(v.get('gate_synth_wait_span', 0))} |")
    return "\n".join(o) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    recs = [json.loads(p.read_text()) for p in sorted(Path(a.records).glob("*.json")) if "_attempt1" not in p.name]
    recs.sort(key=lambda r: (r["repeat"], r["arm"]))
    rows = [run_row(r, Path(a.runs)) for r in recs]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "time_table.json").write_text(json.dumps(rows, indent=1))
    (out / "time_table.md").write_text(md(rows))
    print(md(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
