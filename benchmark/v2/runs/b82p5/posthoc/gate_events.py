#!/usr/bin/env python3
"""82P5 Part B: the planted constants and the gate's events in the one live run, from the run directory (frozen worktree runs/<id>).

    python3 gate_events.py <run dir> > gate_events.json

Per stage-2 snapshot (one per visit, `snapshots.json` + `snap.git`): the shell DESIGN_ID default in the top module and R0_ID if present.
From `build/audit.jsonl`: every write of a DESIGN_ID / create_clock / period_ns line (visit order by time), and the `check` tool's
constants result. From the Claude Code transcripts of the RTL role: the lines in which the role quotes the constants finding.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

rd = Path(sys.argv[1])
out = {"run": rd.name, "snapshots": [], "writes": [], "check_tool_constants": [], "rtl_role_on_the_finding": {}}
g = ["git", f"--git-dir={rd / 'snap.git'}"]
for s in json.load(open(rd / "snapshots.json")):
    if s["stage"] != "rtl-design-creation":
        continue
    t = subprocess.run(g + ["grep", "-h", "-E", r"(DESIGN_ID|R0_ID) +=", s["commit"], "--", "*v2_e_udp_endpoint_top.sv"],
                       capture_output=True, text=True).stdout
    out["snapshots"].append({"key": s["key"], "top_parameters": [x.strip()[:120] for x in t.splitlines()]})
rows = [json.loads(x) for x in (rd / "v2_e_udp_endpoint/build/audit.jsonl").read_text().splitlines()]
for i, d in enumerate(rows):
    if d.get("tool") == "write_file":
        c = (d.get("arguments") or {}).get("content", "")
        h = re.findall(r"DESIGN_ID +=[^,\n]*|\.DESIGN_ID\s*\([^)]*\)|create_clock[^\n]*|period_ns:[^\n]*|design_id:[^\n]*", c)
        if h:
            out["writes"].append({"audit_row": i, "stage": d["stage"], "role": d["role"], "path": d["arguments"].get("path"), "lines": h[:4]})
for x in (rd / "trace.jsonl").read_text().splitlines():
    d = json.loads(x)
    if d.get("tool") == "check" and "CONST-" in json.dumps(d):
        o = d["result"]["output"]
        out["check_tool_constants"].append({"seq": d["seq"], "text": o[o.find("FAIL     constants"):][:900]})
for f in sorted((rd / "claude_code").glob("*_rtl_rtl-design-creation.jsonl")):
    last = [json.loads(x) for x in f.read_text().splitlines() if x.strip()][-1]
    out["rtl_role_on_the_finding"][f.name[:3]] = str(last.get("result"))[:700]
print(json.dumps(out, indent=1))
