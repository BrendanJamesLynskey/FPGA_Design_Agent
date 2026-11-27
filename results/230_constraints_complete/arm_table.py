"""Brief 230: graded outcomes per run from agent run records (run_record.json), for 224's arm 2 (control) and this brief's arm.
Usage: python arm_table.py <out.json> <runs_dir> [<run id> ...]   (all runs of the directory when no id is given)"""
import json
import sys
from pathlib import Path

out, runs = Path(sys.argv[1]), Path(sys.argv[2])
ids = sys.argv[3:] or sorted(p.name for p in runs.iterdir() if (p / "run_record.json").is_file())
rows = []
for rid in ids:
    rr = json.loads((runs / rid / "run_record.json").read_text())
    sv = rr.get("stage_visits") or []
    visits: dict[str, int] = {}
    seen = set()
    for st, v, *_ in sv:
        if (st, v) not in seen:
            seen.add((st, v))
            visits[st] = visits.get(st, 0) + 1
    rows.append({"run": rid, "design": rr.get("design"), "reached_stage": rr.get("reached_stage"), "outcome": rr.get("outcome"),
                 "stage_visits": visits, "constraints_visits": visits.get("constraints", 0), "real_usd": rr.get("real_usd"),
                 "summary_stop": str(rr.get("summary_stop"))[:160], "bitstream_built": rr.get("bitstream_built"), "agent_sha": rr.get("agent_sha")})
out.write_text(json.dumps(rows, indent=1) + "\n")
for r in rows:
    print(r["run"], r["design"], r["reached_stage"], r["constraints_visits"], r["real_usd"], r["outcome"], r["summary_stop"][:70])
