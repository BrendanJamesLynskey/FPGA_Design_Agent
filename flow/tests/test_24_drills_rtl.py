"""Brief 24 drills (benchmark/drills/d24_*): the reference passes the hidden bench (which also reaches every state and legal transition of the
reference), every functional mutant is killed, and the grader tells the choice a design made (registered, lookahead, combinational)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark" / "drills" / "lib"))
import grade_fsm  # noqa: E402

DRILLS = ["d24_registered_outputs", "d24_no_extra_latency"]


@pytest.mark.parametrize("name", DRILLS)
def test_reference_passes_and_every_mutant_is_killed(name: str, tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, str(ROOT / "benchmark" / "tools" / "check_task.py"), str(ROOT / "benchmark" / "drills" / name),
                        "--out", str(tmp_path)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]
    assert "survived" not in r.stdout.lower()


def test_grader_records_the_choice() -> None:
    a = ROOT / "benchmark" / "drills" / "d24_registered_outputs"
    b = ROOT / "benchmark" / "drills" / "d24_no_extra_latency"
    ga = grade_fsm.grade(a, a / "ref", drv={"JB1": "FDRE", "JB2": "FDRE"})
    assert ga["pass"] and ga["checks"]["behaviour"]["lag"] == 1 and ga["choice"].startswith("registered decode")
    assert not grade_fsm.grade(a, a / "ref", drv={"JB1": "FDRE", "JB2": "LUT3"})["pass"]       # a LUT in front of a pin fails the first drill
    gb = grade_fsm.grade(b, b / "ref", drv={"JB1": "LUT2"})
    assert gb["pass"] and gb["checks"]["behaviour"]["lag"] == 0
    # the second drill's reference does not pass the first drill's bench with its lag rule, and vice versa the first accepts lag 0
    cross = grade_fsm.grade(b, a / "ref", drv={"JB1": "FDRE"})
    assert not cross["pass"] and "behaviour" in [k for k, v in cross["checks"].items() if not v["pass"]]       # registered pins are one clock late: rejected
