"""Run a cocotb test module against RTL with Icarus, from pytest.

Every RTL test in the repo goes through :func:`run`, so CI and a local
``pytest`` run the same thing. Results land in ``build/sim/<name>/``.
"""

from __future__ import annotations

import os
import re
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


def run(name: str, toplevel: str, sources: list[Path], test_module: str, test_dir: Path,
        parameters: dict[str, object] | None = None, testcase: str | list[str] | None = None,
        seed: int | None = None, build_root: Path | None = None, extra_env: dict[str, str] | None = None,
        coverage: bool = False) -> None:
    """Build ``sources`` with $SIM (icarus by default; verilator needs 5.036+ for cocotb 2) and run
    ``test_module`` (a name or a list of names); fail if any test failed.

    With ``coverage`` (Verilator only) the build is instrumented for line and toggle coverage and the run
    writes ``<build_dir>/coverage.dat``. Under Verilator, warnings are not fatal (the repo's lint gate is
    flow/lint.sh) and concurrent assertions are on."""
    simname = os.environ.get("SIM", "icarus")
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
    env.update(extra_env or {})
    plus = [f"+verilator+coverage+file+{build_dir / 'coverage.dat'}"] if (simname == "verilator" and coverage) else []
    try:
        results = sim.test(test_module=test_module, hdl_toplevel=toplevel, testcase=testcase, seed=seed,
                           build_dir=build_dir, test_dir=test_dir, extra_env=env, parameters=parameters or {},
                           timescale=("1ns", "1ps"), results_xml=str(build_dir / "results.xml"),
                           log_file=build_dir / "sim.log", plusargs=plus)
    except SystemExit:
        # cocotb's runner exits with only "Failed n of m tests"; the failing assertions and tracebacks are in the
        # simulator log, which lives in a scratch directory the caller never sees. Say what they are.
        raise AssertionError(f"{name}: the cocotb run failed. From {build_dir / 'sim.log'}:\n"
                             + failure_excerpt(build_dir / "sim.log")) from None
    n_tests, n_fail = get_results(results)
    assert n_tests > 0, f"{name}: no cocotb tests ran"
    assert n_fail == 0, f"{name}: {n_fail} of {n_tests} cocotb tests failed (see {build_dir / 'sim.log'})"
