#!/usr/bin/env python3
"""Brief 242: one agent run's record. python3 pilots/242/record_one.py <design> <k>   (the newest run dir whose design is b242_<design>_r<k>)."""
import json, re, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D, K = sys.argv[1], sys.argv[2]
tag = f"b242_{D}_r{K}"
run = sorted(p for p in (ROOT / "runs").glob("2026*") if (p / tag).is_dir())[-1]
des = run / tag
s = json.load(open(run / "summary.json")) if (run / "summary.json").is_file() else {"stop": "no summary.json: the run was killed at the wrapper limit (3300 s, exit 124)"}
out = ROOT / "pilots" / "242" / D / f"arm_run{K}"
out.mkdir(parents=True, exist_ok=True)
g = {}
gp = des / "build/base/gates.json"
if gp.is_file():
    gj = json.load(open(gp))
    g = {"pass": gj.get("pass"), "first_failed_stage": gj.get("first_failed_stage"),
         "failed": {st: [k for k, x in (v.get("gates") or {}).items() if x is False] for st, v in gj["stages"].items()}}
xdc = (des / "design.xdc").read_text() if (des / "design.xdc").is_file() else ""
kp = (des / "build/base/known_post.xdc").read_text() if (des / "build/base/known_post.xdc").is_file() else ""
cg = des / "build/base/clock_groups.json"
arch = (des / "architecture.yaml").read_text() if (des / "architecture.yaml").is_file() else ""
rec = {"run_id": run.name, "design": D, "k": int(K), "stop": s.get("stop"), "stop_detail": str(s.get("stop_detail"))[:300],
       "stages_visited": s.get("stages_visited"), "plan_cost_estimate_usd": s.get("plan_cost_estimate_usd"), "wall_s": s.get("wall_s"),
       "gates_last_build": g, "gates_last": str(s.get("gates_last"))[:600],
       "model_xdc_set_clock_groups": len(re.findall(r"(?m)^\s*set_clock_groups", xdc)),
       "model_xdc_datapath_only": len(re.findall(r"(?m)^\s*set_max_delay[^\n]*-datapath_only", xdc)),
       "flow_set_clock_groups": len(re.findall(r"(?m)^set_clock_groups", kp)), "flow_datapath_only": len(re.findall(r"(?m)^set_max_delay[^\n]*-datapath_only", kp)),
       "architecture_has_clock_relations": "clock_relations" in arch, "architecture_has_clock_muxes": "clock_muxes" in arch,
       "clock_group_plan": json.load(open(cg)) if cg.is_file() else None}
(out / "run_record.json").write_text(json.dumps(rec, indent=1) + "\n")
for f, dst in ((des / "design.xdc", "design.xdc"), (des / "build/base/known_post.xdc", "known_post.xdc"), (des / "architecture.yaml", "architecture.yaml"),
               (des / "build/base/gates.json", "gates.json"), (run / "summary.json", "summary.json")):
    if f.is_file():
        shutil.copy(f, out / dst)
print(json.dumps({k: v for k, v in rec.items() if k not in ("clock_group_plan", "gates_last")}, indent=1))
