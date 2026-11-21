#!/usr/bin/env python3
"""Fresh evidence (brief 143d): re-run the evidence the traceability matrices read, from the current tree, and compare it with the committed records.

CI otherwise reads committed evidence files and never regenerates them, so a record that was true when it was made can go stale or be wrong
without any check noticing. This module has three parts.

* ``run``: execute named jobs (a pytest run with ``--junitxml``, the seeded-fault run, the Lean build) and write fresh records into a directory
  that mirrors the repository paths of the committed ones (``<dir>/results/b119/bench_sim.json`` is the fresh copy of ``results/b119/bench_sim.json``),
  plus one manifest per job (command, exit code, seconds, commit, tool versions, hash of every output). Nothing in the tree is overwritten.
* ``assemble``: merge the output directories of several jobs (one per GitHub runner) into one; JUnit parts of the same record are concatenated.
* ``compare``: say, per record and per verification item, whether the committed record agrees with the fresh run. ``python -m flow.trace_v1 show --fresh DIR``
  and ``write --fresh DIR`` show the same thing in the matrix as "committed record differs from fresh run".

What counts as a difference (and what does not):

* JUnit: a test present in both records with a different outcome (pass against fail), or a test in the fresh run that the committed record does not
  have (the committed record is out of date). A test the fresh run skipped or did not run (an xsim test on a runner without Vivado) is "not re-run here",
  never a difference.
* JSON: any value that differs once volatile keys (seconds, tool banner, time stamps) are removed.
* Text: any difference after trailing space is removed.
* Lean build record: build success, axioms and tier per theorem, statement and definition hashes, file hashes and the toolchain (not the build-log hash).

The tiers: ``github`` jobs fit a free runner (the nightly workflow ``.github/workflows/fresh-evidence.yml``); ``local`` jobs need xsim, the full formal set or Vivado
and are run on the owner's PC by ``tools/fresh_evidence_local.sh`` (a systemd user timer is proposed in ``tools/systemd/``, not enabled).

  python -m flow.fresh_evidence list [--tier github|local]
  python -m flow.fresh_evidence run JOB [JOB ...] --out DIR
  python -m flow.fresh_evidence assemble --out DIR IN_DIR [IN_DIR ...]
  python -m flow.fresh_evidence compare --fresh DIR [--json FILE] [--md FILE] [DESIGN ...]    exit 1 if a committed record differs
"""

from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "fpga-design-agent/fresh-evidence/v1"
VOLATILE = frozenset({"seconds", "elapsed", "elapsed_s", "duration", "started", "ended", "time", "timestamp", "date", "tool"})
B96_JUNIT = "results/116_traceability/b96_kr260_10g/pytest_junit.xml"
B119_JUNIT = "results/116_traceability/b119_tcp_fast/pytest_junit.xml"
OSS = "FDA_OSS_CAD"

# Each job: tier, title, argv ({out} is the output directory), env, outputs (committed repo path, the part file written under {out}, kind), a timeout in
# minutes, and what it needs. The b96 junit is split in two parts so that two runners share the hour of cocotb benches; assemble joins them.
JOBS: dict[str, dict[str, Any]] = {
    "b119-tests": {
        "tier": "github", "title": "b119 model, cocotb bench (Icarus), the bench behind the risk logic, Verilator lint; also rewrites bench_sim.json and top_sim.json",
        "argv": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "designs/b119_tcp_fast/tests", "--junitxml={out}/_parts/b119-tests/pytest_junit.xml"],
        "env": {"B119_RECORD": "{out}/results/b119"}, "mkdir": ["results/b119"], "timeout_min": 30, "needs": ["iverilog", "verilator"],
        "outputs": [{"committed": B119_JUNIT, "part": "_parts/b119-tests/pytest_junit.xml", "kind": "junit"},
                    {"committed": "results/b119/bench_sim.json", "part": "results/b119/bench_sim.json", "kind": "json"},
                    {"committed": "results/b119/top_sim.json", "part": "results/b119/top_sim.json", "kind": "json"}]},
    "b119-mutation": {
        "tier": "github", "title": "b119 seeded faults: the 73 mutants of verif/mutants.yaml against the whole cocotb bench (about a quarter of an hour on two cores)",
        "argv": [sys.executable, "designs/b119_tcp_fast/tests/run_mutants.py", "--jobs", "3", "--json", "{out}/results/b119/mutation.json"],
        "env": {}, "mkdir": ["results/b119"], "timeout_min": 60, "needs": ["iverilog"],
        "outputs": [{"committed": "results/b119/mutation.json", "part": "results/b119/mutation.json", "kind": "json"}]},
    "b96-pcs-rtl": {
        "tier": "github", "title": "b96 10G PCS/MAC cocotb benches (Icarus): the slow half of the b96 JUnit record",
        "argv": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py", "--junitxml={out}/_parts/b96-pcs-rtl/pytest_junit.xml"],
        "env": {}, "mkdir": [], "timeout_min": 150, "needs": ["iverilog"],
        "outputs": [{"committed": B96_JUNIT, "part": "_parts/b96-pcs-rtl/pytest_junit.xml", "kind": "junit"}]},
    "b96-rest": {
        "tier": "github", "title": "b96 model, bench, host, docs, reduced formal (SymbiYosys, OSS CAD Suite), pyuvm bench; the xsim UVM tests skip here",
        "argv": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "designs/b96_kr260_10g/tests", "--ignore=designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py",
                 "--junitxml={out}/_parts/b96-rest/pytest_junit.xml"],
        "env": {"FDA_REQUIRE_FORMAL": "1"}, "mkdir": [], "timeout_min": 120, "needs": ["iverilog", "sby"],
        "outputs": [{"committed": B96_JUNIT, "part": "_parts/b96-rest/pytest_junit.xml", "kind": "junit"}]},
    "lean-build": {
        "tier": "github", "title": "Lean: `lake build` of formal/lean with #print axioms, written as a fresh build record",
        "argv": [sys.executable, "-m", "flow.fresh_evidence", "lean", "--out", "{out}"],
        "env": {}, "mkdir": [], "timeout_min": 40, "needs": ["lake"],
        "outputs": [{"committed": "formal/lean/records/build_record.json", "part": "formal/lean/records/build_record.json", "kind": "lean"}]},
    # ---- local tier: needs the owner's PC ------------------------------------------------------------------------------------------------------
    "b96-full-xsim": {
        "tier": "local", "title": "b96 whole test directory with xsim (UVM bench, 17 mutants) and the full formal set: the complete b96 JUnit record (an hour or more)",
        "argv": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "designs/b96_kr260_10g/tests", "--junitxml={out}/_parts/b96-full-xsim/pytest_junit.xml"],
        "env": {"FDA_REQUIRE_FORMAL": "1"}, "mkdir": [], "timeout_min": 240, "needs": ["iverilog", "sby", "xsim"], "heavy": True,
        "outputs": [{"committed": B96_JUNIT, "part": "_parts/b96-full-xsim/pytest_junit.xml", "kind": "junit"}]},
    "b96-formal-full": {
        "tier": "local", "title": "b96 rate matcher, the full SymbiYosys set (every bit of the entry and the long runs)",
        "argv": [sys.executable, "designs/b96_kr260_10g/verif/formal/run_formal.py", "--set", "full", "--json", "{out}/results/b115/formal_full.json"],
        "env": {}, "mkdir": ["results/b115"], "timeout_min": 180, "needs": ["sby"], "heavy": True,
        "outputs": [{"committed": "results/b115/formal_full.json", "part": "results/b115/formal_full.json", "kind": "json"}]},
    "b119-ooc-vivado": {
        "tier": "local", "title": "b119 out-of-context Vivado build (post-route LUT, FF, WNS, WHS at three clocks); heavy slot, Vivado impl",
        "argv": [sys.executable, "-m", "designs.b119_tcp_fast.ooc.ooc", "--tag", "_fresh"],
        "env": {}, "mkdir": [], "timeout_min": 120, "needs": ["vivado"], "heavy": True, "vivado": True,
        "move": [{"from": "results/b119/ooc/_fresh.json", "to": "{out}/results/b119/ooc/tcp_fast.json"}],
        "outputs": [{"committed": "results/b119/ooc/tcp_fast.json", "part": "results/b119/ooc/tcp_fast.json", "kind": "json"}]},
}


# ---- helpers ---------------------------------------------------------------------------------------------
def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git(*a: str) -> str:
    try:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def tool_versions() -> dict[str, str]:
    out = {"python": sys.version.split()[0]}
    for name, argv in (("iverilog", ["iverilog", "-V"]), ("verilator", ["verilator", "--version"]), ("yosys", ["yosys", "-V"]), ("lake", ["lake", "--version"])):
        exe = shutil.which(argv[0])
        if exe is None and argv[0] == "yosys" and os.environ.get(OSS):
            exe = str(Path(os.environ[OSS]) / "bin" / "yosys")
        if exe is None and argv[0] == "lake" and (Path.home() / ".elan/bin/lake").exists():
            exe = str(Path.home() / ".elan/bin/lake")
        if exe and Path(exe).exists():
            try:
                r = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=30)
                out[name] = ((r.stdout or r.stderr).strip().splitlines() or [""])[0][:120]
            except (OSError, subprocess.SubprocessError):
                pass
    return out


def _sub(s: str, out: Path) -> str:
    return s.replace("{out}", str(out))


# ---- run -------------------------------------------------------------------------------------------------
def run_job(name: str, out: Path) -> dict[str, Any]:
    job = JOBS[name]
    out.mkdir(parents=True, exist_ok=True)
    for d in job.get("mkdir") or []:
        (out / d).mkdir(parents=True, exist_ok=True)
    (out / "_logs").mkdir(exist_ok=True)
    (out / "_manifests").mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    env.update({k: _sub(v, out) for k, v in (job.get("env") or {}).items()})
    if os.environ.get(OSS):
        env["PATH"] = str(Path(os.environ[OSS]) / "bin") + os.pathsep + env["PATH"]
    argv = [_sub(a, out) for a in job["argv"]]
    t0, started = time.time(), _now()
    log = out / "_logs" / f"{name}.log"
    try:
        with log.open("w") as fh:
            rc = subprocess.run(argv, cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=job["timeout_min"] * 60).returncode
    except subprocess.TimeoutExpired:
        rc = 124
    for mv in job.get("move") or []:
        src, dst = ROOT / mv["from"], Path(_sub(mv["to"], out))
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    outs = []
    for o in job["outputs"]:
        p = out / o["part"]
        outs.append({**o, "present": p.exists(), "sha256": _sha(p) if p.exists() else None, "bytes": p.stat().st_size if p.exists() else 0})
    man = {"schema": SCHEMA, "job": name, "tier": job["tier"], "title": job["title"], "argv": [a.replace(str(out), "{out}") for a in argv], "rc": rc, "started": started,
           "seconds": round(time.time() - t0, 1), "commit": _git("rev-parse", "HEAD"), "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
           "tools": tool_versions(), "outputs": outs}
    (out / "_manifests" / f"{name}.json").write_text(json.dumps(man, indent=1) + "\n")
    print(f"{name}: rc {rc}, {man['seconds']} s, outputs {sum(1 for o in outs if o['present'])}/{len(outs)}")
    return man


def lean_job(out: Path) -> int:
    """Build the Lean project and write the record into the fresh directory (the committed record is never touched)."""
    from flow import lean_tier, trace_v1
    if not lean_tier.toolchain_available():
        print("the Lean toolchain (lake) is not installed")
        return 2
    target = out / "formal" / "lean" / "records" / "build_record.json"
    lean_tier.record_path = lambda project=lean_tier.DEFAULT_PROJECT: out / project / "records" / "build_record.json"
    items = lean_tier.lean_items([trace_v1.load(d) for d in trace_v1.v1_designs()])
    for project in sorted({i["lean"].get("project", lean_tier.DEFAULT_PROJECT) for i in items}):
        print("wrote", lean_tier.write_record(items, project))
    return 0 if target.exists() else 1


# ---- assemble --------------------------------------------------------------------------------------------
def _junit_cases(p: Path) -> list[ET.Element]:
    return list(ET.parse(p).getroot().iter("testcase"))


def merge_junit(parts: list[Path], dst: Path) -> None:
    suite = ET.Element("testsuite", name="fresh-evidence")
    cases = [c for p in parts for c in _junit_cases(p)]
    for c in cases:
        suite.append(c)
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(sum(1 for c in cases if c.find("failure") is not None or c.find("error") is not None)))
    suite.set("skipped", str(sum(1 for c in cases if c.find("skipped") is not None)))
    root = ET.Element("testsuites")
    root.append(suite)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(dst, encoding="utf-8", xml_declaration=True)


def assemble(in_dirs: list[Path], out: Path) -> dict[str, Any]:
    mans: list[dict] = []
    seen: dict[str, dict] = {}
    for d in in_dirs:
        for mp in sorted((d / "_manifests").glob("*.json")):
            m = json.loads(mp.read_text())
            m["_dir"] = str(d)
            mans.append(m)
    by_rec: dict[str, list[tuple[dict, dict]]] = {}
    for m in mans:
        for o in m["outputs"]:
            if o["present"]:
                by_rec.setdefault(o["committed"], []).append((m, o))
    for committed, ps in by_rec.items():
        dst = out / committed
        if ps[0][1]["kind"] == "junit":
            merge_junit([Path(m["_dir"]) / o["part"] for m, o in ps], dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src = Path(ps[-1][0]["_dir"]) / ps[-1][1]["part"]
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
        seen[committed] = {"kind": ps[0][1]["kind"], "sha256": _sha(dst), "jobs": [m["job"] for m, _ in ps]}
    out.mkdir(parents=True, exist_ok=True)
    jobs = [{k: m[k] for k in ("job", "tier", "rc", "seconds", "commit", "dirty", "started", "tools") if k in m} | {"outputs_present": sum(1 for o in m["outputs"] if o["present"]), "outputs": len(m["outputs"])} for m in mans]
    expected = sorted({o["committed"] for m in mans for o in m["outputs"]})
    index = {"schema": SCHEMA, "assembled": _now(), "records": seen, "expected_records": expected, "jobs": jobs}
    (out / "manifest.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"assembled {len(seen)} record(s) from {len(mans)} job manifest(s) into {out}")
    return index


# ---- record comparison -----------------------------------------------------------------------------------
def junit_outcomes(p: Path) -> dict[str, str]:
    """``stem::test`` -> pass | fail | skip (the same naming the traceability reader uses)."""
    out: dict[str, str] = {}
    for tc in _junit_cases(p):
        stem = (tc.get("classname") or "").split(".")[-1]
        o = "skip" if tc.find("skipped") is not None else "fail" if (tc.find("failure") is not None or tc.find("error") is not None) else "pass"
        out[f"{stem}::{tc.get('name')}"] = o
    return out


def strip_volatile(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: strip_volatile(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [strip_volatile(v) for v in x]
    return x


def json_diff(a: Any, b: Any, path: str = "") -> list[str]:
    """Paths where a (committed) and b (fresh) differ, with the two values; floats within 1e-9 relative are equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else str(k)
            if k not in a:
                out.append(f"{p}: only in the fresh run")
            elif k not in b:
                out.append(f"{p}: only in the committed record")
            else:
                out += json_diff(a[k], b[k], p)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in json_diff(x, y, f"{path}.{i}")]
    if isinstance(a, float) or isinstance(b, float):
        try:
            if abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a))):
                return []
        except (TypeError, ValueError):
            pass
    return [] if a == b else [f"{path or '(root)'}: committed {json.dumps(a)[:60]} but fresh {json.dumps(b)[:60]}"]


LEAN_KEYS = ("build_ok", "axioms", "tier", "statement_sha256", "definitions_sha256")


def lean_diff(a: dict, b: dict) -> list[str]:
    out = []
    for k in ("build_ok", "toolchain", "lean_version", "files", "rtl_sources"):
        out += json_diff(a.get(k), b.get(k), k)
    for name in sorted(set(a.get("theorems") or {}) | set(b.get("theorems") or {})):
        ta, tb = (a.get("theorems") or {}).get(name), (b.get("theorems") or {}).get(name)
        if ta is None or tb is None:
            out.append(f"theorem {name}: only in the {'fresh run' if ta is None else 'committed record'}")
            continue
        for k in LEAN_KEYS:
            out += json_diff(ta.get(k), tb.get(k), f"theorem {name}.{k}")
    return out


def compare_record(committed: str, kind: str, fresh_dir: Path) -> dict[str, Any]:
    """One record, committed against fresh: state is agrees | differs | not_rerun (no fresh file)."""
    c, f = ROOT / committed, fresh_dir / committed
    if not f.exists():
        return {"record": committed, "kind": kind, "state": "not_rerun", "details": ["no fresh file"]}
    if not c.exists():
        return {"record": committed, "kind": kind, "state": "differs", "details": ["no committed record; the fresh run made one"]}
    if kind == "junit":
        a, b = junit_outcomes(c), junit_outcomes(f)
        det = [f"{t}: committed {a[t]}, fresh {b[t]}" for t in sorted(a) if t in b and "skip" not in (a[t], b[t]) and a[t] != b[t]]
        new = sorted(t for t in b if t not in a and b[t] != "skip")
        if new:
            det.append(f"{len(new)} test(s) in the fresh run that the committed record does not have (the record is out of date), e.g. {', '.join(new[:3])}")
        return {"record": committed, "kind": kind, "state": "differs" if det else "agrees", "details": det[:40], "committed_tests": len(a), "fresh_tests": len(b),
                "fresh_failing": sorted(t for t, o in b.items() if o == "fail")[:20], "not_rerun": len([t for t in a if t not in b or b[t] == "skip"])}
    if kind == "json":
        det = json_diff(strip_volatile(json.loads(c.read_text())), strip_volatile(json.loads(f.read_text())))
    elif kind == "lean":
        det = lean_diff(json.loads(c.read_text()), json.loads(f.read_text()))
    else:
        det = [] if c.read_text().rstrip() == f.read_text().rstrip() else ["text differs"]
    return {"record": committed, "kind": kind, "state": "differs" if det else "agrees", "details": det[:40], "n_differences": len(det)}


def records_of(fresh_dir: Path) -> list[tuple[str, str]]:
    idx = fresh_dir / "manifest.json"
    if idx.exists():
        m = json.loads(idx.read_text())
        kinds = {c: r["kind"] for c, r in m["records"].items()}
        return sorted(kinds.items())
    return sorted({(o["committed"], o["kind"]) for j in JOBS.values() for o in j["outputs"] if (fresh_dir / o["committed"]).exists()})


# ---- item annotation (called by trace_v1.collect(fresh=...)) -----------------------------------------------
def annotate(plan: dict, results: list[dict], design: Path, fresh_dir: Path) -> None:
    """Add ``fresh = {state, detail}`` to every result: ``differs`` when the committed record disagrees with the fresh run for what the item reads,
    ``agrees``, or ``not_rerun`` (the evidence is not something a fresh run regenerates). Verdicts (status) are left as the committed record gives them."""
    from flow import trace_v1 as T
    req_by_id = {r["id"]: r for r in plan["requirements"]}
    lp = fresh_dir / "formal/lean/records/build_record.json"
    lean_cmp = compare_record("formal/lean/records/build_record.json", "lean", fresh_dir) if lp.exists() else None
    for it, res in zip(plan["verification"], results):
        res["fresh"] = {"state": "not_rerun", "detail": ""}
        if it.get("method") == "formal_lean":
            if lean_cmp is not None:
                th = (it.get("lean") or {}).get("theorem")
                mine = [d for d in lean_cmp["details"] if th and (f"theorem {th}." in d or f"theorem {th}:" in d)] + [d for d in lean_cmp["details"] if d.startswith(("build_ok", "toolchain", "lean_version"))]
                res["fresh"] = {"state": "differs" if mine else "agrees", "detail": "; ".join(mine[:3])}
            continue
        ev = it.get("evidence") or {}
        if not ev.get("file") or ev.get("reader") == "review":
            continue
        hits = sorted(glob.glob(str(fresh_dir / ev["file"])))
        if not hits:
            continue
        fp = Path(hits[-1])
        reader = ev.get("reader", "json")
        if reader == "junit":
            cp = T.resolve(ev["file"])
            if cp is None:
                res["fresh"] = {"state": "differs", "detail": "no committed record; the fresh run made one"}
                continue
            a, b = junit_outcomes(cp), junit_outcomes(fp)
            want_f, want_c = [], []
            for t in ev.get("tests") or []:
                if t.endswith("::*"):
                    want_f += [k for k in b if k.startswith(t[:-1])]
                    want_c += [k for k in a if k.startswith(t[:-1])]
                else:
                    want_f.append(t)
                    want_c.append(t)
            det = [f"{t}: committed {a.get(t, 'absent')}, fresh {b[t]}" for t in want_f if t in b and b[t] != "skip" and a.get(t) != b[t] and a.get(t) is not None]
            det += [f"{t}: in the fresh run, absent from the committed record" for t in want_f if t in b and b[t] != "skip" and t not in a]
            rerun = [t for t in want_f if t in b and b[t] != "skip"]
            if not rerun:
                res["fresh"] = {"state": "not_rerun", "detail": "none of the item's tests was run in the fresh run"}
            else:
                res["fresh"] = {"state": "differs" if det else "agrees", "detail": "; ".join(det[:3]) if det else f"{len(rerun)} test(s) re-run, same outcome"}
            continue
        # a value record: judge the item against both files and compare what it reads
        committed_res = T.judge(it, req_by_id, {})
        T.FRESH_DIR = fresh_dir
        try:
            fresh_res = T.judge(it, req_by_id, {})
        finally:
            T.FRESH_DIR = None
        det = []
        if committed_res["status"] != fresh_res["status"]:
            det.append(f"committed {committed_res['status']}, fresh {fresh_res['status']}")
        if committed_res.get("value") != fresh_res.get("value"):
            det.append(f"value: committed {T.fmt(committed_res.get('value'))}, fresh {T.fmt(fresh_res.get('value'))}")
        if fp.suffix == ".json" and committed_res.get("evidence", {}).get("exists"):
            try:
                ca, fa = json.loads((T.ROOT / committed_res["evidence"]["file"]).read_text()), json.loads(fp.read_text())
                for c in it.get("pass_when") or []:
                    if c.get("field"):
                        va, vb = T.dig(ca, c["field"]), T.dig(fa, c["field"])
                        if va != vb:
                            det.append(f"{c['field']}: committed {T.fmt(va)}, fresh {T.fmt(vb)}")
            except (KeyError, IndexError, ValueError, TypeError, OSError):
                pass
        res["fresh"] = {"state": "differs" if det else "agrees", "detail": "; ".join(det[:3]) if det else "same value in the fresh run"}


# ---- compare ---------------------------------------------------------------------------------------------
def compare(fresh_dir: Path, designs: list[Path], expect_tier: str | None = None) -> dict[str, Any]:
    from flow import trace_v1 as T
    idx = json.loads((fresh_dir / "manifest.json").read_text()) if (fresh_dir / "manifest.json").exists() else {"jobs": [], "records": {}, "expected_records": []}
    recs = [compare_record(c, k, fresh_dir) for c, k in records_of(fresh_dir)]
    missing = [c for c in idx.get("expected_records", []) if c not in idx.get("records", {})]
    failed_jobs = [j["job"] for j in idx.get("jobs", []) if j.get("outputs_present", 0) < j.get("outputs", 0)]
    if expect_tier:     # a job that never reported (its runner died or timed out before the manifest) is a failure, not an agreement
        failed_jobs += [n for n, j in JOBS.items() if j["tier"] == expect_tier and n not in {x["job"] for x in idx.get("jobs", [])}]
    items = []
    for d in designs:
        c = T.collect(d, "recorded", fresh=fresh_dir)
        for i in c["items"]:
            f = i.get("fresh") or {}
            if f.get("state") == "differs":
                items.append({"design": c["design"], "item": i["id"], "method": i["method"], "committed_status": i["status"], "detail": f["detail"]})
    out = {"schema": SCHEMA, "compared": _now(), "fresh_dir": str(fresh_dir), "commit": _git("rev-parse", "HEAD"), "jobs": idx.get("jobs", []), "records": recs,
           "records_differing": [r["record"] for r in recs if r["state"] == "differs"], "records_missing": missing, "jobs_without_output": failed_jobs,
           "items_differing": items}
    out["differs"] = bool(out["records_differing"] or out["records_missing"] or out["jobs_without_output"] or items)
    return out


def render_report(r: dict[str, Any]) -> str:
    L = ["# Fresh evidence: committed records against a run of the current tree", "",
         f"Compared {r['compared']}, tree commit `{r['commit'][:10]}`. " + ("**A committed record differs from the fresh run.**" if r["differs"] else "Every re-run record agrees with its committed record."), ""]
    if r["jobs"]:
        L += ["| Job | Exit code | Seconds | Outputs |", "|---|---|---|---|"] + [f"| {j['job']} | {j['rc']} | {j['seconds']:g} | {j['outputs_present']} of {j['outputs']} |" for j in r["jobs"]] + [""]
    L += ["| Record | Kind | State | Detail |", "|---|---|---|---|"]
    for x in r["records"]:
        extra = f" ({x['fresh_tests']} tests fresh, {x['committed_tests']} committed, {x['not_rerun']} committed test(s) not re-run here)" if x["kind"] == "junit" else ""
        L.append(f"| `{x['record']}` | {x['kind']} | {x['state'].replace('_', ' ')} | {'; '.join(x['details'][:3]).replace('|', '/')}{extra} |")
    if r["records_differing"]:
        L += ["", "## Differences by record", ""]
        for x in r["records"]:
            if x["state"] == "differs":
                L += [f"### `{x['record']}`", ""] + [f"- {d}" for d in x["details"][:15]] + [""]
    if r["items_differing"]:
        L += ["", "## Verification items whose committed record differs from the fresh run", "", "| Design | Item | Method | Committed status | What differs |", "|---|---|---|---|---|"]
        L += [f"| {i['design']} | {i['item']} | {i['method']} | {i['committed_status']} | {i['detail'].replace('|', '/')} |" for i in r["items_differing"]]
    if r["records_missing"] or r["jobs_without_output"]:
        L += ["", "## Jobs that produced no record", ""] + [f"- record `{m}` has no fresh file" for m in r["records_missing"]] + [f"- job `{j}`" for j in r["jobs_without_output"]]
    L += ["", "A difference means the committed record is stale or wrong for this tree (or the fresh run found a regression). Re-record it as described in "
          "`results/116_traceability/README.md`, then `python -m flow.trace_v1 pin DESIGN` and `write DESIGN`.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["list", "run", "assemble", "compare", "lean"])
    ap.add_argument("names", nargs="*", help="run: job names; assemble: input directories; compare: designs (default every design with a testplan)")
    ap.add_argument("--out", default="")
    ap.add_argument("--fresh", default="")
    ap.add_argument("--tier", choices=["github", "local"], default=None, help="list/run: only this tier; compare: every job of this tier must have reported")
    ap.add_argument("--json", default="")
    ap.add_argument("--md", default="")
    a = ap.parse_intermixed_args(argv)
    if a.cmd == "list":
        for n, j in JOBS.items():
            if a.tier in (None, j["tier"]):
                print(f"{n}\t{j['tier']}\t{j['timeout_min']} min max\t{j['title']}")
        return 0
    if a.cmd == "lean":
        return lean_job(Path(a.out))
    if a.cmd == "run":
        names = a.names or [n for n, j in JOBS.items() if a.tier in (None, j["tier"])]
        bad = [n for n in names if n not in JOBS]
        if bad or not a.out:
            print("usage: run JOB... --out DIR; unknown:", bad)
            return 2
        out = Path(a.out).resolve()
        mans = [run_job(n, out) for n in names]
        assemble([out], out)
        return 0 if all(any(o["present"] for o in m["outputs"]) for m in mans) else 1
    if a.cmd == "assemble":
        assemble([Path(x).resolve() for x in a.names], Path(a.out).resolve())
        return 0
    from flow import trace_v1 as T
    fresh = Path(a.fresh).resolve()
    ds = [(ROOT / x if not Path(x).is_absolute() else Path(x)) for x in a.names] or T.v1_designs()
    r = compare(fresh, ds, a.tier)
    md = render_report(r)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1) + "\n")
    if a.md:
        Path(a.md).write_text(md)
    print(md)
    return 1 if r["differs"] else 0


if __name__ == "__main__":
    sys.exit(main())
