"""``python -m agent example tools <name>``: show that the tools repeat for the same RTL, without a model call (brief 195).

The reference runs' RTL is stored beside their records (``results/195_repro_examples/<name>/ref_<n>_rtl/``). This re-runs the task's hidden bench on that RTL and
compares the per-test verdicts with the record; the result is the same RTL hash, the same verdicts, or a named difference."""

from __future__ import annotations

import json
import re
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


def vivado_check(name: str, n: int, slot: bool = True, results: Path | None = None, same_path: bool = True) -> dict[str, Any]:
    import os
    import shutil
    import subprocess
    import yaml
    d = (results or R.RESULTS) / name
    rtl, meta, xdc, ref_f = stored_rtl(name, n, results), d / f"ref_{n}_design.json", d / f"ref_{n}_design.xdc", d / f"ref_{n}.json"
    if rtl is None or not (meta.is_file() and xdc.is_file() and ref_f.is_file()):
        return {"ok": False, "error": f"reference {n} of {name} has no stored design files (record it again with `example record`)"}
    ref, m = json.loads(ref_f.read_text()), json.loads(meta.read_text())
    # The build stamp (compiled into the design as BUILD_STAMP) hashes the sources' paths relative to the repository root, so the same RTL in another directory is another
    # netlist constant and, measured, a slightly different build. To rebuild "the same inputs" the design goes back to the relative path it was built at.
    srcs = m.get("sources") or []
    mm = next((re.fullmatch(r"(runs/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/rtl/\*\.sv", x) for x in srcs if x.startswith("runs/")), None)
    if mm is None:
        return {"ok": False, "error": f"reference {n} of {name} does not record the path it was built at (record it again with `example record`)"}
    scratch = (R.ROOT / (mm.group(1) if same_path else f"runs/_tools/{name}_ref{n}")).resolve()
    if not same_path:                                                  # the same RTL at another path: measures what the path-dependent build stamp does
        srcs = ["shell/rtl/*.sv", f"runs/_tools/{name}_ref{n}/rtl/*.sv"]
        m = {**m, "constraints": [f"runs/_tools/{name}_ref{n}/design.xdc"]}
    if not str(scratch).startswith(str(R.ROOT / "runs")) or ".." in mm.group(1):
        return {"ok": False, "error": "bad scratch path"}
    marker = scratch / ".example_tools"
    if scratch.exists() and not marker.is_file():
        return {"ok": False, "error": f"{mm.group(1)} already exists here and was not made by this command (it is probably the original run directory): nothing was touched; use another reference"}
    if scratch.exists():
        shutil.rmtree(scratch)                                         # made by this command earlier (it carries the marker), under runs/
    (scratch / "rtl").mkdir(parents=True)
    marker.write_text("made by python -m agent example tools\n")
    for f in rtl.rglob("*"):
        if f.is_file():
            shutil.copyfile(f, scratch / "rtl" / f.relative_to(rtl))
    shutil.copyfile(xdc, scratch / "design.xdc")
    (scratch / "build.yaml").write_text(yaml.safe_dump({"top": m["top"], "part": m["part"], "sources": srcs, "constraints": m.get("constraints") or [], "generics": m.get("generics") or {}}))
    lock, text = (RN.take_slot("195", f"example tools {name} ref {n}") if slot else (None, None))
    try:
        env = {**os.environ, "FDA_STOP_AFTER": "route", "FDA_BUILD_CACHE": "0", **({"FDA_VIVADO_MAX": "2", "FDA_VIVADO_THREADS": "2"} if lock is not None else {})}   # a second Vivado only because take_heavy_slot.sh admitted this job
        p = subprocess.run([str(R.ROOT / "flow" / "run_vivado.sh"), str(scratch), "base"], cwd=R.ROOT, env=env, capture_output=True, text=True, timeout=3600)
    finally:
        RN.release_slot(lock, text)
    b = X.build_of(scratch)
    want = ref.get("tool_results") or {}
    keys = ("build_stamp", "sources_sha256", "lut", "ff", "dsp", "bram36", "wns_ns", "whs_ns", "vivado_version")
    diffs = {k: {"now": b.get(k), "record": want.get(k)} for k in keys if b.get(k) != want.get(k)}
    return {"same_path": same_path, "path": scratch.relative_to(R.ROOT).as_posix(), "ok": bool(b) and not diffs, "exit_code": p.returncode, "now": {k: b.get(k) for k in keys}, "record": {k: want.get(k) for k in keys}, "differences": diffs, "vivado_wall_s": b.get("vivado_wall_s"),
            "refused_or_failed": (p.stderr.strip().splitlines() or p.stdout.strip().splitlines() or [""])[-1][:200] if not b else None}


def main(a) -> int:
    r = bench_check(a.name, a.ref)
    if "error" in r:
        print(r["error"], file=sys.stderr)
        return 2
    print(f"RTL hash {r['rtl_sha256'][:16]}: {'the same as the record' if r['same_rtl'] else 'DIFFERENT from the record (the stored RTL changed)'}")
    for t, ok in sorted(r["tests_now"].items()):
        print(f"  {'PASS' if ok else 'FAIL'}  {t}  (record: {'PASS' if r['tests_recorded'].get(t) else 'FAIL'})")
    print("bench verdicts " + ("match the record" if not r["differences"] else "DIFFER in " + ", ".join(r["differences"])))
    code = 0 if r["ok"] else 1
    if getattr(a, "vivado", False):
        v = vivado_check(a.name, a.ref, slot=not a.no_slot, same_path=not getattr(a, "other_path", False))
        if "error" in v:
            print(v["error"], file=sys.stderr)
            return 2
        if v.get("refused_or_failed") is not None:
            print("Vivado rebuild did not produce a build: " + v["refused_or_failed"], file=sys.stderr)
            return 2
        print(f"Vivado rebuild (no cache, post-route, {v['vivado_wall_s']} s): " + ("every compared field equals the record" if v["ok"] else "DIFFERS: " + json.dumps(v["differences"])))
        for k, x in v["now"].items():
            print(f"  {k}: {x}  (record {v['record'][k]})")
        code = code or (0 if v["ok"] else 1)
    return code
