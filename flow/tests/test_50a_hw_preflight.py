"""Brief 50A: flow/hw.py preflight counts real Vivado binaries (as flow/run_vivado.sh does) against FDA_VIVADO_MAX."""

from __future__ import annotations

import subprocess

import pytest

from flow import hw

LINES = ("101 /opt/Xilinx/2026.1/Vivado/bin/unwrapped/lnx64.o/vivado -mode batch -source build.tcl\n"
         "102 /opt/Xilinx/2026.1/Vivado/bin/unwrapped/lnx64.o/vivado -mode tcl -source task_worker.tcl\n")


def fake(stdout: str):
    def run(cmd, capture_output=True, text=True):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
    return run


def test_one_running_vivado_blocks_by_default(monkeypatch) -> None:
    monkeypatch.setattr(hw.subprocess, "run", fake(LINES))
    monkeypatch.delenv("FDA_VIVADO_MAX", raising=False)
    with pytest.raises(hw.HwError, match="101"):
        hw.preflight(min_avail_gb=0)


def test_an_admitted_second_job_may_run(monkeypatch) -> None:
    monkeypatch.setattr(hw.subprocess, "run", fake(LINES))
    monkeypatch.setenv("FDA_VIVADO_MAX", "2")
    assert hw.preflight(min_avail_gb=0) >= 0             # the synthesis helper is not counted


def test_no_vivado(monkeypatch) -> None:
    monkeypatch.setattr(hw.subprocess, "run", fake(""))
    monkeypatch.delenv("FDA_VIVADO_MAX", raising=False)
    assert hw.preflight(min_avail_gb=0) >= 0
