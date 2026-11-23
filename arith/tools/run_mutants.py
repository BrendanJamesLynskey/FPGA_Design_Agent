#!/usr/bin/env python3
"""Seeded-fault run for one arithmetic function (arith brief 139a): every mutant of arith/<function>/verif/mutants.yaml must be killed by the
function's cocotb bench; writes arith/<function>/verif/results/mutation.json.

    python3 -m arith.tools.run_mutants adder [--only a,b] [--jobs 2] [--json PATH]

Each mutant is one exact text replacement (old -> new, old occurring once) in a copy of its variant's RTL file; the real RTL is never touched. The bench
run per variant is spec.yaml's ``mutant_run`` (a list of mode and parameters: an exhaustive small point and a random larger one). Killed: a run fails.
Survived: every run passes. Invalid: the copy does not build (left out of the score). The unmutated variant must pass first. Sim only (Icarus)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from arith.tools import arith_common as ac


def one(fn: str, variant: str, rtl_dir: Path, root: Path, runs: list[dict]) -> tuple[str, str]:
    for i, r in enumerate(runs):
        p = subprocess.run([sys.executable, "-m", "arith.tools.run_point_cli", fn, variant, r["mode"], json.dumps(r.get("params", {})), "--rtl-dir", str(rtl_dir),
                            "--build-root", str(root / f"r{i}"), "--n", str(r.get("n", 1500))],
                           cwd=ac.ROOT, env={**__import__("os").environ, "PYTHONPATH": str(ac.ROOT)}, capture_output=True, text=True)
        if p.returncode == 3:
            return "invalid", (p.stdout + p.stderr)[-300:]
        if p.returncode == 1:
            return "killed", f"{r['mode']} {r.get('params', {})}"
    return "survived", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("function")
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    fn = a.function
    spec = ac.load_spec(fn)
    d = ac.ARITH / fn
    muts = yaml.safe_load((d / "verif" / "mutants.yaml").read_text())["mutants"]
    if a.only:
        keep = set(a.only.split(","))
        muts = [m for m in muts if m["name"] in keep]
    work = ac.ROOT / "build" / "arith_mut" / f"{fn}_{__import__('os').getpid()}"          # one folder per run, so two runs of one function (a pytest and a recording run) cannot clash
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    # the unmutated variants first
    for v, vd in spec["variants"].items():
        base = work / "baseline" / v
        base.mkdir(parents=True)
        shutil.copy(d / vd["file"], base)
        st, why = one(fn, v, base, base / "sim", vd["mutant_run"])
        if st != "survived":
            print("the unmutated variant", v, "does not pass:", st, why)
            return 2
    jobs = []
    for m in muts:
        vd = spec["variants"][m["variant"]]
        tf = d / m["file"] if m.get("file") else d / vd["file"]          # a mutant may name a shared file instead (``file``, relative to the function's folder)
        src = tf.read_text()
        if src.count(m["old"]) != 1:
            print("mutant", m["name"], "does not apply exactly once:", src.count(m["old"]))
            return 2
        rd = work / m["name"] / "rtl"
        rd.mkdir(parents=True)
        (rd / tf.name).write_text(src.replace(m["old"], m["new"]))
        jobs.append((m, rd, vd))
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        out = list(ex.map(lambda j: one(fn, j[0]["variant"], j[1], work / j[0]["name"] / "sim", j[2]["mutant_run"]), jobs))
    res = []
    for (m, _, _), (st, why) in zip(jobs, out):
        res.append({"name": m["name"], "variant": m["variant"], "class": m["class"], "status": st, "detail": why, "why": m["why"]})
        print(f"{st:9s} {m['variant']:14s} {m['name']:24s} {why[:60]}")
    valid = [r for r in res if r["status"] != "invalid"]
    killed = [r for r in valid if r["status"] == "killed"]
    summary = {"function": fn, "mutants": len(res), "valid": len(valid), "killed": len(killed), "survived": [r["name"] for r in valid if r["status"] == "survived"],
               "invalid": [r["name"] for r in res if r["status"] == "invalid"], "score_pct": round(100 * len(killed) / max(1, len(valid)), 1),
               "per_variant": {v: {"valid": sum(1 for r in valid if r["variant"] == v), "killed": sum(1 for r in killed if r["variant"] == v)} for v in spec["variants"]},
               "results": res}
    outp = Path(a.json) if a.json else d / "verif" / "results" / "mutation.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(summary, indent=1) + "\n")
    print(f"{len(killed)} of {len(valid)} valid mutants killed ({summary['score_pct']} %), {len(summary['invalid'])} invalid -> {outp}")
    return 0 if not summary["survived"] else 1


if __name__ == "__main__":
    sys.exit(main())
