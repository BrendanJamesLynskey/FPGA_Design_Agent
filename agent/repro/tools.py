"""``python -m agent example tools <name>``: show that the tools repeat for the same RTL, without a model call (brief 195).

The reference runs' RTL is stored beside their records (``results/195_repro_examples/<name>/ref_<n>_rtl/``). This re-runs the task's hidden bench on that RTL and
compares the per-test verdicts with the record; the result is the same RTL hash, the same verdicts, or a named difference. ``--vivado`` also re-runs the post-route
build (a heavy job: the caller takes a slot) and compares resources, slack and build stamp with the record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agent.repro import extract as X
from agent.repro import registry as R
from agent.repro import runner as RN


def stored_rtl(name: str, n: int, results: Path | None = None) -> Path | None:
    d = (results or R.RESULTS) / name / f"ref_{n}_rtl"
    return d if d.is_dir() else None


def bench_check(name: str, n: int, python: str | None = None, results: Path | None = None) -> dict[str, Any]:
    import subprocess
    e = R.get(name)
    ref_file = (results or R.RESULTS) / name / f"ref_{n}.json"
    rtl = stored_rtl(name, n, results)
    if not ref_file.is_file() or rtl is None:
        return {"ok": False, "error": f"no stored reference {n} with RTL for {name}"}
    ref = json.loads(ref_file.read_text())
    files = sorted(p for p in rtl.rglob("*") if p.suffix in X.RTL_EXT)
    h = X.rtl_hash(files, rtl)
    out = rtl.parent / f".tools_{n}.json"
    p = subprocess.run([python or sys.executable, str(R.ROOT / e["scorer"]), str(R.task_dir(e)), "--rtl", str(rtl), "--tag", f"tools_{name}_{n}", "--json", str(out)],
                       cwd=R.ROOT, capture_output=True, text=True, timeout=3600)
    try:
        res = json.loads(out.read_text())
    finally:
        try:
            out.unlink()
        except OSError:
            pass
    tests = res.get("tests") or {}
    want = (ref.get("tool_results") or {}).get("bench_tests") or {}
    same_rtl = h == (ref.get("tool_results") or {}).get("rtl_sha256")
    diffs = sorted(t for t in set(tests) | set(want) if tests.get(t) != want.get(t))
    return {"ok": same_rtl and not diffs, "rtl_sha256": h, "record_rtl_sha256": (ref.get("tool_results") or {}).get("rtl_sha256"), "same_rtl": same_rtl,
            "tests_now": tests, "tests_recorded": want, "differences": diffs}


def main(a) -> int:
    r = bench_check(a.name, a.ref)
    if "error" in r:
        print(r["error"], file=sys.stderr)
        return 2
    print(f"RTL hash {r['rtl_sha256'][:16]}: {'the same as the record' if r['same_rtl'] else 'DIFFERENT from the record (the stored RTL changed)'}")
    for t, ok in sorted(r["tests_now"].items()):
        print(f"  {'PASS' if ok else 'FAIL'}  {t}  (record: {'PASS' if r['tests_recorded'].get(t) else 'FAIL'})")
    print("bench verdicts " + ("match the record" if not r["differences"] else "DIFFER in " + ", ".join(r["differences"])))
    if a.vivado:
        print("the --vivado re-build is not wired to this command yet: see docs/reproducible_examples.md", file=sys.stderr)
    return 0 if r["ok"] else 1
