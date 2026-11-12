"""SymbiYosys jobs of brief 58A (verif/formal): the interlocks (bounded, k-induction, cover) and the MAC frame FSMs
(bounded and cover only: their k-induction needs invariants on internal state, not written yet).
Skipped where sby is not installed (CI: the verification job installs it)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FORMAL = Path(__file__).resolve().parents[1] / "verif" / "formal"
JOBS = [("interlocks", "bmc"), ("interlocks", "prove"), ("interlocks", "cover"),
        ("mac_tx", "bmc"), ("mac_tx", "cover"),
        ("mac_rx", "bmc"), ("mac_rx", "cover")]


@pytest.mark.skipif(shutil.which("sby") is None, reason="SymbiYosys not installed")
@pytest.mark.parametrize("job,task", JOBS)
def test_formal(tmp_path, job, task):
    out = tmp_path / f"{job}_{task}"
    r = subprocess.run(["sby", "-f", "-d", str(out), f"{job}.sby", task], cwd=FORMAL, capture_output=True, text=True,
                       timeout=1800)
    status = (out / "status").read_text().split()[0] if (out / "status").exists() else "ABSENT"
    assert status == "PASS", (status, r.stdout[-2000:])
