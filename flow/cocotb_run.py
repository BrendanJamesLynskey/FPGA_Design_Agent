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

from flow import cdc_inject, srcorder

ROOT = Path(__file__).resolve().parents[1]
SHELL_RTL = sorted((ROOT / "shell" / "rtl").glob("*.sv"))


_EXC_LINE = re.compile(r"^[\w.]*(Error|Exception|Exit|Interrupt)\b.*")


def root_cause(lines: list[str], before: int = 8) -> list[str]:
    """07a2 fix 3: the FIRST exception line of a simulator log (a non-indented ``SomeError: ...`` line that ends a
    traceback) with the ``before`` lines above it (the frames, the last of which is the user's own file). A
    collection-time or import error in the bench is followed by cocotb's own follow-on error
    (``AttributeError ... _running_test``); the root cause is the first one, and it used to fall outside the excerpt.
    Raw log lines, headed by a marker; [] when the log has no exception line."""
    for i, l in enumerate(lines):
        if _EXC_LINE.match(l) and any(x.startswith("Traceback") for x in lines[max(0, i - 40):i]):
            return ["[root cause: the first exception in the simulator log]",
                    *[x.rstrip() for x in lines[max(0, i - before):i + 1]], "[other failure lines]"]
    return []


def failure_excerpt(log: Path, limit: int = 3500) -> str:
    """The failing tests of a cocotb simulator log, raw: each line that reports a failure with the traceback lines
    that follow it (no interpretation); the log's tail if none is recognised."""
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError as e:
        return f"(no simulator log: {e.strerror or e})"
    out: list[str] = root_cause(lines)
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


def swap_mutant_sources(sources: list[Path]) -> list[Path]:
    """05k: flow/mutate.py runs a design's own bench against a mutated copy of its RTL without the bench knowing. With
    ``$FDA_MUTANT_ORIG`` (the design's rtl directory) and ``$FDA_MUTANT_DIR`` (the mutated copy) set, every source that
    lives in the first is replaced by the same-named file of the second. Unset, nothing changes."""
    orig, new = os.environ.get("FDA_MUTANT_ORIG"), os.environ.get("FDA_MUTANT_DIR")
    if not (orig and new):
        return sources
    orig_d, new_d = Path(orig).resolve(), Path(new).resolve()
    return [new_d / Path(s).name if (new_d / Path(s).name).is_file() and Path(s).resolve().parent == orig_d else Path(s)
            for s in sources]


_BIND = re.compile(r"^\s*bind\s", re.M)


def with_checkers(sources: list[Path], design: Path) -> list[Path]:
    """07a2 fix 4: the design's bound checkers (``verif/checkers/*.sv``) in a Verilator build, whether or not the bench's
    own source list names them (run 4's bench did not, so every cover property read 0 %). Files already listed are not
    added twice; a file with a ``bind`` statement goes last, after the modules it binds into. Icarus has no bind and no
    concurrent assertions, so it never calls this."""
    have = {Path(s).resolve() for s in sources}
    found = sorted((Path(design) / "verif" / "checkers").glob("*.sv"))
    add = [c for c in found if c.resolve() not in have]
    out = [Path(s) for s in sources] + add
    binds = [c for c in out if c in found and _BIND.search(c.read_text(errors="replace"))]
    return [c for c in out if c not in binds] + binds


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
    sources = swap_mutant_sources(sources)
    design = srcorder.design_of(test_dir)
    # brief 16: stand-ins for the XPM macros a build instantiates (Icarus and Verilator have none) and, with
    # $FDA_CDC_INJECT_SEED, the synchroniser-delay injection (flow/cdc_inject.py)
    inj_env = os.environ.get("FDA_CDC_INJECT_SEED")
    sources, inj_plus, inj_info = cdc_inject.prepare(sources, (build_root or ROOT / "build" / "sim") / f"{name}_cdcinj",
                                                     int(inj_env) if inj_env not in (None, "") else None)
    if inj_env not in (None, "") and os.environ.get("FDA_CDC_INJECT_INFO"):
        Path(os.environ["FDA_CDC_INJECT_INFO"]).write_text(__import__("json").dumps(inj_info, indent=1))
    if srcorder.no_shell(design):                         # 07a2-prep: a UART-subject design is built without the test shell
        sources = srcorder.drop_shell(sources)
    if simname == "verilator":                            # 07a2 fix 4: bound checkers belong to every Verilator build
        sources = with_checkers(sources, design)
    sources = srcorder.order_sv(sources)                  # 07a2-prep: packages and interfaces first, not name order
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
    plus += inj_plus
    try:
        # 07a2-prep: the simulator starts in test_dir; the task's data files are linked there for the run ($readmemh)
        with srcorder.linked_data(design / "data", test_dir):
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
