"""Brief 42 round-1 driver and its record tools (results/42_workflows): run-directory ownership, record repair, build error."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from agent.core.session import ROOT

WF = ROOT / "results" / "42_workflows"


def _load(name: str):
    sys.path.insert(0, str(WF))
    try:
        spec = importlib.util.spec_from_file_location(f"wf42_{name}", WF / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(WF))


driver = _load("driver")
repair = _load("repair_records")


def _run(runs: Path, name: str, task: str, arms: str | None) -> None:
    (runs / name).mkdir(parents=True)
    (runs / name / "config.json").write_text(json.dumps({"name": task, "harness_arms": "" if arms is None else arms}))


def test_a_run_directory_is_owned_by_its_task_and_exact_arm(tmp_path: Path) -> None:
    _run(tmp_path, "r1", "t1_gray_stepper", "H9")
    _run(tmp_path, "r2", "t1_gray_stepper", "H2")
    _run(tmp_path, "r3", "t1_gray_stepper", None)
    _run(tmp_path, "r4", "t1_debounce_bank", "H9")
    own = lambda n, task, arm, taken=frozenset(): driver.owns(tmp_path, n, task, arm, set(taken))  # noqa: E731
    assert [n for n in ("r1", "r2", "r3", "r4") if own(n, "t1_gray_stepper", "H9")] == ["r1"]
    assert [n for n in ("r1", "r2", "r3", "r4") if own(n, "t1_gray_stepper", "H2")] == ["r2"]
    assert [n for n in ("r1", "r2", "r3", "r4") if own(n, "t1_gray_stepper", "A0")] == ["r3"]
    assert [n for n in ("r1", "r2", "r3", "r4") if own(n, "t1_debounce_bank", "H9")] == ["r4"]
    assert not own("r1", "t1_gray_stepper", "H9", {"r1"})            # already recorded by another run
    assert not own("missing", "t1_gray_stepper", "H9")


def test_repair_never_picks_an_infrastructure_failure() -> None:
    rows = [
        {"task": "t", "seed": 1, "arm": "H9", "run_id": "old", "infra_failure": "malformed"},
        {"task": "t", "seed": 1, "arm": "H9", "run_id": "wrong"},
        {"task": "t", "seed": 1, "arm": "H9", "run_id": "done", "repaired": "yes"},
    ]
    assert repair.pick_row(rows, "t", 1, "H9", "right") == 1             # the one valid, not repaired row
    rows[1]["run_id"] = "right"
    assert repair.pick_row(rows, "t", 1, "H9", "right") == 1
    with pytest.raises(SystemExit):
        repair.pick_row(rows[:1], "t", 1, "H9", "right")                 # only an infrastructure record: nothing to repair


def test_first_build_error_is_the_compilers_message(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None:
        pytest.skip("Icarus not installed")
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "x_top.sv").write_text("module x_top(input logic clk);\n  assign clk = 1'b0;\n  assign = ;\nendmodule\n")
    msg = driver.first_build_error(ROOT, "benchmark/tasks/x", rtl)
    assert "error" in msg.lower() and "iverilog" not in msg and "-g2012" not in msg
