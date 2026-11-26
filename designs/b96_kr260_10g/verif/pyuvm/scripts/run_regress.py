#!/usr/bin/env python3
"""The one-command regression of the pyuvm bench (brief 123): build, run every test over its seeds, merge the coverage, optionally run the seeded-bug set.

    run_regress.py [--out DIR] [--seeds N] [--rand N] [--quick] [--mutants] [--mutants-only] [--only "M01 M02"] [--blind] [--record DIR]

  --seeds N     seeds per directed test (default 2); --rand N seeds for each constrained-random test (default 10); --quick = 1 and 3
  --mutants     afterwards build and run each mutant of ../uvm/mutants/mutants.tsv (brief 112's file, the same 17 bugs) until a test fails
  --blind       the mutant run uses the tests without the two patterns 112 added after seeing M13 and M15 survive (PYUVM_BLIND=1); writes mutants_blind.tsv
  --record DIR  copy the compact records into DIR
Same machine rule as 112's script for simulation-only runs: wait while the 1-minute load is 6 or more or less than 12 GB is free (up to 30 minutes a run)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYUVM = HERE.parent
DESIGN = PYUVM.parents[1]
ROOT = DESIGN.parents[1]
sys.path.insert(0, str(ROOT))

DIRECTED = ["t_smoke", "t_lens", "t_gaps", "t_badfcs", "t_underrun", "t_xg", "t_line_blocks", "t_hdr", "t_slip", "t_ber", "t_rxreset", "t_offsets"]
RANDOMT = ["t_rand", "t_rand_line"]
MUT_TESTS = [("t_smoke", 1), ("t_lens", 1), ("t_xg", 1), ("t_line_blocks", 1), ("t_hdr", 1), ("t_badfcs", 1), ("t_gaps", 1), ("t_offsets", 1), ("t_rxreset", 1), ("t_slip", 1),
             ("t_ber", 1), ("t_rand", 1), ("t_rand", 2), ("t_rand_line", 1), ("t_rand_line", 2),
             ("t_underrun", 1)]          # brief 158: last in the order, so every earlier kill is the same as in brief 123's record


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


pyuvm_run = _load("pyuvm_run", HERE / "pyuvm_run.py")
mutate = _load("mutate", DESIGN / "verif" / "uvm" / "scripts" / "mutate.py")


def wait_for_machine() -> None:
    for _ in range(90):
        load = float(Path("/proc/loadavg").read_text().split()[0])
        avail = next(int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemAvailable")) / 1048576
        if load < 6 and avail > 12:
            return
        time.sleep(20)
    sys.exit("machine busy (load >= 6 or under 12 GB free) for 30 minutes: stopping")


def sim_ns(xml: Path) -> float:
    try:
        return max(float(t.get("sim_time_ns", "0")) for t in ET.parse(xml).getroot().iter("testcase"))
    except Exception:
        return 0.0


def one(build: Path, test: str, seed: int, out: Path, rtl_dir: Path | None = None):
    wait_for_machine()
    run_dir = out / f"{test}_{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    ok, wall, xml = pyuvm_run.run(build, test, seed, run_dir, rtl_dir, test_dir=run_dir if os.environ.get("SIM", "icarus") == "verilator" else None)
    js = run_dir / f"{test}_seed{seed}.json"
    rec = json.loads(js.read_text()) if js.exists() else None
    return ok, wall, sim_ns(xml), rec


def merge_coverage(out: Path, files: list[Path]) -> dict:
    from cocotb_coverage.coverage import merge_coverage as mc
    import yaml
    merged = out / "coverage_merged.yml"
    mc(logging.getLogger("merge").info, str(merged), *[str(f) for f in files])
    data = yaml.safe_load(merged.read_text())
    pts = {}
    for name, v in data.items():
        if "bins:_hits" in v:
            pts[name] = {str(b): h for b, h in v["bins:_hits"].items()}
    return pts


def write_cov_report(out: Path, pts: dict, nruns: int) -> str:
    rows = ["| coverage point | bins | hit | hit % |", "|---|---|---|---|"]
    tot = hit = 0
    holes = []
    for name in sorted(pts):
        b = pts[name]
        h = sum(1 for x in b.values() if x > 0)
        tot += len(b); hit += h
        holes += [f"{name}|{k}" for k, x in b.items() if x == 0]
        rows.append(f"| {name} | {len(b)} | {h} | {100.0 * h / len(b):.1f} % |")
    (out / "coverage_merged.tsv").write_text("".join(f"{n}|{k}\t{x}\n" for n in sorted(pts) for k, x in pts[n].items()))
    text = f"# Merged functional coverage (cocotb-coverage), {nruns} runs\n\n**{hit} of {tot} bins hit**, {len(holes)} open holes.\n\n" + "\n".join(rows) + "\n"
    if holes:
        text += "\n## Open holes\n\n" + "\n".join(f"- `{h}`" for h in holes) + "\n"
    (out / "coverage_report.md").write_text(text)
    return f"merged {nruns} runs: {hit}/{tot} bins hit, {len(holes)} open holes"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PYUVM / "build")); ap.add_argument("--seeds", type=int, default=2); ap.add_argument("--rand", type=int, default=10)
    ap.add_argument("--quick", action="store_true"); ap.add_argument("--mutants", action="store_true"); ap.add_argument("--mutants-only", action="store_true")
    ap.add_argument("--only", default=""); ap.add_argument("--blind", action="store_true"); ap.add_argument("--record", default="")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    seeds, rand = (1, 3) if a.quick else (a.seeds, a.rand)
    summary: list[str] = []
    nfail = 0
    t_start = time.time()
    if not a.mutants_only:
        print("== build (clean RTL)")
        bt = pyuvm_run.build(out / "build_clean")
        print(f"   build {bt:.1f} s")
        rows = ["test\tseed\tresult\terrors\twall_s\tsim_ns"]
        jsons = []
        print("== regression")
        for t, n in [(t, seeds) for t in DIRECTED] + [(t, rand) for t in RANDOMT]:
            for s in range(1, n + 1):
                ok, wall, ns, rec = one(out / "build_clean", t, s, out / "runs")
                nfail += not ok
                rows.append(f"{t}\t{s}\t{'PASS' if ok else 'FAIL'}\t{rec['errors'] if rec else '-'}\t{wall:.1f}\t{ns:.0f}")
                print(f"  {t} seed {s}: {'PASS' if ok else 'FAIL'} {wall:.1f} s")
                if rec:
                    jsons.append(rec)
        (out / "results.tsv").write_text("\n".join(rows) + "\n")
        comp, mism = {}, {}
        for r in jsons:
            for k, v in r["compared"].items(): comp[k] = comp.get(k, 0) + v
            for k, v in r["mismatch"].items(): mism[k] = mism.get(k, 0) + v
        (out / "scoreboard_totals.tsv").write_text("".join(f"{k}\t{comp[k]}\t{mism[k]}\n" for k in sorted(comp)))
        pc = {}
        for r in jsons:
            for k, v in r["protocol_cover"].items(): pc[k] = pc.get(k, 0) + v
        (out / "protocol_cover.tsv").write_text("".join(f"{k}\t{v}\n" for k, v in sorted(pc.items())))
        pf = sum(sum(r["protocol_fails"].values()) for r in jsons)
        files = sorted((out / "runs").glob("*/cov_*.yml"))
        cov_line = write_cov_report(out, merge_coverage(out, files), len(files))
        total_wall = sum(float(r.split("\t")[4]) for r in rows[1:])
        summary += [f"regression: {len(rows) - 1} runs, {nfail} failed", "scoreboard checks (check, comparisons, mismatches):"]
        summary += [f"  {k}\t{comp[k]}\t{mism[k]}" for k in sorted(comp)]
        summary += [f"protocol checker: {pf} failures", cov_line, f"simulator wall time, summed over runs: {total_wall:.0f} s"]
    if a.mutants or a.mutants_only:
        if a.blind:
            os.environ["PYUVM_BLIND"] = "1"
        print("== mutants" + (" (blind: without 112's two hindsight patterns)" if a.blind else ""))
        rows = ["id\tverdict\tkilled_by\tchecks_that_fired\truns\twall_s\twhat"]
        seen = {}
        for mid, fn, _o, _n, what in mutate.rows():
            seen.setdefault(mid, what)
        for mid, what in seen.items():
            if a.only and mid not in a.only.split():
                continue
            mdir = out / ("mut_blind" if a.blind else "mut") / mid
            if mutate.main(["mutate.py", "make", mid, str(DESIGN / "rtl"), str(mdir / "rtl")]) != 0:
                rows.append(f"{mid}\tNOT_APPLIED\t-\t-\t0\t0\t{what}"); continue
            try:
                pyuvm_run.build(mdir / "build", mdir / "rtl")
            except Exception as e:
                rows.append(f"{mid}\tBUILD_FAIL\t-\t-\t0\t0\t{what}"); print(f"  {mid}: does not build ({e})"); continue
            verdict, by, fired, nr, wall_m = "SURVIVED", "-", "-", 0, 0.0
            for t, s in MUT_TESTS:
                ok, wall, _ns, rec = one(mdir / "build", t, s, mdir / "runs", mdir / "rtl")
                nr += 1; wall_m += wall
                if not ok:
                    verdict, by = "KILLED", f"{t} seed {s}"
                    if rec:
                        f = [k for k, v in rec["mismatch"].items() if v] + (["SVA"] if sum(rec["protocol_fails"].values()) else [])
                        fired = " ".join(sorted(f)) or "-"
                    break
            print(f"  {mid}: {verdict} ({by}) checks: {fired}")
            rows.append(f"{mid}\t{verdict}\t{by}\t{fired}\t{nr}\t{wall_m:.0f}\t{what}")
        name = "mutants_blind.tsv" if a.blind else "mutants.tsv"
        (out / name).write_text("\n".join(rows) + "\n")
        killed = sum(1 for r in rows[1:] if r.split("\t")[1] == "KILLED")
        summary.append(f"mutants killed{' (blind)' if a.blind else ''}: {killed} of {len(rows) - 1}")
    summary.append(f"total wall time of this invocation: {time.time() - t_start:.0f} s")
    text = "\n".join(summary) + "\n"
    (out / ("summary_mutants_blind.txt" if a.blind else "summary.txt")).write_text(text)
    print(text)
    if a.record:
        rec = Path(a.record); rec.mkdir(parents=True, exist_ok=True)
        for f in ["results.tsv", "summary.txt", "summary_mutants_blind.txt", "coverage_report.md", "coverage_merged.tsv", "scoreboard_totals.tsv", "protocol_cover.tsv", "mutants.tsv", "mutants_blind.tsv"]:
            if (out / f).exists():
                shutil.copy(out / f, rec / f)
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
