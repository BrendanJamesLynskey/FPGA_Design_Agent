#!/usr/bin/env python3
"""82P6: rebuild the stage-2 evidence of the 82P4 B r2 and B r3 runs from their private archives, for the P1 replay.

    python3 benchmark/v2/runs/b82p6/posthoc/extract_replay_evidence.py <KB checkout>   (from the repo root)

For each run: the V2 verification checks as the gate recorded them (build/verif/verif_gates.json of the run, the last gate
evaluation) and every failed ``simulate`` result the RTL role saw (its transcript's tool results, 82P4 recorded no per-visit
gate evidence), in order. The output ``agent/tests/fixtures/b82p6_replay_evidence.json`` holds test names, assertion lines and
check values only (simulator and tool output, no prompt text); the run directory path is replaced by ``<run>``.
"""
import glob
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path

KB = Path(sys.argv[1])
RUNS = {"B_r2": "20261120-072336-553a", "B_r3": "20261120-104735-68eb"}
OUT = Path("agent/tests/fixtures/b82p6_replay_evidence.json")


def tool_results(path: str):
    for line in open(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") or {}
        c = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    t = b.get("content")
                    if isinstance(t, list):
                        t = " ".join(x.get("text", "") for x in t if isinstance(x, dict))
                    yield str(t or "")


out = {}
for tag, rid in RUNS.items():
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(KB / f"results_private/benchmark/v2/runs/b82p4/artifacts/{rid}/run_dir.tar.gz") as t:
            t.extractall(td, filter="data")
        root = Path(td) / rid
        v = json.loads((root / "v2_e_udp_endpoint/build/verif/verif_gates.json").read_text())
        sims = []
        for f in sorted(glob.glob(str(root / "claude_code/*_rtl_rtl-design-creation.jsonl"))):
            for t in tool_results(f):
                i = t.find("[first failure] ")
                if i >= 0:
                    sims.append(t[i:i + 1800].replace(str(root), "<run>"))
        sims = [re.sub(r"/home/[^\s\"\\]*", "<path>", s) for s in sims]
        out[tag] = {"run_id": rid, "verif": {"reached": v.get("reached"), "first_failed": v.get("first_failed"),
                                              "V2": v["stages"]["V2"]["checks"]},
                    "sim_failures": sims}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=1) + "\n")
print({k: len(v["sim_failures"]) for k, v in out.items()})
