#!/usr/bin/env python3
"""Run a benchmark task's hidden acceptance bench against an RTL directory.

    python3 benchmark/tools/run_task.py <task_dir> [--rtl DIR] [--sim icarus|verilator] [--seed N] [--json OUT]

<task_dir> holds spec.md (what the agent sees) and hidden/ (bench.yaml, model.py, the cocotb module, an optional
SystemVerilog wrapper). Without --rtl the task's reference RTL (ref/rtl) is used. The RTL under test is every *.sv
and *.v in the directory plus the test shell (shell/rtl); its top must be the one hidden/bench.yaml names, with the
parameters it lists. Results: per-test pass/fail from cocotb's results.xml, never from any agent output.

The same entry scores an agent's design (--rtl <its rtl dir>), checks the reference, and runs mutants and trap
variants (benchmark/tools/mutants.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# The shell a score is tied to. Normally this tree's; FDA_GRADER_SHELL names a checked-out frozen copy (a repository root that
# holds shell/) while the agent's own shell moves on (benchmark/tools/shell_freeze.py, brief 15).
SHELL_ROOT = Path(os.environ.get("FDA_GRADER_SHELL") or ROOT).resolve()
SIM_STUBS = ROOT / "benchmark" / "lib" / "sim"


def load_bench(task: Path) -> dict:
    return yaml.safe_load((task / "hidden" / "bench.yaml").read_text())


def sources(task: Path, rtl: Path) -> list[Path]:
    b = load_bench(task)
    src = sorted((SHELL_ROOT / "shell" / "rtl").glob("*.sv"))
    taken = {s.name for s in src}
    own = sorted(p for p in rtl.iterdir() if p.suffix in (".sv", ".v"))
    clash = sorted(p.name for p in own if p.name in taken)
    if clash:                   # used to be dropped silently in favour of the shell's file, which hid the collision
        raise ValueError(f"{rtl}: file name(s) {', '.join(clash)} also name a test-shell file; rename them (the shell's own "
                         f"modules are compiled into every build)")
    src += own
    for stub in b.get("sim_stubs", []):
        src.append(SIM_STUBS / stub)
    if b.get("wrapper"):
        src.append(task / "hidden" / b["wrapper"])
    return src


def parse_results(xml: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if not xml.exists():
        return out
    for tc in ET.parse(xml).getroot().iter("testcase"):
        name = tc.get("name", "?")
        bad = tc.find("failure") is not None or tc.find("error") is not None
        out[name] = not bad
    return out


def run(task: Path, rtl: Path | None = None, sim: str | None = None, seed: int = 1, tag: str = "ref",
        testcase: list[str] | None = None, build_root: Path | None = None) -> dict:
    from cocotb_tools.runner import get_runner

    task = task.resolve()
    rtl = (rtl or task / "ref" / "rtl").resolve()
    b = load_bench(task)
    simname = sim or os.environ.get("SIM", "icarus")
    runner = get_runner(simname)
    build_dir = (build_root or ROOT / "build" / "bench_sim") / f"{task.name}__{tag}__{simname}"
    if simname == "verilator":
        args = ["-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-TIMESCALEMOD", "-j", "2"]
    else:
        args = ["-g2012"]
    try:
        srcs = sources(task, rtl)
    except ValueError as e:                         # a name that collides with the shell: an error, not a silent swap
        result = {"task": task.name, "tag": tag, "sim": simname, "seed": seed, "rtl": str(rtl), "built": False,
                  "tests": {}, "pass": False, "error": f"build failed: {e}"}
        return result
    args += [f"-I{d}" for d in sorted({str(s.parent) for s in srcs})]
    params = dict(b.get("parameters") or {})
    result = {"task": task.name, "tag": tag, "sim": simname, "seed": seed, "rtl": str(rtl), "built": False,
              "tests": {}, "pass": False}
    try:
        runner.build(sources=[str(s) for s in srcs], hdl_toplevel=b["toplevel"], parameters=params,
                     build_dir=build_dir, timescale=("1ns", "1ps"), always=True, build_args=args,
                     log_file=build_dir / "build.log")
    except (SystemExit, Exception) as e:          # a design that does not build fails every test
        result["error"] = f"build failed: {e}"
        return result
    result["built"] = True
    pre = [str(ROOT)]
    if SHELL_ROOT != ROOT:                          # only the shell package comes from the frozen copy, not the whole tree
        link = build_dir / "grader_shell"
        link.mkdir(parents=True, exist_ok=True)
        target = SHELL_ROOT / "shell"
        if (link / "shell").is_symlink() and (link / "shell").resolve() != target:
            (link / "shell").unlink()
        if not (link / "shell").is_symlink():
            (link / "shell").symlink_to(target)
        pre.insert(0, str(link))
    env = {"PYTHONPATH": os.pathsep.join([*pre, str(task / "hidden"), os.environ.get("PYTHONPATH", "")]),
           "BENCH_TASK": str(task)}
    xml = build_dir / "results.xml"
    xml.unlink(missing_ok=True)
    try:
        runner.test(test_module=b.get("module", "acceptance"), hdl_toplevel=b["toplevel"], testcase=testcase,
                    seed=seed, build_dir=build_dir, test_dir=task / "hidden", extra_env=env, parameters=params,
                    timescale=("1ns", "1ps"), results_xml=str(xml), log_file=build_dir / "sim.log")
    except SystemExit:
        pass
    result["tests"] = parse_results(xml)
    result["pass"] = bool(result["tests"]) and all(result["tests"].values())
    result["log"] = str(build_dir / "sim.log")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task", type=Path)
    ap.add_argument("--rtl", type=Path)
    ap.add_argument("--sim", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default="ref")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    r = run(a.task, a.rtl, a.sim, a.seed, a.tag)
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    for t, ok in r["tests"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {t}")
    print(f"{r['task']} [{r['tag']}, {r['sim']}]: {'PASS' if r['pass'] else 'FAIL'}"
          f" ({sum(r['tests'].values())}/{len(r['tests'])} tests){'; ' + r['error'] if 'error' in r else ''}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
