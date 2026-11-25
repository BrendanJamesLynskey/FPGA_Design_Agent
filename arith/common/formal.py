"""SymbiYosys runs for the arithmetic library (brief 139b): one job = a proof harness (`<function>_fv.sv`), its parameters, an engine.

Engines: ``abc pdr`` (unbounded: property-directed reachability finds an inductive invariant), ``smtbmc boolector`` in induction mode
(``kind``: k-induction, unbounded when it passes; brief 139c, for feed-forward pipelines whose arithmetic abc pdr cannot take), ``comb`` (a
combinational property: a depth-1 ``smtbmc boolector`` check over all inputs is complete) and ``bmc`` (bounded: a counterexample search to a
depth). A job states which it used; a BMC pass is reported as bounded with its depth, never as a proof.
The front end is yosys-slang (OSS CAD Suite), as in brief 115.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from arith.common import sim


def run(top: str, files: list[Path], params: dict[str, int], engine: str = "pdr", depth: int = 20, timeout: int = 900) -> dict:
    """engine: 'pdr' (mode prove, abc pdr), 'kind' (mode prove, smtbmc boolector: k-induction), 'comb' (a combinational lemma, depth 1) or 'bmc' (mode bmc, smtbmc boolector). Returns {status: PASS|FAIL|ERROR|TIMEOUT, engine, depth, seconds}."""
    sby = sim.need("sby")
    wd = Path(tempfile.mkdtemp(prefix="arith_sby_"))
    try:
        gen = " ".join(f"-G {k}={v}" for k, v in params.items())
        eng, mode = {"pdr": ("abc pdr", "prove"), "kind": ("smtbmc boolector", "prove"), "comb": ("smtbmc boolector", "bmc"), "bmc": ("smtbmc boolector", "bmc")}[engine]
        if engine == "comb":
            depth = 1
        names = [f.name for f in files]
        assert len(set(names)) == len(names), "formal sources must have distinct file names"
        sby_text = (f"[options]\nmode {mode}\ndepth {depth}\n\n[engines]\n{eng}\n\n[script]\nplugin -i slang\n"
                    f"read_slang --top {top} {gen} {' '.join(names)}\nprep -top {top}\n\n[files]\n" + "\n".join(str(f) for f in files) + "\n")
        (wd / "job.sby").write_text(sby_text)
        import time
        t0 = time.time()
        try:
            r = subprocess.run([sby, "-f", "-d", str(wd / "out"), str(wd / "job.sby")], capture_output=True, text=True, env=sim.env(), timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "engine": engine, "depth": depth, "seconds": round(time.time() - t0, 1)}
        st = (wd / "out" / "status")
        word = st.read_text().split()[0] if st.exists() else ""
        status = {"PASS": "PASS", "FAIL": "FAIL"}.get(word, "ERROR")
        return {"status": status, "engine": engine, "depth": depth, "seconds": round(time.time() - t0, 1), "log": r.stdout[-1500:] if status == "ERROR" else ""}
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def with_mutant(rtl_dir: Path, tmp: Path, fname: str, find: str, replace: str, mid: str) -> list[Path]:
    """Copy every .sv of rtl_dir to tmp with one replacement applied; return the copied paths."""
    from arith.common.mutants import apply
    out = []
    for f in sorted(rtl_dir.glob("*.sv")):
        t = tmp / f.name
        shutil.copy(f, t)
        out.append(t)
        if f.name == fname:
            t.write_text(apply(f.read_text(), find, replace, mid))
    return out


def summarise(record: dict) -> dict:
    """Counts the testplan reads: per kind (reference, pair, mutant) how many jobs ran, how many were proved unbounded, bounded, or caught a fault."""
    jobs = record.get("jobs", [])
    out = {}
    for kind in ("reference", "pair", "mutant", "lemma"):
        if kind == "lemma" and not any(j["kind"] == "lemma" for j in jobs):
            continue                                       # records of functions without lemma jobs keep their summary unchanged
        js = [j for j in jobs if j["kind"] == kind]
        out[kind] = {"jobs": len(js), "proved_unbounded": sum(1 for j in js if j["status"] == "PASS" and j["engine"] in ("pdr", "kind", "comb")),
                     "passed_bounded": sum(1 for j in js if j["status"] == "PASS" and j["engine"] == "bmc"),
                     "failed": sum(1 for j in js if j["status"] == "FAIL" and kind != "mutant") + sum(1 for j in js if j["status"] != "FAIL" and kind == "mutant"),
                     "faults_caught": sum(1 for j in js if j["status"] == "FAIL" and kind == "mutant")}
    return out
