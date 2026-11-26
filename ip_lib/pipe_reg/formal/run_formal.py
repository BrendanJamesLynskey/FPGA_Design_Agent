#!/usr/bin/env python3
"""run_formal.py (brief 151): the SymbiYosys jobs of pipe.sby (every mode, several N, proved by k-induction at W = 4) and the
planted faults of faults.yaml that a safety property can see, each run on a throw-away copy of the RTL.

    python3 ip_lib/pipe_reg/formal/run_formal.py --json results/b151/pipe_reg_formal.json
    python3 ip_lib/pipe_reg/formal/run_formal.py --only skid2        # one task

Needs sby, yosys and boolector (the OSS CAD Suite the repo's CI pins), found through FDA_OSS_CAD, ~/.local/opt/oss-cad-suite
or PATH. A fault whose bug is only slower, or never answers (a liveness or performance bug), cannot be refuted by a safety
property: it is listed as `not a safety bug` and not counted. The RTL itself is never edited."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ENTRY = HERE.parent
TASKS = ["fwd1", "fwd3", "skid1", "skid2", "skid3", "full1", "full2", "full3", "half1", "half2", "comb1", "comb2", "comb3", "wire0", "skid2c", "fwd3c", "full2c", "half2c", "comb2c", "wire0c"]
SVA_TASKS = ["sva_fwd3", "sva_skid1", "sva_skid2", "sva_full2", "sva_half2", "sva_comb2", "sva_wire0", "sva_fwd3c", "sva_skid2c", "sva_full2c", "sva_half2c", "sva_comb2c", "sva_wire0c"]
FAULT_TASK = {"comb": "comb2", "half": "half2", "skid": "skid2", "full": "full2", "fwd": "fwd3", "chain": "skid2", "wire": "wire0"}
NOT_SAFETY = {"fwd_valid_gated_by_ready": "tvalid depending on tready: caught by the bench (tready flipped within a clock), not by the port rules, because a gated valid never looks withdrawn",
              "comb_ready_ignores_take": "a throughput bug: the slice is correct but slower", "fwd_enable_needs_ready": "a liveness bug: a sink that waits for valid before ready waits for ever; no safety property is broken"}


def oss_bin() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    w = shutil.which("sby")
    return str(Path(w).parent) if w else ""


def run_sby(root: Path, task: str, out: Path, sbyfile: str = "pipe.sby") -> tuple[str, float]:
    env = dict(os.environ, PATH=oss_bin() + os.pathsep + os.environ["PATH"])
    t0 = time.time()
    subprocess.run(["sby", "-f", "-d", str(out), sbyfile, task], cwd=root / "formal", env=env, capture_output=True, text=True, timeout=3600)
    st = (out / "status").read_text().split()[0] if (out / "status").exists() else "ABSENT"
    return st, round(time.time() - t0, 1)


def main_for_test() -> int:
    """Run every fault job (and no proof) in a temporary folder; 0 when each is refuted (or listed as not a safety bug)."""
    sys.argv = [sys.argv[0], "--only", ",".join(m["name"] for m in yaml.safe_load((ENTRY / "faults.yaml").read_text())["faults"])]
    return main()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--no-faults", action="store_true")
    a = ap.parse_args()
    if not oss_bin():
        print("sby not found (set FDA_OSS_CAD)")
        return 2
    only = set(filter(None, a.only.split(",")))
    out = {"proofs": [], "faults": []}
    bad = 0
    with tempfile.TemporaryDirectory(prefix="b151formal_") as tmp:
        tmp = Path(tmp)
        for t in TASKS + SVA_TASKS:
            if only and t not in only:
                continue
            st, sec = run_sby(ENTRY, t, tmp / f"p_{t}", "pipe_sva.sby" if t.startswith("sva_") else "pipe.sby")
            exp = "PASS"
            ok = st == exp
            bad += not ok
            out["proofs"].append({"task": t, "status": st, "seconds": sec, "kind": "cover" if t.endswith("c") else ("k-induction proof of the AXI4-Stream rules as SVA (slang)" if t.startswith("sva_") else "k-induction proof")})
            print(f"{'ok ' if ok else 'BAD'} {t:8s} {st} {sec}s", flush=True)
        if not a.no_faults:
            fy = yaml.safe_load((ENTRY / "faults.yaml").read_text())["faults"]
            for m in fy:
                if only and m["name"] not in only:
                    continue
                if m["name"] in NOT_SAFETY:
                    out["faults"].append({"name": m["name"], "status": "not a safety bug", "why": NOT_SAFETY[m["name"]]})
                    print(f"-- {m['name']}: not a safety bug")
                    continue
                task = FAULT_TASK[m["name"].split("_")[0]]
                d = tmp / f"f_{m['name']}"
                shutil.copytree(ENTRY / "rtl", d / "rtl")
                shutil.copytree(HERE, d / "formal", ignore=shutil.ignore_patterns("__pycache__", "*.json"))
                src = d / "rtl" / m["file"]
                text = src.read_text()
                if text.count(m["old"]) != 1:
                    out["faults"].append({"name": m["name"], "status": "invalid"})
                    bad += 1
                    continue
                src.write_text(text.replace(m["old"], m["new"]))
                st, sec = run_sby(d, task, tmp / f"fo_{m['name']}")
                refuted = st == "FAIL"
                bad += not refuted
                out["faults"].append({"name": m["name"], "task": task, "status": "refuted" if refuted else f"NOT refuted ({st})", "seconds": sec})
                print(f"{'ok ' if refuted else 'BAD'} fault {m['name']:34s} {task:6s} {'refuted' if refuted else st} {sec}s", flush=True)
    out["date"] = time.strftime("%Y-%m-%d %H:%M")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
