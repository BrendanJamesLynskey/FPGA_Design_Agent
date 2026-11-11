"""Brief 24: the formal jobs of the reference controller (SymbiYosys, z3): both machines meet the burst-length properties, and the
induction depth that closes each is the recorded one (separated 6, monolithic 5)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FORMAL = Path(__file__).parent / "fixtures" / "fsm_discipline" / "formal"
pytestmark = pytest.mark.skipif(shutil.which("sby") is None or shutil.which("z3") is None, reason="needs sby and z3")


def sby(task: str, tmp: Path) -> str:
    p = subprocess.run(["sby", "-f", "-d", str(tmp / task), "ctl.sby", task], cwd=FORMAL, capture_output=True, text=True)
    return next((l.split("DONE ")[1][1:].split(",")[0] for l in p.stdout.splitlines() if "DONE (" in l), "ERROR")


@pytest.mark.parametrize("task,status", [
    ("sep_bmc", "PASS"), ("mono_bmc", "PASS"), ("sep_cover", "PASS"), ("mono_cover", "PASS"),
    ("sep_prove_k5", "UNKNOWN"), ("sep_prove_k6", "PASS"), ("mono_prove_k4", "UNKNOWN"), ("mono_prove_k5", "PASS"),
])
def test_formal_jobs(task: str, status: str, tmp_path: Path) -> None:
    assert sby(task, tmp_path) == status
