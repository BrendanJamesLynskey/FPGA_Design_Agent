"""Brief 185: the advisory DSP-slice register check (flow/dsp_regs_check.py, the `dsp_regs` check of the suite) on the committed Vivado 2026.1 records."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from flow import checks as C
from flow import dsp_regs_check as D

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "results" / "185_dsp_slices" / "raw"
NOREG = RAW / "a7" / "mul_WA18_WB18_NA0_NM0_NP0_RSTP0"
FULL = RAW / "a7" / "mul_WA18_WB18_NA1_NM1_NP1_RSTP0"
K26_NOP = RAW / "k26" / "mul_WA18_WB18_NA1_NM1_NP0_RSTP0"


def cells(d: Path) -> list[dict]:
    return D.parse_cells((d / "dsp_cells.txt").read_text())


def codes(fs: list[dict]) -> list[str]:
    return sorted(f["code"] for f in fs)


def test_limits_file_is_regenerated_from_the_committed_measurements() -> None:
    assert subprocess.run([sys.executable, str(ROOT / "tools" / "dsp_regs_limits.py"), "--check"]).returncode == 0
    lim = json.loads((ROOT / "flow" / "dsp_regs_limits.json").read_text())["families"]
    assert lim["7series"]["slice"] == "DSP48E1" and lim["ultrascale_plus"]["slice"] == "DSP48E2"
    assert lim["7series"]["period_needs_mreg_below_ns"] > lim["7series"]["period_needs_preg_below_ns"] > lim["7series"]["slice_min_period_ns"]


def test_no_multiplier_register_is_flagged_below_the_measured_period() -> None:
    assert cells(NOREG)[0]["MREG"] == 0
    assert codes(D.check(cells(NOREG), 4.0)) == ["DSPREG-01"]
    assert D.check(cells(NOREG), 6.0) == []                   # a slow clock: nothing to say


def test_a_fully_registered_slice_is_clean_until_the_slice_limit() -> None:
    c = cells(FULL)
    assert (c[0]["AREG"], c[0]["MREG"], c[0]["PREG"]) == (1, 1, 1)
    assert D.check(c, 2.5) == []
    assert codes(D.check(c, 2.0)) == ["DSPREG-03"]            # DSP48E1 minimum period 2.154 ns at -1


def test_no_output_register_is_flagged_on_ultrascale_plus() -> None:
    c = cells(K26_NOP)
    assert (c[0]["MREG"], c[0]["PREG"]) == (1, 0) and c[0]["type"] == "DSP48E2"
    assert codes(D.check(c, 1.2)) == ["DSPREG-02"]
    assert D.check(c, 3.0) == []


def test_vivados_own_dsp_rows_are_passed_on() -> None:
    drc = (NOREG / "dsp_lines_methodology_drc.txt").read_text().replace("drc.rpt: ", "")
    fs = D.check(cells(FULL), 5.0, drc)
    assert [f["where"] for f in fs] == ["DPIP-1", "DPOP-1", "DPOP-2"] and all(f["code"] == "DSPREG-04" for f in fs)


def test_registered_in_the_suite_and_mapped_to_a_rule() -> None:
    assert "dsp_regs" in C.CHECKS and C.CHECKS["dsp_regs"].kind == "records"
    from flow.lint_ruleset import load_rules
    mapped = {c for r in load_rules()["rules"] for c in (r.get("checks") or {}).get("dsp_regs", [])}
    assert mapped == {"DSPREG-01", "DSPREG-02", "DSPREG-03", "DSPREG-04"}


def test_suite_check_reads_the_build_files(tmp_path: Path) -> None:
    b = tmp_path / "d" / "build" / "base"
    b.mkdir(parents=True)
    (b / "dsp_cells.txt").write_text((NOREG / "dsp_cells.txt").read_text())
    (b / "timing_summary.rpt").write_text("Clock      Waveform(ns)         Period(ns)      Frequency(MHz)\n-----      ------------         ----------      --------------\n"
                                          "clk        {0.000 2.000}        4.000           250.000\n")
    (b / "run.json").write_text("{}")
    assert C.CHECKS["dsp_regs"].applies(tmp_path / "d") is None and C.CHECKS["dsp_regs"].applies(tmp_path / "none") is not None
    ctx = C.Ctx(design=tmp_path / "d", scope="route")
    res = C.CHECKS["dsp_regs"].run(ctx)
    assert [f["code"] for f in res["findings"]] == ["DSPREG-01"] and not res["findings"][0]["blocking"]
