#!/usr/bin/env python3
"""Brief 156: the same cocotb benches on GHDL (mcode 4.1.0, LLVM 7.0.0-dev) and NVC (1.23.1), timed.

    python3 results/156_vhdl_tools/run_sims.py [--reps 3] [--designs a,b] [--sims s1,s2] [--out sim_compare.json]

For each design and simulator: build (analysis + elaboration command), a start-up run (BENCH_OPS=0: simulator start, elaboration for
the mcode and JIT flows, cocotb start, reset), and a workload run (BENCH_OPS=N). Each is repeated ``reps`` times; the table reports the
median. Pass/fail comes from cocotb's results.xml; the per-clock trace digest (benches/common.py Trace) is compared across simulators.
Run it under ``systemd-run --user --scope -p MemoryMax=4G nice -n 15`` (one job at a time); the driver itself starts one process at a time.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
T55 = ROOT / "results" / "55_vhdl" / "translations" / "A"
NVC_ENV = Path.home() / ".local/opt/nvc-1.23.1/env.sh"
OSS = Path.home() / ".local/opt/oss-cad-suite"

DESIGNS = {
    "sync_fifo_regs": dict(top="sync_fifo_regs", bench="bench_sync_fifo_regs", ops=40000, gen={},
                           files=[T55 / "t1_sync_fifo_regs/rtl/sync_fifo_regs.vhd"]),
    "gray_stepper": dict(top="gray_stepper", bench="bench_gray_stepper", ops=1500, gen={"DEBOUNCE_CYCLES": 6, "TICK_CYCLES": 4},
                         files=[T55 / "t1_gray_stepper/rtl" / f for f in ("sync2.vhd", "bm_debounce.vhd", "gray_stepper.vhd")]),
    "debounce_bank": dict(top="debounce_bank", bench="bench_debounce_bank", ops=4000, gen={"DEBOUNCE_CYCLES": 6},
                          files=[T55 / "t1_debounce_bank/rtl" / f for f in ("sync2.vhd", "bm_debounce.vhd", "debounce_bank.vhd")]),
    "elevator_fsm": dict(top="elevator_fsm", bench="bench_elevator_fsm", ops=300, gen={"FLOOR_CYCLES": 6, "DOOR_CYCLES": 10},
                         files=[T55 / "t1_elevator_fsm/rtl" / f for f in ("sync2.vhd", "elevator_fsm.vhd")]),
    "axil_regs": dict(top="axil_regs", bench="bench_axil_regs", ops=8000, gen={},
                      files=[T55 / "axil_regs/rtl/axil_regs.vhd"]),
    "fir16": dict(top="fir16", bench="bench_fir16", ops=6000, gen={},
                  files=[HERE / "rtl" / f for f in ("fir_pkg.vhd", "fir_add_tree.vhd", "fir16.vhd")]),
}

# one hand-written fault per design (file, old text, new text); every simulator must fail the bench on it
MUTANTS = {
    "sync_fifo_regs": ("sync_fifo_regs.vhd", "level <= level + to_unsigned(1, level'length);", "level <= level + to_unsigned(2, level'length);"),
    "gray_stepper": ("gray_stepper.vhd", "else bin + to_unsigned(1, 10);", "else bin + to_unsigned(2, 10);"),
    "debounce_bank": ("debounce_bank.vhd", "cnt(k) <= cnt(k) + 1;", "cnt(k) <= cnt(k) + 2;"),
    "elevator_fsm": ("elevator_fsm.vhd", "moves <= moves + 1;", "moves <= moves + 2;"),
    "axil_regs": ("axil_regs.vhd", "r3 <= r0 xor r1 xor r2;", "r3 <= r0 xor r1;"),
    "fir16": ("fir16.vhd", "shift_right(tree_s, 10)", "shift_right(tree_s, 9)"),
}

PYLIB = subprocess.run([sys.executable, "-m", "cocotb_tools.config", "--libpython"], capture_output=True, text=True).stdout.strip()


def lib(kind: str, sim: str) -> str:
    return subprocess.run([sys.executable, "-m", "cocotb_tools.config", "--lib-name-path", kind, sim],
                          capture_output=True, text=True).stdout.strip()


def nvc_env() -> dict:
    """The environment env.sh would set (read by hand: sourcing is a shell thing)."""
    home = Path.home() / ".local/opt/nvc-1.23.1/root/usr"
    e = dict(os.environ)
    e["PATH"] = f"{home}/bin:{e['PATH']}"
    e["LD_LIBRARY_PATH"] = f"{home}/lib:{e.get('LD_LIBRARY_PATH', '')}"
    e["NVC_LIBPATH"] = f"{home}/lib/x86_64-linux-gnu/nvc"
    return e


def ghdl_llvm_env() -> dict:
    e = dict(os.environ)
    e["PATH"] = f"{OSS}/bin:{e['PATH']}"
    return e


class Sim:
    """A way of building and running a VHDL design under cocotb. build() returns a list of commands; run() a command."""

    def __init__(self, name, exe, env, kind):
        self.name, self.exe, self.env, self.kind = name, exe, env, kind

    def version(self) -> str:
        r = subprocess.run([self.exe, "--version"], capture_output=True, text=True, env=self.env)
        return " | ".join(l.strip() for l in r.stdout.splitlines()[:3] if l.strip())

    def build_cmds(self, d, wd: Path, gen) -> list[list[str]]:
        files = [str(f) for f in d["files"]]
        gl = [f"-g{k}={v}" for k, v in gen.items()]
        if self.kind in ("ghdl-mcode", "ghdl-llvm"):
            return [[self.exe, "-a", "--std=08", f"--workdir={wd}"] + files,
                    [self.exe, "-e", "--std=08", f"--workdir={wd}"] + (gl if self.kind == "ghdl-mcode" else []) + [d["top"]]]   # LLVM: -g goes to the run
        w = f"--work=work:{wd}/work"
        c = [[self.exe, "--std=2008", w, "-a", "--preserve-case"] + files]
        if self.kind == "nvc-aot":           # elaborate to a native shared library, as plain `nvc -e` does
            c.append([self.exe, "--std=2008", w, "-e"] + gl + [d["top"]])
        return c                              # nvc-jit: cocotb's own flow elaborates inside the run command (-e --no-save ... -r)

    def run_cmd(self, d, wd: Path, gen) -> list[str]:
        gl = [f"-g{k}={v}" for k, v in gen.items()]
        if self.kind in ("ghdl-mcode", "ghdl-llvm"):
            return [self.exe, "-r", "--std=08", f"--workdir={wd}", d["top"]] + gl + [f"--vpi={lib('vpi', 'ghdl')}"]
        w = f"--work=work:{wd}/work"
        if self.kind == "nvc-jit":
            return [self.exe, "--std=2008", w, "-e", "--no-save"] + gl + [d["top"], "-r", "--load", lib("vhpi", "nvc")]
        return [self.exe, "--std=2008", w, "-r", "--load", lib("vhpi", "nvc"), d["top"]]


def sims(which: list[str]) -> list[Sim]:
    allsims = [
        Sim("ghdl-4.1.0-mcode", str(Path.home() / ".local/bin/ghdl"), dict(os.environ), "ghdl-mcode"),
        Sim("ghdl-7.0.0dev-llvm", str(OSS / "bin/ghdl"), ghdl_llvm_env(), "ghdl-llvm"),
        Sim("nvc-1.23.1-jit", str(Path.home() / ".local/opt/nvc-1.23.1/root/usr/bin/nvc"), nvc_env(), "nvc-jit"),
        Sim("nvc-1.23.1-aot", str(Path.home() / ".local/opt/nvc-1.23.1/root/usr/bin/nvc"), nvc_env(), "nvc-aot"),
    ]
    return [s for s in allsims if not which or s.name in which or s.kind in which]


def results_xml(p: Path) -> dict:
    if not p.is_file():
        return {"tests": 0, "fail": 0, "error": "no results.xml"}
    r = ET.parse(p).getroot()
    cases = list(r.iter("testcase"))
    fails = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    msg = None
    if fails:
        f = fails[0].find("failure")
        f = f if f is not None else fails[0].find("error")
        msg = (f.get("message") or f.text or "")[:300]
    return {"tests": len(cases), "fail": len(fails), "message": msg}


def mutated(name: str, d: dict, work: Path) -> dict:
    """A copy of the design with its one fault applied (the sources are copied; the originals are untouched)."""
    fn, old, new = MUTANTS[name]
    md = work / f"mutant__{name}"
    if md.exists():
        shutil.rmtree(md)
    md.mkdir(parents=True)
    files = []
    hit = 0
    for f in d["files"]:
        t = Path(f).read_text()
        if Path(f).name == fn:
            assert t.count(old) == 1, f"{fn}: the text to mutate occurs {t.count(old)} times"
            t = t.replace(old, new)
            hit += 1
        (md / Path(f).name).write_text(t)
        files.append(md / Path(f).name)
    assert hit == 1
    return dict(d, files=files)


def one(sim: Sim, name: str, d: dict, ops: int, work: Path, seed: int = 1, gen=None, tag: str = "") -> dict:
    gen = d["gen"] if gen is None else gen
    wd = work / f"{sim.name}__{name}{tag}"
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    # build
    t0 = time.perf_counter()
    for c in sim.build_cmds(d, wd, gen):
        r = subprocess.run(c, cwd=wd, env=sim.env, capture_output=True, text=True)
        if r.returncode:
            return {"build_ok": False, "error": (r.stderr or r.stdout)[-600:], "cmd": " ".join(c)}
    build_s = time.perf_counter() - t0
    out = {"build_ok": True, "build_s": build_s}
    env = dict(sim.env)
    env.update({"COCOTB_TEST_MODULES": d["bench"], "COCOTB_TOPLEVEL": d["top"], "TOPLEVEL_LANG": "vhdl",
                "PYTHONPATH": f"{HERE / 'benches'}", "PYGPI_PYTHON_BIN": sys.executable, "LIBPYTHON_LOC": PYLIB, "COCOTB_RESULTS_FILE": str(wd / "results.xml"),
                "BENCH_SEED": str(seed), "BENCH_OUT": str(wd / "trace"), "PYTHONDONTWRITEBYTECODE": "1", "BENCH_TRACE_ALL": os.environ.get("BENCH_TRACE_ALL", "0")})
    for label, n in (("start", 0), ("work", ops)):
        env["BENCH_OPS"] = str(n)
        t0 = time.perf_counter()
        r = subprocess.run(sim.run_cmd(d, wd, gen), cwd=wd, env=env, capture_output=True, text=True)
        dt = time.perf_counter() - t0
        out[f"{label}_s"] = dt
        out[f"{label}_rc"] = r.returncode
        psl = [l for l in (r.stdout + r.stderr).splitlines() if re.search(r"psl assertion", l, re.I)]
        out[f"{label}_psl_failures"] = len(psl)
        if psl:
            out[f"{label}_psl_first"] = psl[0].strip()[:160]
        out[f"{label}_xml"] = results_xml(wd / "results.xml")
        tf = wd / "trace" / f"{d['top']}.trace.json"
        if tf.is_file():
            out[f"{label}_trace"] = json.loads(tf.read_text())
        if r.returncode or out[f"{label}_xml"]["fail"]:
            out[f"{label}_log_tail"] = (r.stdout + r.stderr)[-3500:]
        (wd / "results.xml").unlink(missing_ok=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--designs", default="")
    ap.add_argument("--sims", default="")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply every design's workload")
    ap.add_argument("--mutants", action="store_true", help="run each design's fault instead of the design (every simulator must fail it)")
    ap.add_argument("--out", default=str(HERE / "sim_compare.json"))
    ap.add_argument("--work", default=str(ROOT / "build" / "156_sims"))
    a = ap.parse_args()
    ds = [x for x in a.designs.split(",") if x] or list(DESIGNS)
    ss = sims([x for x in a.sims.split(",") if x])
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    res = {"date": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "reps": a.reps, "scale": a.scale, "mutants": a.mutants, "machine": "i7-3770 workstation",
           "versions": {s.name: s.version() for s in ss}, "designs": {}}
    for dn in ds:
        d = DESIGNS[dn]
        if a.mutants:
            d = mutated(dn, d, work)
        ops = int(d["ops"] * a.scale)
        res["designs"][dn] = {"ops": ops, "sims": {}}
        for s in ss:
            reps = [one(s, dn, d, ops, work, tag="__mutant" if a.mutants else "") for _ in range(a.reps)]
            ok = [r for r in reps if r.get("build_ok")]
            row = {"reps": reps}
            if ok:
                for k in ("build_s", "start_s", "work_s"):
                    row[f"{k}_median"] = statistics.median(r[k] for r in ok)
                row["sim_s_median"] = statistics.median(r["work_s"] - r["start_s"] for r in ok)
            res["designs"][dn]["sims"][s.name] = row
            w = reps[0].get("work_xml", {})
            print(f"{dn:15s} {s.name:20s} build {row.get('build_s_median', float('nan')):6.2f}  start {row.get('start_s_median', float('nan')):6.2f}  "
                  f"work {row.get('work_s_median', float('nan')):6.2f}  tests {w.get('tests')} fail {w.get('fail')}", flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
