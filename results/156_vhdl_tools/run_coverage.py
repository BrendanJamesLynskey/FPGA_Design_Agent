#!/usr/bin/env python3
"""Brief 156: VHDL code coverage of the same cocotb benches, NVC (--cover) and GHDL (gcov, where the back end has it).

    python3 results/156_vhdl_tools/run_coverage.py [--designs a,b] [--out coverage.json]

NVC: elaborate with --cover=statement,branch,toggle,expression,fsm-state, run the bench twice (seeds 1 and 2, separate databases), merge the two
databases (--cover-merge), export Cobertura XML (per-line hits) and NVC's own XML (bins per kind); numbers come from those exports.
GHDL: see the ``ghdl_*`` functions: the mcode back end has no coverage; the LLVM back end is tried with gcov flags.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_sims as R  # noqa: E402

NVC = str(Path.home() / ".local/opt/nvc-1.23.1/root/usr/bin/nvc")
KINDS = "statement,branch,toggle,expression,fsm-state"


def cobertura(path: Path) -> dict:
    r = ET.parse(path).getroot()
    files = {}
    for c in r.iter("class"):
        fn = c.get("filename")
        lines = {int(l.get("number")): int(l.get("hits")) for l in c.iter("line")}
        f = files.setdefault(fn, {})
        for k, v in lines.items():
            f[k] = max(f.get(k, 0), v)
    tot = sum(len(v) for v in files.values())
    hit = sum(1 for v in files.values() for h in v.values() if h > 0)
    return {"line_rate": r.get("line-rate"), "branch_rate": r.get("branch-rate"), "lines": tot, "lines_hit": hit,
            "per_file": {Path(k).name: {"lines": len(v), "hit": sum(1 for h in v.values() if h > 0)} for k, v in files.items()}}


def kinds(xml: Path) -> dict:
    """Bins per kind from NVC's xml export: total (excluding excluded bins, data = -2**31), hit (count >= 1)."""
    out = {}
    for e in ET.parse(xml).getroot().iter():
        if e.tag in ("statement", "branch", "toggle", "expression", "fsm-state", "functional"):
            n = int(e.get("data"))
            if n == -2147483648:
                out.setdefault(e.tag, {"total": 0, "hit": 0, "excluded": 0})["excluded"] += 1
                continue
            k = out.setdefault(e.tag, {"total": 0, "hit": 0, "excluded": 0})
            k["total"] += 1
            k["hit"] += n >= 1
    return out


def nvc_design(name: str, d: dict, ops: int, work: Path) -> dict:
    sim = R.sims(["nvc-aot"])[0]
    wd = work / f"nvc_cov__{name}"
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    w = f"--work=work:{wd}/work"
    gl = [f"-g{k}={v}" for k, v in d["gen"].items()]
    cmds = [[NVC, "--std=2008", w, "-a", "--preserve-case"] + [str(f) for f in d["files"]],
            [NVC, "--std=2008", w, "-e", f"--cover={KINDS}", f"--cover-file={wd}/run.ncdb"] + gl + [d["top"]]]
    for c in cmds:
        p = subprocess.run(c, cwd=wd, env=sim.env, capture_output=True, text=True)
        if p.returncode:
            return {"error": (p.stderr + p.stdout)[-400:]}
    dbs = {}
    shutil.copy(wd / "run.ncdb", wd / "elab.ncdb")          # elaboration writes the empty database; each run fills a fresh copy
    small = max(10, ops // 200)
    for label, seed, n in (("short_seed1", 1, small), ("short_seed2", 2, small), ("full_seed1", 1, ops)):
        shutil.copy(wd / "elab.ncdb", wd / "run.ncdb")
        env = dict(sim.env)
        env.update({"COCOTB_TEST_MODULES": d["bench"], "COCOTB_TOPLEVEL": d["top"], "TOPLEVEL_LANG": "vhdl", "PYTHONPATH": str(R.HERE / "benches"),
                    "PYGPI_PYTHON_BIN": sys.executable, "LIBPYTHON_LOC": R.PYLIB, "COCOTB_RESULTS_FILE": str(wd / "results.xml"),
                    "BENCH_OPS": str(n), "BENCH_SEED": str(seed), "PYTHONDONTWRITEBYTECODE": "1"})
        p = subprocess.run([NVC, "--std=2008", w, "-r", "--load", R.lib("vhpi", "nvc"), d["top"]], cwd=wd, env=env, capture_output=True, text=True)
        x = R.results_xml(wd / "results.xml")
        if x["fail"] or not (wd / "run.ncdb").is_file():
            return {"error": f"{label}: {x} {(p.stdout + p.stderr)[-300:]}"}
        keep = wd / f"{label}.ncdb"
        shutil.move(wd / "run.ncdb", keep)
        dbs[label] = keep
    merged = wd / "merged_short.ncdb"
    p = subprocess.run([NVC, "--cover-merge", "-o", str(merged), str(dbs["short_seed1"]), str(dbs["short_seed2"])], cwd=wd, env=sim.env, capture_output=True, text=True)
    if p.returncode:
        return {"error": "merge: " + (p.stderr + p.stdout)[-300:]}
    dbs["merged_short"] = merged
    out = {"ops": {"short": small, "full": ops}}
    for label, db in dbs.items():
        xml = wd / f"{label}.cobertura.xml"
        p = subprocess.run([NVC, "--cover-export", "--format=cobertura", "-o", str(xml), str(db)], cwd=wd, env=sim.env, capture_output=True, text=True)
        px = wd / f"{label}.bins.xml"
        p2 = subprocess.run([NVC, "--cover-export", "--format=xml", "-o", str(px), str(db)], cwd=wd, env=sim.env, capture_output=True, text=True)
        if p.returncode or p2.returncode:
            return {"error": "export: " + (p.stderr + p.stdout + p2.stderr)[-300:]}
        out[label] = cobertura(xml)
        out[label]["bins"] = kinds(px)
        if label == "full_seed1":
            shutil.copy(xml, R.HERE / "coverage" / f"{name}.nvc.cobertura.xml")
            rep = wd / "report_full"
            p = subprocess.run([NVC, "--cover-report", "--per-file", "-o", str(rep), str(db)], cwd=wd, env=sim.env, capture_output=True, text=True)
            out[label]["html_report_rc"] = p.returncode
    return out


def bins_from_report(rep: Path) -> dict:
    """Pull the summary percentages (statement, branch, toggle, expression, fsm-state) out of the HTML report's index page."""
    import re
    idx = rep / "index.html"
    if not idx.is_file():
        return {}
    t = re.sub(r"<[^>]+>", " ", idx.read_text())
    t = re.sub(r"\s+", " ", t)
    return {"index_text": t[:900]}


GHDL = str(Path.home() / ".local/bin/ghdl")          # GHDL 4.1.0 mcode (Ubuntu package): the CI pin


def ghdl_parse(path: Path) -> dict:
    """GHDL's coverage file (a JSON-like text with single quotes): {source file: {line: count}}."""
    import re
    out, cur = {}, None
    for l in path.read_text().splitlines():
        m = re.match(r"\s*'file': '(.*)',?$", l)
        if m:
            cur = out.setdefault(m.group(1), {})
            continue
        m = re.match(r"\s*'(\d+)': (\d+),?$", l)
        if m and cur is not None:
            cur[int(m.group(1))] = int(m.group(2))
    return out


def ghdl_merge(paths: list[Path], out: Path) -> None:
    """Union of several GHDL coverage files into one file of the same shape (ghdl coverage 4.1.0 raises CONSTRAINT_ERROR on two inputs)."""
    import re
    tot = {}
    for p in paths:
        for f, lines in ghdl_parse(p).items():
            t = tot.setdefault(f, {})
            for n, c in lines.items():
                t[n] = max(t.get(n, 0), c)       # the file holds hit flags (0/1), not counts: the union is the maximum
    cur, lines_out = None, []
    for l in paths[0].read_text().splitlines():
        m = re.match(r"\s*'file': '(.*)',?$", l)
        if m:
            cur = m.group(1)
        m = re.match(r"(\s*)'(\d+)': (\d+)(,?)$", l)
        if m and cur is not None:
            l = f"{m.group(1)}'{m.group(2)}': {tot[cur][int(m.group(2))]}{m.group(4)}"
        lines_out.append(l)
    out.write_text("\n".join(lines_out) + "\n")


def ghdl_summary(path: Path) -> dict:
    p = subprocess.run([GHDL, "coverage", "--format=summary", str(path)], capture_output=True, text=True)
    import re
    m = re.search(r"Summary: (\d+)/(\d+)", p.stdout)
    return {"hit": int(m.group(1)), "total": int(m.group(2))} if m else {"error": (p.stdout + p.stderr)[-200:]}


def ghdl_design(name: str, d: dict, ops: int, work: Path) -> dict:
    wd = work / f"ghdl_cov__{name}"
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    env = dict(os.environ)
    gl = [f"-g{k}={v}" for k, v in d["gen"].items()]
    p = subprocess.run([GHDL, "-a", "--std=08", "--coverage", f"--workdir={wd}"] + [str(f) for f in d["files"]], cwd=wd, env=env, capture_output=True, text=True)
    if p.returncode:
        return {"error": "analysis: " + (p.stderr + p.stdout)[-300:]}
    small = max(10, ops // 200)
    out, files = {"ops": {"short": small, "full": ops}}, {}
    for label, seed, n in (("short_seed1", 1, small), ("short_seed2", 2, small), ("full_seed1", 1, ops)):
        e = dict(env)
        e.update({"COCOTB_TEST_MODULES": d["bench"], "COCOTB_TOPLEVEL": d["top"], "TOPLEVEL_LANG": "vhdl", "PYTHONPATH": str(R.HERE / "benches"),
                  "PYGPI_PYTHON_BIN": sys.executable, "LIBPYTHON_LOC": R.PYLIB, "COCOTB_RESULTS_FILE": str(wd / "results.xml"),
                  "BENCH_OPS": str(n), "BENCH_SEED": str(seed), "PYTHONDONTWRITEBYTECODE": "1"})
        for old in wd.glob("coverage-*.json"):
            old.unlink()
        p = subprocess.run([GHDL, "-r", "--std=08", "--coverage", f"--workdir={wd}", d["top"]] + gl + [f"--vpi={R.lib('vpi', 'ghdl')}"],
                           cwd=wd, env=e, capture_output=True, text=True)
        x = R.results_xml(wd / "results.xml")
        got = sorted(wd.glob("coverage-*.json"))
        if x["fail"] or not got:
            return {"error": f"{label}: {x} files={[g.name for g in got]} {(p.stdout + p.stderr)[-300:]}"}
        files[label] = wd / f"{label}.cov.json"
        shutil.move(got[0], files[label])
        s = ghdl_summary(files[label])
        pf = ghdl_parse(files[label])
        out[label] = dict(s, files={Path(k).name: {"lines": len(v), "hit": sum(1 for c in v.values() if c)} for k, v in pf.items()})
    ghdl_merge([files["short_seed1"], files["short_seed2"]], wd / "merged_short.cov.json")
    out["merged_short"] = ghdl_summary(wd / "merged_short.cov.json")
    lc = subprocess.run([GHDL, "coverage", "--format=lcov", str(files["full_seed1"])], capture_output=True, text=True)
    (R.HERE / "coverage" / f"{name}.ghdl.lcov").write_text(lc.stdout.replace(str(R.ROOT) + "/", ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", default="")
    ap.add_argument("--ops-scale", type=float, default=0.05)
    ap.add_argument("--out", default=str(R.HERE / "coverage.json"))
    ap.add_argument("--work", default=str(R.ROOT / "build" / "156_cov"))
    a = ap.parse_args()
    (R.HERE / "coverage").mkdir(exist_ok=True)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    res = {"nvc": {}, "ghdl": {}, "tool": "NVC 1.23.1 --cover=" + KINDS + "; GHDL 4.1.0 mcode --coverage"}
    for dn in [x for x in a.designs.split(",") if x] or list(R.DESIGNS):
        d = R.DESIGNS[dn]
        res["nvc"][dn] = nvc_design(dn, d, max(1, int(d["ops"] * a.ops_scale)), work)
        m = res["nvc"][dn]
        print("nvc ", dn, {k: m[k]["lines_hit"] for k in m if isinstance(m[k], dict) and "lines_hit" in m[k]}, m.get("error", ""), flush=True)
        g = res["ghdl"][dn] = ghdl_design(dn, d, max(1, int(d["ops"] * a.ops_scale)), work)
        print("ghdl", dn, {k: f"{g[k].get('hit')}/{g[k].get('total')}" for k in g if isinstance(g[k], dict) and "total" in g[k]}, g.get("error", ""), flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
