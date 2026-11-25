#!/usr/bin/env python3
"""Post-hoc (not a pre-registered number): what the runs that were killed at 4 h (no summary.json) had reached, read from the frozen
tree's run directories: stage-2 visits, spec-test state, time in tools and roles, and the last audit line (run_vivado queueing).
    python3 killed_runs_state.py <runs dir of the frozen worktree> > killed_runs_state.json
"""
import json, sys, collections
from pathlib import Path
out = {}
for rd in sorted(Path(sys.argv[1]).iterdir()):
    des = rd / "v2_e_udp_endpoint"
    if not des.is_dir():
        continue
    ru = [json.loads(x) for x in (rd / "role_usage.jsonl").read_text().splitlines() if x.strip()]
    au = [json.loads(x) for x in (des / "build/audit.jsonl").read_text().splitlines() if x.strip()]
    sec = collections.defaultdict(float)
    for a in au:
        sec[a.get("tool")] += a.get("seconds") or 0
    st = {}
    f = des / "build/spectest/state.json"
    if f.is_file():
        s = json.loads(f.read_text())
        st = {k: s.get(k) for k in ("fired", "runs", "outcome", "passed", "caught_bug", "design_wrong", "bench_wrong")}
    out[rd.name] = {"has_summary": (rd / "summary.json").is_file(),
                    "stage2_max_visit": max([u["visit"] for u in ru if u["stage"] == "rtl-design-creation"] or [0]),
                    "role_minutes": round(sum(u["wall_s"] for u in ru) / 60), "tool_minutes": {k: round(v / 60) for k, v in sec.items() if v > 60},
                    "spec_test": st, "last_audit": (au[-1].get("tool"), (au[-1].get("result_summary") or "")[:160]) if au else None}
print(json.dumps(out, indent=1))
