#!/usr/bin/env python3
"""Run every SymbiYosys job of the reference controller (formal/ctl.sby) and record status and time: results/24_fsm/formal.json.
    source ~/.local/opt/formal-deb/env.sh; python3 results/24_fsm/run_formal.py        (one run each; times are wall clock on a loaded machine)"""
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

F = Path(__file__).resolve().parents[2] / "flow" / "tests" / "fixtures" / "fsm_discipline" / "formal"
tasks = re.findall(r"^(\w+)$", re.search(r"\[tasks\]\n(.*?)\n\n", (F / "ctl.sby").read_text(), re.S).group(1), re.M)
out = {}
with tempfile.TemporaryDirectory() as t:
    for k in tasks:
        t0 = time.time()
        p = subprocess.run(["sby", "-f", "-d", f"{t}/{k}", "ctl.sby", k], cwd=F, capture_output=True, text=True)
        st = next((l.split("DONE (")[1].split(",")[0] for l in p.stdout.splitlines() if "DONE (" in l), "ERROR")
        out[k] = {"status": st, "seconds": round(time.time() - t0, 2)}
        print(k, out[k])
Path(__file__).with_name("formal.json").write_text(json.dumps(out, indent=1) + "\n")
