"""Course tier development tasks: the reference RTL passes its hidden acceptance bench (SIM picks the simulator).
Mutants: benchmark/course/tools/check_task.py (CI runs it per task)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmark.course.tools import no_shell
from benchmark.tools import run_task

COURSE = Path(__file__).resolve().parents[1]
TASKS = sorted(d for d in (COURSE / "tasks").iterdir() if d.is_dir())


@pytest.mark.parametrize("task", TASKS, ids=lambda d: d.name)
def test_reference_passes(task: Path) -> None:
    no_shell.apply()
    r = run_task.run(task, sim=os.environ.get("SIM", "icarus"))
    assert r["built"], r.get("error")
    assert r["pass"], {t: ok for t, ok in r["tests"].items() if not ok}


def test_c12_open_drain_pin_logic_port(tmp_path: Path) -> None:
    """Grader validity (08a2): a design that declares the open-drain pin `output logic` and releases it with 1'bz (the style an
    agent's top used) reads the board's pull-up in the bench exactly like the reference's `output wire`."""
    task = COURSE / "tasks" / "c12_nexys_pwm_audio"
    for f in (task / "ref" / "rtl").glob("*.sv"):
        (tmp_path / f.name).write_text(f.read_text())
    top = tmp_path / "c12_nexys_pwm_audio_top.sv"
    text = top.read_text()
    assert "output wire         AUD_PWM" in text
    top.write_text(text.replace("output wire         AUD_PWM", "output logic        AUD_PWM"))
    no_shell.apply()
    r = run_task.run(task, tmp_path, sim="icarus")
    assert r["built"], r.get("error")
    assert r["pass"], {t: ok for t, ok in r["tests"].items() if not ok}


def test_no_fragile_pulled_pin_bench() -> None:
    """No bench wires a pulled net straight to a design output port (see benchmark/tools/pin_scan.py)."""
    from benchmark.tools import pin_scan

    fragile = [t.name for base in pin_scan.SETS if base.is_dir() for t in sorted(base.iterdir())
               if t.is_dir() and (r := pin_scan.scan(t)) is not None and (t / "ref").is_dir() and r["fragile"]]
    assert fragile == []
