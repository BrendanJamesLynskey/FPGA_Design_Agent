"""Run a cocotb test module against RTL with Icarus, from pytest.

Every RTL test in the repo goes through :func:`run`, so CI and a local
``pytest`` run the same thing. Results land in ``build/sim/<name>/``.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner

ROOT = Path(__file__).resolve().parents[1]
SHELL_RTL = sorted((ROOT / "shell" / "rtl").glob("*.sv"))


def failure_excerpt(log: Path, limit: int = 3500) -> str:
    """The failing tests of a cocotb simulator log, raw: each line that reports a failure with the traceback lines
    that follow it (no interpretation); the log's tail if none is recognised."""
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError as e:
        return f"(no simulator log: {e.strerror or e})"
    out: list[str] = []
    for i, l in enumerate(lines):
        if re.search(r"\bFAIL\b|failed\b|Traceback|Error\b|error:", l) and "Failed 0" not in l:
            out += [x.rstrip() for x in lines[i:i + 14]]
            if len(out) > 60:
                break
    text = "\n".join(dict.fromkeys(out)) if out else "\n".join(lines[-40:])
    return text[:limit]


def collect_results(build_dir: Path, seed: int | None, dest_root: Path | None = None) -> Path | None:
    """Copy this run's ``results.xml`` to ``<dest>/seed<N>/results.xml``, the place flow/verif_gates.py reads (V2/V3).

    ``dest`` is ``$FDA_SIM_RESULTS_DIR`` (set by the agent's ``simulate`` tool to ``<design>/build/verif/sim``); with
    it unset nothing is copied, so CI and local pytest runs are unchanged. Several runs of one seed (a directed bench
    and a random one) are merged into one file: a test case with the same class and name is replaced. A run without a
    seed counts as seed 1. Returns the destination file, or None when there was nothing to copy."""
    if dest_root is None:
        env = os.environ.get("FDA_SIM_RESULTS_DIR")
        if not env:
            return None
        dest_root = Path(env) if Path(env).is_absolute() else ROOT / env
    src = build_dir / "results.xml"
    if not src.is_file():
        return None
    out = dest_root / f"seed{1 if seed is None else seed}" / "results.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    # 05j: the coverage evidence of this run goes next to the results (the gate reads seed*/coverage*.dat and
    # seed*/coverage*.yml); a second run of the same seed keeps its file under a numbered name instead of overwriting
    for name, stem, ext in (("coverage.dat", "coverage", ".dat"), ("coverage_func.yml", "coverage_func", ".yml")):
        if (build_dir / name).is_file():
            n, dst = 1, out.parent / name
            while dst.exists():
                n += 1
                dst = out.parent / f"{stem}_{n}{ext}"
            shutil.copy(build_dir / name, dst)
    new = ET.parse(src).getroot()
    if not out.is_file():
        ET.ElementTree(new).write(out, encoding="utf-8", xml_declaration=True)
        return out
    tree = ET.parse(out)
    root = tree.getroot()
    suite = next(root.iter("testsuite"), root)
    have = {(tc.get("classname"), tc.get("name")): tc for tc in root.iter("testcase")}
    for tc in new.iter("testcase"):
        old = have.get((tc.get("classname"), tc.get("name")))
        if old is not None:
            old[:] = list(tc)
            old.attrib.update(tc.attrib)
        else:
            suite.append(copy.deepcopy(tc))
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out


def run(name: str, toplevel: str, sources: list[Path], test_module: str, test_dir: Path,
        parameters: dict[str, object] | None = None, testcase: str | list[str] | None = None,
        seed: int | None = None, build_root: Path | None = None, extra_env: dict[str, str] | None = None,
        coverage: bool | None = None) -> None:
    """Build ``sources`` with $SIM (icarus by default; verilator needs 5.036+ for cocotb 2) and run
    ``test_module`` (a name or a list of names); fail if any test failed.

    ``coverage=None`` follows ``$FDA_COVERAGE`` (set by the agent's ``simulate(coverage=True)``). The bench can export
    its functional-coverage bins to ``$FDA_COV_OUT`` (cocotb-coverage ``coverage_db.export_to_yaml``). With ``coverage`` (Verilator only) the build is instrumented for line and toggle coverage and the run
    writes ``<build_dir>/coverage.dat``. Under Verilator, warnings are not fatal (the repo's lint gate is
    flow/lint.sh) and concurrent assertions are on."""
    simname = os.environ.get("SIM", "icarus")
    if coverage is None:
        coverage = os.environ.get("FDA_COVERAGE") == "1"
    sim = get_runner(simname)
    build_dir = (build_root or ROOT / "build" / "sim") / name
    if simname == "verilator":
        args = ["--assert", "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-TIMESCALEMOD", "-j", "1"]
        if coverage:
            args += ["--coverage-line", "--coverage-toggle", "--coverage-user"]
    else:
        args = ["-g2012"]
    args += [f"-I{d}" for d in sorted({str(Path(s).parent) for s in sources})]     # `include "x.svh" next to a source
    sim.build(sources=[str(s) for s in sources], hdl_toplevel=toplevel, parameters=parameters or {},
              build_dir=build_dir, timescale=("1ns", "1ps"), always=True, build_args=args)
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(test_dir), os.environ.get("PYTHONPATH", "")])}
    env["FDA_COV_OUT"] = str(build_dir / "coverage_func.yml")
    env.update(extra_env or {})
    plus = [f"+verilator+coverage+file+{build_dir / 'coverage.dat'}"] if (simname == "verilator" and coverage) else []
    try:
        results = sim.test(test_module=test_module, hdl_toplevel=toplevel, testcase=testcase, seed=seed,
                           build_dir=build_dir, test_dir=test_dir, extra_env=env, parameters=parameters or {},
                           timescale=("1ns", "1ps"), results_xml=str(build_dir / "results.xml"),
                           log_file=build_dir / "sim.log", plusargs=plus)
    except SystemExit:
        collect_results(build_dir, seed)         # a failing run is evidence too: the gate reads the failures
        # cocotb's runner exits with only "Failed n of m tests"; the failing assertions and tracebacks are in the
        # simulator log, which lives in a scratch directory the caller never sees. Say what they are.
        raise AssertionError(f"{name}: the cocotb run failed. From {build_dir / 'sim.log'}:\n"
                             + failure_excerpt(build_dir / "sim.log")) from None
    collect_results(build_dir, seed)
    n_tests, n_fail = get_results(results)
    assert n_tests > 0, f"{name}: no cocotb tests ran"
    assert n_fail == 0, f"{name}: {n_fail} of {n_tests} cocotb tests failed (see {build_dir / 'sim.log'})"
