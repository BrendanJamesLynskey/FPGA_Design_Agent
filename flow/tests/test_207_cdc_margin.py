"""Brief 207: flow/cdc_margin.py, the "constraint present and met" step of the clock-crossing method (docs/cdc_margin_method.md).

The property the check stands for: every multi-bit asynchronous crossing has a bounded skew that the routed design meets, its latency
bound is no looser than its protocol needs, and (on UltraScale+) every synchroniser chain is seen by the MTBF report; a user clock
uncertainty is never accepted as the crossing's margin. Cosmetic changes to a report (spacing, the table of contents) must not change a
verdict.

Fixtures are recorded tool output: brief 105's M3 runs (results/105_constraints_survey/raw/m3_*: one Gray bus with no exception, with
datapath-only only, with a met and a violated bus skew; m1_k26_attr: an UltraScale+ MTBF report) and brief 207's own runs
(flow/tests/fixtures/cdc_margin_207/records/: Vivado on xc7a35t and xck26, Quartus Lite on Cyclone V and MAX 10).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from flow import cdc_margin as CM
from flow import gates

ROOT = Path(__file__).resolve().parents[2]
R105 = ROOT / "results" / "105_constraints_survey" / "raw"
REC = Path(__file__).parent / "fixtures" / "cdc_margin_207" / "records"


def _build(tmp: Path, src: Path, names: dict[str, str]) -> Path:
    """A build directory with the named reports copied in (target name -> source name)."""
    d = tmp / "build"
    d.mkdir(parents=True, exist_ok=True)
    for dst, s in names.items():
        shutil.copy(src / s, d / dst)
    return d


# ---- parsers on recorded text --------------------------------------------------------------------------------------------
def test_bus_skew_parser_reads_requirement_actual_slack_and_skips_the_table_of_contents() -> None:
    c = CM.parse_bus_skew((R105 / "m3_c" / "bus_skew.rpt").read_text())
    assert [(x["requirement"], x["actual"], x["slack"]) for x in c] == [(6.0, 0.906, 5.094)]
    d = CM.parse_bus_skew((R105 / "m3_d" / "bus_skew.rpt").read_text())
    assert d[0]["slack"] == pytest.approx(-0.656)
    assert "set_bus_skew" in d[0]["command"]


def test_no_bus_skew_constraint_gives_an_empty_list() -> None:
    assert CM.parse_bus_skew("Bus Skew Report\n\nNo bus skew constraints\n") == []


def test_mtbf_parser_reads_overall_and_every_chain() -> None:
    m = CM.parse_mtbf((R105 / "m1_k26_attr" / "mtbf.rpt").read_text())
    assert m["n_sync"] == 24 and len(m["chains"]) == 24
    assert m["overall_years"] == pytest.approx(2.8e25)
    assert all(c["mtbf_years"] and c["mtbf_years"] > 1e9 for c in m["chains"])


def test_mtbf_undefined_is_none() -> None:
    t = ("2. Default Synchronizer Chain Summary\n| CDC Path | MTBF | a | b | c | d | e | f | g |\n"
         "| 1        | UNDEFINED      | 25 | 333 | 0 | clk_a | clk_b | 2 | x |\n")
    m = CM.parse_mtbf(t)
    assert m["chains"][0]["mtbf_years"] is None


def test_datapath_only_value_parser() -> None:
    rows = CM.parse_exceptions_dpo((R105 / "m3_c" / "exceptions.rpt").read_text())
    assert [r["value"] for r in rows] == [10.0]


# ---- the gate and its findings ----------------------------------------------------------------------------------------------
def test_met_bus_skew_passes_and_violated_bus_skew_fails_the_gate(tmp_path: Path) -> None:
    ok = CM.evaluate(_build(tmp_path / "c", R105 / "m3_c", {"bus_skew_route.rpt": "bus_skew.rpt"}))
    assert ok["evaluated"] and ok["pass"]
    bad = CM.evaluate(_build(tmp_path / "d", R105 / "m3_d", {"bus_skew_route.rpt": "bus_skew.rpt"}))
    assert not bad["pass"]
    assert [f["code"] for f in bad["findings"] if f["level"] == "gate"] == ["CDCM-SKEW-VIOL"]


def test_a_build_from_before_brief_207_is_not_evaluated(tmp_path: Path) -> None:
    r = CM.evaluate(tmp_path)
    assert r == {"evaluated": False, "pass": True, "findings": [], "note": r["note"]}


def test_hand_built_bus_with_datapath_only_but_no_bus_skew_is_flagged(tmp_path: Path) -> None:
    """Survey rank 1's negative case: m3 variant b (datapath-only, no bus skew) passes a slack-only gate vacuously."""
    d = _build(tmp_path, R105 / "m3_b", {"bus_skew_route.rpt": "bus_skew.rpt" if (R105 / "m3_b" / "bus_skew.rpt").exists() else "cdc.rpt",
                                          "cdc_paths_synth.rpt": "cdc_paths_synth.rpt", "cdc_synth.rpt": "cdc_synth.rpt",
                                          "exceptions_route.rpt": "exceptions.rpt"})
    r = CM.evaluate(d)
    assert r["pass"]                                            # advisory only: the guide does not require bus skew
    assert "CDCM-SKEW-MISSING" in {f["code"] for f in r["findings"]}


def test_bus_with_a_bus_skew_constraint_is_not_flagged_missing(tmp_path: Path) -> None:
    d = _build(tmp_path, R105 / "m3_c", {"bus_skew_route.rpt": "bus_skew.rpt", "cdc_paths_synth.rpt": "cdc_paths_synth.rpt",
                                          "cdc_synth.rpt": "cdc_synth.rpt", "exceptions_route.rpt": "exceptions.rpt"})
    r = CM.evaluate(d)
    assert "CDCM-SKEW-MISSING" not in {f["code"] for f in r["findings"]}


def test_loose_datapath_only_value_is_flagged(tmp_path: Path) -> None:
    """Survey rank 2: a datapath-only bound above the source period bounds nothing useful."""
    d = _build(tmp_path, R105 / "m3_c", {"bus_skew_route.rpt": "bus_skew.rpt", "cdc_paths_synth.rpt": "cdc_paths_synth.rpt",
                                          "cdc_synth.rpt": "cdc_synth.rpt"})
    ex = (R105 / "m3_c" / "exceptions.rpt").read_text().replace("max_dpo=10 ", "max_dpo=100")
    (d / "exceptions_route.rpt").write_text(ex)
    r = CM.evaluate(d)
    loose = [f for f in r["findings"] if f["code"] == "CDCM-DPO-LOOSE"]
    assert loose and loose[0]["value"] == 100.0 and loose[0]["level"] == "advisory"
    # the same value is accepted when the architecture declares the crossing a handshake with enough sync stages
    big = CM.evaluate(d, crossings=[{"to": "q1_reg", "type": "handshake", "sync_stages": 20}])
    assert "CDCM-DPO-LOOSE" not in {f["code"] for f in big["findings"]}


def test_usplus_build_without_mtbf_report_is_flagged(tmp_path: Path) -> None:
    d = _build(tmp_path, R105 / "m3_c", {"bus_skew_route.rpt": "bus_skew.rpt"})
    r = CM.evaluate(d, part="xck26-sfvc784-2LV-c")
    assert "CDCM-MTBF-MISSING" in {f["code"] for f in r["findings"]}
    r7 = CM.evaluate(d, part="xc7a35ticsg324-1L")
    assert "CDCM-MTBF-MISSING" not in {f["code"] for f in r7["findings"]}       # 7 series: no report exists (UG835)


def test_mtbf_below_target_is_flagged(tmp_path: Path) -> None:
    d = _build(tmp_path, R105 / "m1_k26_attr", {"mtbf_route.rpt": "mtbf.rpt"})
    (d / "bus_skew_route.rpt").write_text("Bus Skew Report\n\nNo bus skew constraints\n")
    assert "CDCM-MTBF-LOW" not in {f["code"] for f in CM.evaluate(d)["findings"]}
    low = CM.evaluate(d, mtbf_target_years=1e40)
    assert "CDCM-MTBF-LOW" in {f["code"] for f in low["findings"]} and low["pass"]


def test_gate_is_wired_into_post_route(tmp_path: Path) -> None:
    """gates._cdc_margin is what evaluate() calls after routing; None for a build without the report."""
    assert gates._cdc_margin(tmp_path, None, {}) is None
    d = _build(tmp_path / "x", R105 / "m3_d", {"bus_skew_route.rpt": "bus_skew.rpt"})
    r = gates._cdc_margin(d, None, {"part": "xc7a100tcsg324-1"})
    assert r is not None and r["pass"] is False


def test_build_tcl_writes_the_reports() -> None:
    t = (ROOT / "flow" / "build.tcl").read_text()
    assert "report_bus_skew -max_paths 50 -nworst 1 -file $out/bus_skew_route.rpt" in t
    assert "report_synchronizer_mtbf -file $out/mtbf_route.rpt" in t


# ---- brief 207's own records (skipped until they are committed) ------------------------------------------------------------
@pytest.mark.skipif(not (REC / "expect.json").is_file(), reason="brief 207 Vivado records not present")
def test_records_seeded_bad_crossings_are_caught_as_the_method_says() -> None:
    import json
    exp = json.loads((REC / "expect.json").read_text())
    for case in exp["cases"]:
        d = REC / case["dir"]
        r = CM.evaluate(d, part=case.get("part", ""))
        codes = {f["code"] for f in r["findings"]}
        assert r["pass"] is case["pass"], case
        for c in case.get("codes", []):
            assert c in codes, (case, codes)
        for c in case.get("not_codes", []):
            assert c not in codes, (case, codes)


# ---- Quartus records (brief 207: Quartus Prime Lite 25.1std; trimmed to the summary tables the parser reads) ----------------
CV, M10 = "6_slow_1100mv_85c", "7_slow_1200mv_85c"


def test_quartus_bounds_met_on_cyclone_v() -> None:
    r = CM.evaluate_quartus(REC / "qcv_D", CV)
    assert r["pass"] and r["findings"] == []
    assert r["max_skew"]["paths"] == 96 and len(r["max_skew"]["constraints"]) == 4
    assert r["metastability"]["n_chains"] == 22 and r["metastability"]["shortest"] == 2


def test_quartus_clock_group_silently_removes_the_skew_check() -> None:
    """E5: the same fit, analysed with set_clock_groups -asynchronous plus the same set_max_skew lines: no skew path is analysed."""
    r = CM.evaluate_quartus(REC / "qcv_DD", CV)
    assert r["max_skew"]["paths"] == 0
    assert [f["code"] for f in r["findings"]] == ["QCDCM-SKEW-NONE"]


def test_quartus_uncertainty_tightens_max_skew_and_settling_time() -> None:
    """E4: Altera-style 12.5 % uncertainty (DU) against none (D), same fit: skew slack and settling time both fall."""
    d, du = CM.evaluate_quartus(REC / "qcv_D", CV), CM.evaluate_quartus(REC / "qcv_DU", CV)
    assert du["max_skew"]["worst_slack"] < d["max_skew"]["worst_slack"] - 1.0
    assert du["metastability"]["settling_ns"] == pytest.approx(d["metastability"]["settling_ns"] - 1.6, abs=0.01)
    m = CM.evaluate_quartus(REC / "qm10_DU", M10)
    assert "QCDCM-MTBF-LOW" in {f["code"] for f in m["findings"]}         # MAX 10: worst-case design MTBF 69.1 years


def test_quartus_missing_stage_is_caught_by_chain_length_not_by_mtbf() -> None:
    r = CM.evaluate_quartus(REC / "qcv_b2_D", CV)
    assert [f["code"] for f in r["findings"]] == ["QCDCM-CHAIN-SHORT"]
    assert r["metastability"]["worst_mtbf"].startswith("1e+09")           # the MTBF figure alone looks fine


def test_quartus_binary_bus_is_invisible_to_timing() -> None:
    """B1: binary pointers crossed bit by bit pass every constraint and report: coding is a simulation/structure question."""
    r = CM.evaluate_quartus(REC / "qcv_b1_D", CV)
    assert r["pass"] and r["findings"] == []
