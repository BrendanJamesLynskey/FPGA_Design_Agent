"""Brief 189 item 12: per-crossing synchroniser MTBF from Vivado's report (advisory), parsed from the reports of brief 105 (Vivado 2026.1)."""

from __future__ import annotations

import json
from pathlib import Path

from flow import mtbf as M

ROOT = Path(__file__).resolve().parents[2]
SURVEY = ROOT / "results" / "105_constraints_survey"


def test_k26_survey_fixture_lists_24_chains() -> None:
    r = M.record(SURVEY / "raw" / "m1_k26_attr" / "mtbf.rpt")
    assert r["status"] == "ok" and len(r["crossings"]) == 24 and r["chains_in_design"] == 24
    assert r["device"] == "xck26-sfvc784-2LV-c" and r["overall_years"] == 2.8e25
    assert r["worst"]["net"] == "src[17]" and r["worst"]["mtbf_years"] == 6.31e25
    assert r["crossings"][0] == {"path": 1, "mtbf_years": 1.74e26, "mtbf_text": "1.74e+26 years", "toggle_text": "25", "settling_text": "4.4",
                                 "toggle_mtrs": 25.0, "sample_mhz": 333.0, "settling_ns": 4.4, "from": "clk_a", "to": "clk_b", "stages": 2, "net": "src[0]"}
    assert r["enforced"] is False and r["findings"] == []


def test_kr260_design_has_1345_chains_and_a_worst_one() -> None:
    r = M.record(SURVEY / "m4_kr260" / "mtbf.rpt")
    assert len(r["crossings"]) == 1345 and r["overall_years"] == 6.48e51
    numeric = [c["mtbf_years"] for c in r["crossings"] if c["mtbf_years"] is not None]
    assert r["worst"]["mtbf_years"] == min(numeric) and len(numeric) < 1345
    assert r["undefined_static"] == sum(1 for c in r["crossings"] if c["mtbf_years"] is None) - 8       # all but the 8 "n/a" rows
    assert any(c["mtbf_text"].startswith(">") and c["mtbf_years"] == 1.8e308 for c in r["crossings"])
    assert [f["code"] for f in r["findings"]] == ["MTBF-03"] * 8 and "n/a" in r["findings"][0]["message"]


def test_plain_variant_without_async_reg_lists_no_chains_and_seven_series_has_no_report() -> None:
    assert M.record(SURVEY / "raw" / "m1_k26_plain" / "mtbf.rpt")["status"] == "no_chains"
    a7 = M.record(SURVEY / "raw" / "m1_a7_attr" / "mtbf.rpt")             # 7-series: no file written
    assert a7["status"] == "no_report" and a7["crossings"] == []


def test_findings_below_the_target(tmp_path: Path) -> None:
    r = M.record(SURVEY / "raw" / "m1_k26_attr" / "mtbf.rpt", min_years=1e27)
    assert {f["code"] for f in r["findings"]} == {"MTBF-01"} and len(r["findings"]) > 0
    assert all(f["mtbf_years"] < 1e27 for f in r["findings"])


def test_one_stage_chain_is_flagged(tmp_path: Path) -> None:
    text = (SURVEY / "raw" / "m1_k26_attr" / "mtbf.rpt").read_text().replace("| 2             | src[0]", "| 1             | src[0]")
    p = tmp_path / "mtbf.rpt"
    p.write_text(text)
    assert [f["code"] for f in M.record(p)["findings"]] == ["MTBF-02"]


def test_cli_and_build_tcl_hook(tmp_path: Path) -> None:
    out = tmp_path / "m.json"
    assert M.main([str(SURVEY / "raw" / "m1_k26_attr" / "mtbf.rpt"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["status"] == "ok"
    tcl = (ROOT / "flow" / "build.tcl").read_text()
    assert "catch {report_synchronizer_mtbf -file $out/mtbf.rpt}" in tcl      # a failure never fails the build


def test_units_are_converted_to_years() -> None:
    """Brief 246: Vivado prints each MTBF with its own unit (UG835: 'dynamic time units, from seconds to years'); ``mtbf_years`` is always years."""
    assert M._years("6.48e+51 years") == 6.48e51
    assert abs(M._years("1.32 days") - 1.32 / 365.25) < 1e-12
    assert abs(M._years("3 hours") - 3 / 8766.0) < 1e-12
    assert abs(M._years("31557600 seconds") - 1.0) < 1e-9
    assert M._years("> 1.8e+308 years") == 1.8e308
    assert M._years("UNDEFINED") is None


def test_a_days_chain_is_below_a_years_target() -> None:
    """results/207_cdc_margin/raw/vv_k26_b3/B3U/mtbf.rpt has a 1.32 day chain: it is a finding (MTBF-01), not 'the tool gives no MTBF' (MTBF-03)."""
    r = M.record(ROOT / "results" / "207_cdc_margin" / "raw" / "vv_k26_b3" / "B3U" / "mtbf.rpt")
    assert any(f["code"] == "MTBF-01" and f["where"].endswith("ctg_a") for f in r["findings"])      # before the fix its cell parsed as None and counted as MTBF-03
    assert not any(f["code"] == "MTBF-03" and f["where"].endswith("ctg_a") for f in r["findings"])
