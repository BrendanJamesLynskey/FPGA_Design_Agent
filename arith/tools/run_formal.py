#!/usr/bin/env python3
"""Formal jobs of one arithmetic function (arith brief 139a): SymbiYosys with the slang front end, on the fv top of arith/<function>/formal/.

    python3 -m arith.tools.run_formal adder [--only name,name] [--json PATH]

arith/<function>/formal/jobs.yaml lists jobs: ``name``, ``top``, ``params`` (top-level parameters, -G), ``mode`` (prove: k-induction, or bmc), ``depth``,
``engine``, ``sources`` and ``claim`` (what a pass means, in words: "proved for all inputs" or "bounded to N clocks from reset"). A job with
``mutant`` (a name in verif/mutants.yaml) runs on a copy of the RTL with that one change and EXPECTS a failure (the counterexample): it shows the
check can fail. A constant table written as a case statement becomes a read-only memory with initial contents; in a k-induction step the memory would be free (initial values constrain only the first step), so every
job script maps memories to logic (``memory_map``) and the table stays a constant (brief 139d; the earlier functions have no tables, so it changes nothing for them). Writes verif/results/formal.json (status, seconds, tool versions). Needs the OSS CAD Suite (FDA_OSS_CAD, ~/.local/opt/oss-cad-suite or PATH)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from arith.tools import arith_common as ac


def sby_text(job: dict, files: list[Path], top: str) -> str:
    gs = " ".join(f"-G {k}={v}" for k, v in (job.get("params") or {}).items())
    mode = job.get("mode", "prove")
    return "\n".join([
        "[options]", f"mode {mode}", f"depth {job['depth']}", "",
        "[engines]", f"smtbmc {job.get('engine', 'boolector')}", "",
        "[script]", "plugin -i slang", f"read_slang --top {top} {gs} " + " ".join(f.name for f in files), f"prep -top {top}", "memory_map", "",
        "[files]", *[str(f) for f in files], ""])


def run_job(fn: str, job: dict, work: Path, mutants: dict) -> dict:
    d = ac.ARITH / fn
    spec = ac.load_spec(fn)
    files = []
    jd = work / job["name"]
    jd.mkdir(parents=True)
    for s in job["sources"]:
        src = (d / s).read_text()
        if job.get("mutant"):
            m = mutants[job["mutant"]]
            if ((d / m["file"]) if m.get("file") else (d / spec["variants"][m["variant"]]["file"])).resolve() == (d / s).resolve():
                assert src.count(m["old"]) == 1, f"mutant {job['mutant']} does not apply once"
                src = src.replace(m["old"], m["new"])
        (jd / "src").mkdir(exist_ok=True)
        (jd / "src" / Path(s).name).write_text(src)
        files.append(jd / "src" / Path(s).name)
    (jd / "job.sby").write_text(sby_text(job, files, job["top"]))
    sby = ac.tool("sby")
    env = {**os.environ, "PATH": ac.oss_bin() + os.pathsep + os.environ["PATH"]}
    t0 = time.time()
    r = subprocess.run([sby, "-f", "-d", str(jd / "out"), str(jd / "job.sby")], capture_output=True, text=True, env=env, timeout=int(job.get("timeout", 900)))
    secs = round(time.time() - t0, 1)
    out = r.stdout + r.stderr
    m = re.search(r"DONE \((PASS|FAIL|UNKNOWN|ERROR), rc=(\d+)\)", out)
    status = m.group(1) if m else "ERROR"
    expect_fail = bool(job.get("mutant"))
    ok = (status == "FAIL") if expect_fail else (status == "PASS")
    failing = sorted(set(re.findall(r"Assert failed in [\w.]+: (\S+)", out)))
    return {"name": job["name"], "top": job["top"], "params": job.get("params") or {}, "mode": job.get("mode", "prove"), "depth": job["depth"],
            "engine": job.get("engine", "boolector"), "claim": job["claim"], "mutant": job.get("mutant"), "expected": "FAIL" if expect_fail else "PASS",
            "status": status, "ok": ok, "seconds": secs, "failed_assertions": failing[:6], "tail": "" if ok else out[-500:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("function")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    fn = a.function
    d = ac.ARITH / fn
    jobs = yaml.safe_load((d / "formal" / "jobs.yaml").read_text())["jobs"]
    if a.only:
        keep = set(a.only.split(","))
        jobs = [j for j in jobs if j["name"] in keep]
    mutants = {m["name"]: m for m in yaml.safe_load((d / "verif" / "mutants.yaml").read_text())["mutants"]}
    work = Path(tempfile.mkdtemp(prefix=f"arith_formal_{fn}_", dir=ac.ROOT / "build" if (ac.ROOT / "build").is_dir() else None))
    res = []
    for j in jobs:
        r = run_job(fn, j, work, mutants)
        res.append(r)
        print(f"{'ok ' if r['ok'] else 'BAD'} {r['name']:34s} expected {r['expected']} got {r['status']} in {r['seconds']} s  {r['claim']}")
    ver = subprocess.run([ac.tool("yosys"), "-V"], capture_output=True, text=True, env={**os.environ, "PATH": ac.oss_bin() + os.pathsep + os.environ["PATH"]}).stdout.strip()
    out = {"function": fn, "tool": ver, "jobs": len(res), "ok": sum(r["ok"] for r in res), "results": res}
    outp = Path(a.json) if a.json else d / "verif" / "results" / "formal.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=1) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"{out['ok']} of {out['jobs']} jobs as expected -> {outp}")
    return 0 if out["ok"] == out["jobs"] else 1


if __name__ == "__main__":
    sys.exit(main())
