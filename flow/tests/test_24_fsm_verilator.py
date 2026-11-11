"""Brief 24: what Verilator does with FSM coverage constructs, as the knowledge skill `fsm-coverage` states it (probe in
results/24_fsm/simprobe). Needs Verilator 5.036+ (the survey's 5.048): the apt package's 5.020 rejects a covergroup."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parents[2] / "results" / "24_fsm" / "simprobe"


def version() -> tuple[int, int]:
    out = subprocess.run(["verilator", "--version"], capture_output=True, text=True).stdout
    m = re.search(r"Verilator (\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


pytestmark = pytest.mark.skipif(shutil.which("verilator") is None or version() < (5, 36), reason="needs Verilator 5.036+")


def build(tmp: Path, define: str) -> subprocess.CompletedProcess:
    return subprocess.run(["verilator", "--binary", "--timing", "--assert", "--coverage", "--coverage-user", "-Wno-fatal", "-Wno-lint",
                           "-Wno-style", f"-D{define}", "--top-module", "tb_probe", "-Mdir", str(tmp / define),
                           str(PROBE / "probe_fsm.sv"), str(PROBE / "tb_probe.sv")], capture_output=True, text=True)


def points(tmp: Path, define: str) -> dict[str, list[tuple[str, int]]]:
    exe = tmp / define / "Vtb_probe"
    subprocess.run([str(exe), f"+verilator+coverage+file+{tmp / define / 'cov.dat'}"], cwd=tmp / define, capture_output=True, check=True)
    out: dict[str, list[tuple[str, int]]] = {}
    for line in (tmp / define / "cov.dat").read_text(errors="replace").splitlines():
        if not line.startswith("C "):
            continue
        f = dict(re.findall(r"\x01(\w+)\x02([^\x01]*)", line))
        out.setdefault(f.get("page", "").split("/")[0], []).append((f.get("o", ""), int(line.rsplit(" ", 1)[1])))
    return out


def test_covergroup_is_ignored_with_no_data(tmp_path: Path) -> None:
    r = build(tmp_path, "WITH_COVERGROUP")
    assert "COVERIGN" in r.stdout + r.stderr
    assert "v_user" not in points(tmp_path, "WITH_COVERGROUP")


def test_sequence_cover_property_counts_real_hits_and_the_implication_form_counts_vacuous_ones(tmp_path: Path) -> None:
    build(tmp_path, "WITH_COVERPROP")
    seq = dict(points(tmp_path, "WITH_COVERPROP")["v_user"])
    assert seq == {"C_run_done": 1, "C_idle_run": 1, "C_run_err": 0}          # RUN -> ERR never happens: 0 hits
    build(tmp_path, "WITH_COVERPROP_IMPL")
    imp = dict(points(tmp_path, "WITH_COVERPROP_IMPL")["v_user"])
    assert imp["C_run_err"] > 0                                                # the trap: a vacuous pass is counted as a hit


def test_case_arm_line_hits_show_the_state_never_entered(tmp_path: Path) -> None:
    build(tmp_path, "WITH_COVERPROP")
    arms = [n for o, n in points(tmp_path, "WITH_COVERPROP")["v_line"] if o == "case"]
    assert arms[:3] == [15, 6, 2] or sorted(arms, reverse=True)[:3] == [15, 6, 2]
    assert arms.count(0) >= 1                                                  # the ERR arm
