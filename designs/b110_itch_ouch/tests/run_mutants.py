#!/usr/bin/env python3
"""Seeded-fault run for the ITCH/OUCH path (brief 110): every mutant of verif/mutants.yaml must be killed by the cocotb bench.

    python3 designs/b110_itch_ouch/tests/run_mutants.py [--only a,b] [--jobs 2] [--json results/b110/mutation.json]

Each mutant is a copy of rtl/ with one exact string replaced (the real RTL is never touched), run through tests/test_b110_rtl.py::test_all_benches
(B110_RTL_DIR points the bench at the copy). Killed: the bench fails. Survived: it passes. Invalid: the copy does not build (excluded from the score).
The unmutated RTL must pass first. Sim-only (Icarus); each run uses its own build root so two can run at once.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

D = Path(__file__).resolve().parents[1]
ROOT = D.parents[1]
WORK = ROOT / "build" / "b110_mut"


def run_one(name: str, rtl: Path, root: Path, env_extra: dict | None = None) -> dict:
    env = dict(os.environ, B110_RTL_DIR=str(rtl), FDA_SIM_BUILD_ROOT=str(root), PYTHONPATH=str(ROOT)) | {k: str(v) for k, v in (env_extra or {}).items()}
    env.pop("B110_RECORD", None)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(D / "tests" / "test_b110_rtl.py::test_all_benches"),
                        str(D / "tests" / "test_b110_rtl.py::test_book_core_queue"), str(D / "tests" / "test_b110_rtl.py::test_notional_modes")]
                       + ([str(D / "tests" / "test_b110_rtl.py::test_lane_by_type")] if (env_extra or {}).get("B110_PARSE_INPLACE") else []), cwd=ROOT, env=env, capture_output=True, text=True)
    xmls = [root / "b110_all" / "results.xml", root / "b110_lane0" / "results.xml", root / "b110_lane1" / "results.xml", root / "b110_book" / "results.xml", root / "b110_nt1" / "results.xml", root / "b110_nt2" / "results.xml"]
    failed = []
    for x in xmls:
        if x.is_file():
            failed += [tc.get("name") for tc in ET.parse(x).getroot().iter("testcase") if tc.find("failure") is not None]
    if r.returncode == 0:
        return {"name": name, "status": "survived", "killed_by": []}
    if not any(x.is_file() for x in xmls):
        return {"name": name, "status": "invalid", "killed_by": [], "note": (r.stdout + r.stderr)[-300:]}
    return {"name": name, "status": "killed", "killed_by": failed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    muts = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    if a.only:
        keep = set(a.only.split(","))
        muts = [m for m in muts if m["name"] in keep]
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    # the unmutated RTL first
    base = run_one("baseline", D / "rtl", WORK / "baseline")
    if base["status"] != "survived":
        print("the unmutated RTL does not pass:", base)
        return 2
    jobs = []
    for m in muts:
        src = (D / "rtl" / m["file"]).read_text()
        if src.count(m["old"]) != 1:
            print("mutant", m["name"], "does not apply exactly once")
            return 2
        d = WORK / m["name"] / "rtl"
        shutil.copytree(D / "rtl", d)
        (d / m["file"]).write_text(src.replace(m["old"], m["new"]))
        jobs.append((m, d))
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(lambda j: {**run_one(j[0]["name"], j[1], WORK / j[0]["name"] / "sim", j[0].get("env")), "class": j[0]["class"], "file": j[0]["file"], "why": j[0]["why"]}, jobs))
    for r in res:
        print(f"{r['status']:9s} {r['name']:22s} {', '.join(r['killed_by'][:3])}")
    valid = [r for r in res if r["status"] != "invalid"]
    killed = [r for r in valid if r["status"] == "killed"]
    out = {"mutants": len(res), "valid": len(valid), "killed": len(killed), "survived": [r["name"] for r in valid if r["status"] == "survived"],
           "invalid": [r["name"] for r in res if r["status"] == "invalid"], "score_pct": round(100 * len(killed) / max(1, len(valid)), 1), "results": res}
    print(f"killed {len(killed)} of {len(valid)} valid ({out['score_pct']} %); survived: {out['survived']}; invalid: {out['invalid']}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    return 0 if not out["survived"] else 1


if __name__ == "__main__":
    sys.exit(main())
