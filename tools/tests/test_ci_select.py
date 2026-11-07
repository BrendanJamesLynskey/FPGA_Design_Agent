"""Brief 07a2 fix 5, group G: pull-request CI runs the touched benchmark tasks plus a smoke set; everything else runs all."""

from __future__ import annotations

from pathlib import Path

import yaml

from tools import ci_select as cs

ROOT = Path(__file__).resolve().parents[2]


def test_a_push_the_nightly_run_and_a_missing_base_run_everything() -> None:
    assert cs.select("v1", "push", "abc") is None
    assert cs.select("course", "schedule", None) is None
    assert cs.select("v1", "pull_request", None) is None


def test_a_pull_request_runs_the_touched_tasks_plus_the_smoke_set() -> None:
    smoke = yaml.safe_load((ROOT / "tools" / "ci_smoke.yaml").read_text())
    files = ["benchmark/tasks/t2_vga_sprite/hidden/acceptance.py", "benchmark/course/tasks/c15_softmax_unit/spec.md",
             "agent/graph/run.py"]
    v1 = cs.select("v1", "pull_request", "base", files)
    assert set(v1) == set(smoke["v1"]) | {"t2_vga_sprite"}
    course = cs.select("course", "pull_request", "base", files)
    assert set(course) == set(smoke["course"]) | {"c15_softmax_unit"}
    assert cs.select("v1", "pull_request", "base", ["README.md"]) == sorted(smoke["v1"])      # untouched: smoke only


def test_smoke_set_names_real_tasks_and_is_small() -> None:
    smoke = yaml.safe_load((ROOT / "tools" / "ci_smoke.yaml").read_text())
    for tier, names in smoke.items():
        assert set(names) <= set(cs.all_tasks(tier)) and 1 <= len(names) <= 3
    assert len(cs.all_tasks("v1")) >= 16 and len(cs.all_tasks("course")) >= 18      # the full sweep stays much larger


def test_a_task_directory_that_does_not_exist_is_ignored() -> None:
    assert "t9_gone" not in cs.select("v1", "pull_request", "b", ["benchmark/tasks/t9_gone/x"])


def test_command_line_modes(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    assert cs.main(["v1"]) == 0 and capsys.readouterr().out.strip() == "ALL"
    assert cs.main(["v1", "--k"]) == 0 and capsys.readouterr().out.strip() == ""
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("PR_BASE_SHA", "HEAD")                      # nothing changed against itself: the smoke set
    assert cs.main(["v1", "--k"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == " or ".join(sorted(["t1_bcd_updown", "t1_elevator_fsm", "t2_i2c_scanner"]))
