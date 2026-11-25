"""The host program and the verdict script of board row B-R8, without a board (brief 191): the C program is built for this PC with a software stand-in for the registers (-DMOCK),
its JSON is parsed, and the verdict script judges three copies of it per port as it would the board's files. Also builds the real (aarch64, static) program when the cross compiler is present."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DESIGN = Path(__file__).resolve().parents[1]


def test_mock_session_and_verdict(tmp_path) -> None:
    exe = tmp_path / "ps_axi_lat_mock"
    subprocess.run(["gcc", "-O2", "-Wall", "-Werror", "-DMOCK", "-o", str(exe), str(DESIGN / "host" / "ps_axi_lat.c")], check=True)
    out = tmp_path / "res"
    out.mkdir()
    for port in ("fpd", "lpd"):
        for k in (1, 2, 3):
            r = subprocess.run([str(exe), "--n", "200000", "--runs", "5", "--label", port], capture_output=True, text=True, check=True)
            data = json.loads(r.stdout)
            assert data["integrity_mismatches"] == 0 and data["bad_accesses"] == 0 and len(data["runs"]) == 5
            (out / f"result_{port}_run{k}.json").write_text(r.stdout)
    (out / "conditions_before.txt").write_text("mock\n")
    (out / "conditions_after.txt").write_text("mock\n")
    v = subprocess.run([sys.executable, "-I", str(DESIGN / "scripts" / "ps_axi_lat_verdict.py"), str(out)], capture_output=True, text=True)
    assert v.returncode == 0, v.stdout + v.stderr
    rec = json.loads((out / "record.json").read_text())
    assert rec["valid"] and set(rec["ports"]) == {"fpd", "lpd"}
    for fig in ("read_cpu", "read_fab", "write_cpu", "rw_cpu", "write_fab", "write_burst"):
        row = rec["ports"]["fpd"][fig]
        assert row["runs"] == 15 and row["n_per_run"] == 200000 and "p99_ns_median_of_runs" in row and "p999_ns_median_of_runs" in row
    # a missing file or a failing integrity count makes the verdict invalid
    (out / "result_fpd_run3.json").unlink()
    assert subprocess.run([sys.executable, "-I", str(DESIGN / "scripts" / "ps_axi_lat_verdict.py"), str(out)], capture_output=True, text=True).returncode == 1


@pytest.mark.skipif(not shutil.which("aarch64-linux-gnu-gcc"), reason="aarch64 cross compiler not installed")
def test_arm_build(tmp_path) -> None:
    exe = tmp_path / "ps_axi_lat"
    subprocess.run(["aarch64-linux-gnu-gcc", "-O2", "-Wall", "-Werror", "-static", "-o", str(exe), str(DESIGN / "host" / "ps_axi_lat.c")], check=True)
    assert b"ELF 64-bit" in subprocess.run(["file", str(exe)], capture_output=True).stdout
