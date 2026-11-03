#!/usr/bin/env python3
"""Self-check a benchmark task: the reference RTL passes, every mutant is killed, the trap variant fails its trap test.

    python3 benchmark/tools/check_task.py <task_dir> [--sim icarus|verilator] [--only ref,mutants,trap] [--out DIR]

hidden/mutants.yaml lists ``mutants`` (each one exact-string edit of a copy of ref/rtl: ``{name, file, find,
replace, why}``; ``find`` must occur exactly once) and an optional ``trap``: the book or demo behaviour, as edits
of the reference (``{twin, why, edits: [{file, find, replace}], must_fail: [test, ...]}``). A mutant is killed when
any acceptance test fails or the copy does not build; the trap passes its check only if every ``must_fail`` test
fails. The real RTL is never touched. Writes <out>/<task>__<sim>.json (default: benchmark/results/reference/).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark.tools import run_task  # noqa: E402


def apply(src: Path, dst: Path, edits: list[dict]) -> None:
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    for e in edits:
        f = dst / e["file"]
        text = f.read_text()
        n = text.count(e["find"])
        if n != 1:
            raise SystemExit(f"{dst.name}: {e['find']!r} occurs {n} times in {e['file']} (must be exactly once)")
        f.write_text(text.replace(e["find"], e["replace"]))


def check(task: Path, sim: str, only: set[str], out: Path) -> dict:
    task = task.resolve()
    spec = yaml.safe_load((task / "hidden" / "mutants.yaml").read_text())
    ref = task / "ref" / "rtl"
    work = ROOT / "build" / "bench_mut" / task.name
    res: dict = {"task": task.name, "sim": sim, "date": time.strftime("%Y-%m-%d")}
    if "ref" in only:
        r = run_task.run(task, ref, sim, tag="ref")
        res["ref"] = {"pass": r["pass"], "tests": r["tests"]}
        print(f"{task.name} ref [{sim}]: {'PASS' if r['pass'] else 'FAIL'} {sum(r['tests'].values())}/{len(r['tests'])}")
    if "mutants" in only:
        res["mutants"] = []
        for m in spec.get("mutants", []):
            d = work / m["name"]
            apply(ref, d, [m])
            r = run_task.run(task, d, sim, tag=f"mut_{m['name']}")
            killed = not r["pass"]
            failed = [t for t, ok in r["tests"].items() if not ok]
            res["mutants"].append({"name": m["name"], "why": m["why"], "killed": killed, "built": r["built"],
                                   "failed_tests": failed})
            print(f"  mutant {m['name']}: {'killed' if killed else 'SURVIVED'} {failed if r['built'] else '(no build)'}")
        res["mutants_killed"] = sum(m["killed"] for m in res["mutants"])
        res["mutants_total"] = len(res["mutants"])
    if "trap" in only and spec.get("trap"):
        t = spec["trap"]
        d = work / "trap"
        apply(ref, d, t["edits"])
        r = run_task.run(task, d, sim, tag="trap")
        failed = [n for n, ok in r["tests"].items() if not ok]
        ok = r["built"] and all(n in failed for n in t["must_fail"])
        res["trap"] = {"twin": t["twin"], "why": t["why"], "must_fail": t["must_fail"], "failed_tests": failed,
                       "trap_fires": ok}
        print(f"  trap ({t['twin']}): {'fires' if ok else 'DOES NOT FIRE'} failed={failed}")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{task.name}__{sim}.json").write_text(json.dumps(res, indent=2) + "\n")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", type=Path)
    ap.add_argument("--sim", default="icarus")
    ap.add_argument("--only", default="ref,mutants,trap")
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "reference")
    a = ap.parse_args()
    r = check(a.task, a.sim, set(a.only.split(",")), a.out)
    ok = r.get("ref", {}).get("pass", True) and all(m["killed"] for m in r.get("mutants", [])) \
        and r.get("trap", {}).get("trap_fires", True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
