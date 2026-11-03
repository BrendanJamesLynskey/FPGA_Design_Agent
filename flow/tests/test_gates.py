"""Gates parser tests against saved snippets of real Vivado 2025.2 reports.

good_*: the T1 base build (every gate passes); the per-stage reports (04e: *_rtl, *_synth,
        *_place, *_route and good_power_board_env) are from the 04e rebuild of the same sources.
bad_*:  flow/tests/fixtures/bad_design, built once to make every gate fail.
The snippets are cut from the reports, not written by hand (see data/README.md). Two thresholds
(QoR score, post-place hold) have no real failing report yet, so those tests edit a number in a
real report in memory and say so.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from flow import gates

DATA = Path(__file__).parent / "data"


def rd(name: str) -> str:
    return (DATA / name).read_text()


def test_timing_summary_good() -> None:
    t = gates.parse_timing_summary(rd("good_timing_summary.rpt"))
    assert (t["wns_ns"], t["tns_ns"], t["whs_ns"], t["ths_ns"]) == (3.616, 0.0, 0.122, 0.0)
    assert t["tns_total_endpoints"] == 1232 and t["wpws_ns"] == 4.5 and t["timing_met"]
    assert gates.parse_wns(rd("good_timing_summary.rpt")) == 3.616


def test_timing_summary_bad() -> None:
    t = gates.parse_timing_summary(rd("bad_timing_summary.rpt"))
    assert t["wns_ns"] < 0 and t["tns_ns"] < 0 and t["tns_failing_endpoints"] > 0 and not t["timing_met"]


def test_check_timing() -> None:
    good = gates.parse_check_timing(rd("good_check_timing.rpt"))
    assert len(good) == 12 and not any(good.values())
    bad = gates.parse_check_timing(rd("bad_check_timing.rpt"))
    # in_fp has a false path but no input delay: check_timing still counts it (2 = in_fp + in_none)
    assert bad["no_input_delay"] == 2 and bad["no_output_delay"] == 1


def test_utilization() -> None:
    u = gates.parse_utilization(rd("good_utilization.rpt"))
    assert (u["lut"], u["ff"], u["bram_tile"], u["dsp"], u["carry4"]) == (485, 488, 0, 0, 29)
    assert u["lut_available"] == 63400 and u["iob"] == 55 and u["bufg"] == 1


def test_rule_tables() -> None:
    assert gates.parse_rule_table(rd("good_drc.rpt")) == []
    meth = gates.parse_rule_table(rd("good_methodology.rpt"))
    assert meth == [{"rule": "XDCH-2", "severity": "Warning",
                     "description": "Same min and max delay values on IO port", "count": 54}]
    drc = {r["rule"]: r["severity"] for r in gates.parse_rule_table(rd("bad_drc.rpt"))}
    assert drc["NSTD-1"] == drc["UCIO-1"] == "Critical Warning" and drc["CFGBVS-1"] == "Warning"
    meth = {r["rule"]: r for r in gates.parse_rule_table(rd("bad_methodology.rpt"))}
    assert meth["TIMING-6"]["severity"] == "Critical Warning" and meth["TIMING-16"]["count"] == 267


def test_cdc() -> None:
    assert gates.parse_cdc(rd("good_cdc.rpt")) == {"safely_timed": True, "rules": []}
    bad = gates.parse_cdc(rd("bad_cdc.rpt"))
    assert not bad["safely_timed"]
    assert bad["rules"] == [{"rule": "CDC-1", "severity": "Critical", "count": 2,
                             "description": "1-bit unknown CDC circuitry"}]


def test_power() -> None:
    p = gates.parse_report_power(rd("good_power.rpt"))
    assert p["total_w"] == 0.133 and p["dynamic_w"] == 0.035 and p["confidence"] == "Low"
    assert p["core_w"] == 0.004    # clocks + slice logic + signals, I/O excluded


def test_parsers_refuse_the_wrong_report() -> None:
    with pytest.raises(ValueError):
        gates.parse_timing_summary(rd("good_utilization.rpt"))
    with pytest.raises(ValueError):
        gates.parse_check_timing(rd("good_power.rpt"))
    with pytest.raises(ValueError):
        gates.parse_cdc(rd("good_drc.rpt"))
    with pytest.raises(ValueError):
        gates.parse_report_power(rd("good_cdc.rpt"))


STAGE_REPORTS = ("methodology_rtl", "timing_summary_synth", "check_timing_synth", "methodology_synth", "drc_synth",
                 "qor_assessment_synth", "utilization_synth", "timing_summary_place", "qor_assessment_route")


def _build_dir(tmp: Path, prefix: str, top: str, bit: bool, variant: str = "base", stages: bool = False) -> Path:
    """A build directory from the fixtures: the F0A post-route set, plus (stages=True) the 04e per-stage reports
    and the power report made for the board's thermal environment."""
    d = tmp / prefix
    d.mkdir()
    for name in ("timing_summary", "check_timing", "utilization", "drc", "methodology", "cdc", "power"):
        shutil.copy(DATA / f"{prefix}_{name}.rpt", d / f"{name}.rpt")
    if stages:
        for name in STAGE_REPORTS:
            shutil.copy(DATA / f"good_{name}.rpt", d / f"{name}.rpt")
        shutil.copy(DATA / "good_power_board_env.rpt", d / "power.rpt")
    (d / "prepare.json").write_text(json.dumps({"top": top, "variant": variant, "build_stamp": "0"}))
    if bit:
        (d / f"{top}.bit").write_bytes(b"\x00" * 16)
    return d


def test_every_gate_passes_on_the_good_build(tmp_path: Path) -> None:
    r = gates.evaluate(_build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True))
    assert r["pass"] and all(r["gates"].values())
    assert r["methodology"]["warnings"] == 54 and r["drc"]["errors"] == r["drc"]["critical_warnings"] == 0
    # an F0A-era build: the per-stage reports are absent, so those stages are "not run", not failed
    assert [r["stages"][n]["ran"] for n in gates.STAGES] == [False, False, False, True, True]
    assert r["first_failed_stage"] is None and "power_junction_ok" not in r["gates"]


# --- 04e: the UltraFast stages -------------------------------------------------------------------------------

def test_qor_assessment() -> None:
    q = gates.parse_qor_assessment(rd("good_qor_assessment_synth.rpt"))
    assert q["score"] == 5 and q["meaning"] == "Design runs will meet timing"
    assert q["flow_guidance"] == ["Run report_methodology and fix or waive warnings", "Continue to route_design"]
    assert q["review"] == [{"name": "Max LUT Combined", "threshold": "20.00", "actual": "46.64", "affects_score": False}]
    assert gates.parse_qor_assessment(rd("good_qor_assessment_route.rpt"))["score"] == 5
    with pytest.raises(ValueError):
        gates.parse_qor_assessment(rd("good_drc.rpt"))


def test_stage_reports_parse() -> None:
    assert gates.parse_rule_table(rd("good_methodology_rtl.rpt"))[0]["rule"] == "XDCH-2"
    assert gates.parse_timing_summary(rd("good_timing_summary_synth.rpt"))["wns_ns"] == 4.602
    assert gates.parse_timing_summary(rd("good_timing_summary_place.rpt"))["whs_ns"] == -0.027
    assert not any(gates.parse_check_timing(rd("good_check_timing_synth.rpt")).values())
    assert gates.parse_rule_table(rd("good_drc_synth.rpt")) == []
    env = gates.parse_power_environment(rd("good_power_board_env.rpt"))
    assert (env["airflow_lfm"], env["heatsink"], env["junction_c"], env["theta_ja_c_per_w"]) == (0.0, "none", 42.7, 18.2)


def test_every_stage_passes_on_the_04e_build(tmp_path: Path) -> None:
    r = gates.evaluate(_build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True, stages=True))
    assert r["pass"] and r["first_failed_stage"] is None
    assert all(r["stages"][n]["ran"] and r["stages"][n]["pass"] for n in gates.STAGES)
    assert set(r["stages"]["rtl"]["gates"]) == {"rtl_methodology_no_critical"}
    assert set(r["stages"]["post_synth"]["gates"]) == {"post_synth_no_unconstrained_endpoints", "post_synth_methodology_no_critical",
                                                       "post_synth_drc_clean"}
    assert "post_synth_qor_assessment" not in r["gates"] and r["warnings"] == []
    assert set(r["stages"]["post_place"]["gates"]) == {"post_place_hold"}
    assert "power_junction_ok" in r["stages"]["post_route"]["gates"]
    assert r["stages"]["post_route"]["gates"]["post_route_qor_assessment"] is True
    assert r["stages"]["post_synth"]["qor_assessment"]["score"] == 5 and r["stages"]["post_route"]["qor_assessment"]["score"] == 5
    assert r["stages"]["post_synth"]["timing"]["wns_ns"] == 4.602 and r["stages"]["post_place"]["timing"]["whs_ns"] == -0.027
    # the flat gates dict still carries the F0A names, plus the stage-prefixed ones
    assert {"setup", "hold", "pulse_width", "no_unconstrained_endpoints", "drc_clean", "methodology_no_critical",
            "cdc_no_critical", "bitstream_present"} <= set(r["gates"])


def test_first_failed_stage_is_the_earliest(tmp_path: Path) -> None:
    d = _build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True, stages=True)
    # the bad design's methodology report (TIMING-6 critical) as the RTL-stage report
    shutil.copy(DATA / "bad_methodology.rpt", d / "methodology_rtl.rpt")
    r = gates.evaluate(d)
    assert not r["pass"] and r["first_failed_stage"] == "rtl" and not r["gates"]["rtl_methodology_no_critical"]
    assert r["stages"]["post_synth"]["pass"] and r["stages"]["post_route"]["pass"]
    # fix rtl, break post_synth with the bad design's check_timing and DRC reports
    shutil.copy(DATA / "good_methodology_rtl.rpt", d / "methodology_rtl.rpt")
    shutil.copy(DATA / "bad_check_timing.rpt", d / "check_timing_synth.rpt")
    shutil.copy(DATA / "bad_drc.rpt", d / "drc_synth.rpt")
    r = gates.evaluate(d)
    assert r["first_failed_stage"] == "post_synth"
    assert not r["gates"]["post_synth_no_unconstrained_endpoints"] and not r["gates"]["post_synth_drc_clean"]
    assert r["gates"]["post_synth_methodology_no_critical"]


def test_qor_gate_is_after_routing(tmp_path: Path) -> None:
    """Brief 05g. A post-synthesis score below 4 is a recorded warning, not a gate; the routed score is the gate.
    No real report scores below 3 yet: one number of a real report is changed."""
    d = _build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True, stages=True)
    for rpt in ("synth", "route"):
        good = rd(f"good_qor_assessment_{rpt}.rpt")
        for score, text, ok in ((2, "Design will not meet timing", False), (3, "Design will likely not meet timing", False),
                                (4, "Design will likely meet timing", True)):
            (d / f"qor_assessment_{rpt}.rpt").write_text(good.replace("| 5 - Design runs will meet timing", f"| {score} - {text}"))
            r = gates.evaluate(d)
            if rpt == "synth":     # post-synthesis: warning only, the build still passes
                assert "post_synth_qor_assessment" not in r["gates"] and r["pass"]
                assert r["stages"]["post_synth"]["qor_assessment"]["score"] == score
                assert (r["warnings"] == []) is ok
                if not ok:
                    assert r["warnings"][0]["name"] == "post_synth_qor_assessment" and r["warnings"][0]["stage"] == "post_synth"
                    assert r["warnings"][0]["score"] == score and r["stages"]["post_synth"]["warnings"] == r["warnings"]
            else:                  # post-route: the gate
                assert r["gates"]["post_route_qor_assessment"] is ok and r["stages"]["post_route"]["qor_assessment"]["score"] == score
                assert (r["first_failed_stage"] is None) is ok and r["pass"] is ok
                if not ok:
                    assert r["first_failed_stage"] == "post_route"
        (d / f"qor_assessment_{rpt}.rpt").write_text(good)
    assert gates.QOR_SCORE_MIN == 4
    # synth 3 and route 5 (the 06a pattern on small designs): passes, with the warning kept
    (d / "qor_assessment_synth.rpt").write_text(rd("good_qor_assessment_synth.rpt").replace(
        "| 5 - Design runs will meet timing", "| 3 - Design will likely not meet timing"))
    r = gates.evaluate(d)
    assert r["pass"] and len(r["warnings"]) == 1 and r["gates"]["post_route_qor_assessment"]


def test_place_hold_threshold(tmp_path: Path) -> None:
    d = _build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True, stages=True)
    t = rd("good_timing_summary_place.rpt").replace("-0.027", "-0.627")
    (d / "timing_summary_place.rpt").write_text(t)
    r = gates.evaluate(d)
    assert r["first_failed_stage"] == "post_place" and not r["gates"]["post_place_hold"]
    assert r["stages"]["post_place"]["timing"]["whs_ns"] == -0.627


def test_power_junction_gate_needs_the_board_environment(tmp_path: Path) -> None:
    d = _build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True, stages=True)
    shutil.copy(DATA / "good_power.rpt", d / "power.rpt")        # F0A's report: Vivado's default heat sink and airflow
    r = gates.evaluate(d)
    assert r["first_failed_stage"] == "post_route" and not r["gates"]["power_junction_ok"]


def test_the_bad_build_fails_each_gate_it_should(tmp_path: Path) -> None:
    r = gates.evaluate(_build_dir(tmp_path, "bad", "bad_top", bit=False))
    assert not r["pass"]
    failed = {g for g, ok in r["gates"].items() if not ok}
    assert {"setup", "pulse_width", "no_unconstrained_endpoints", "drc_clean",
            "methodology_no_critical", "cdc_no_critical", "bitstream_present"} <= failed


def test_ila_variant_needs_the_probes_file(tmp_path: Path) -> None:
    d = _build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True, variant="ila")
    assert not gates.evaluate(d)["gates"]["debug_probes_present"]
    (d / "t1_dimmer_counter_top.ltx").write_text("{}")
    assert gates.evaluate(d)["pass"]


def test_cli_exit_status(tmp_path: Path) -> None:
    good = _build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True)
    assert gates.main([str(good), "--json", str(tmp_path / "g.json")]) == 0
    assert json.loads((tmp_path / "g.json").read_text())["pass"] is True
    assert gates.main([str(_build_dir(tmp_path, "bad", "bad_top", bit=False))]) == 1


def test_stage_limited_build_marks_later_stages_not_run(tmp_path) -> None:
    """A build stopped after synthesis (FDA_STOP_AFTER=synth, brief 05a) has no post-route reports."""
    import shutil
    from pathlib import Path
    data = Path(__file__).parent / "data"
    for dst, src in {"methodology_rtl.rpt": "good_methodology_rtl.rpt", "timing_summary_synth.rpt": "good_timing_summary_synth.rpt",
                     "check_timing_synth.rpt": "good_check_timing_synth.rpt", "methodology_synth.rpt": "good_methodology_synth.rpt",
                     "drc_synth.rpt": "good_drc_synth.rpt", "qor_assessment_synth.rpt": "good_qor_assessment_synth.rpt",
                     "utilization_synth.rpt": "good_utilization_synth.rpt"}.items():
        shutil.copy(data / src, tmp_path / dst)
    r = gates.evaluate(tmp_path)
    assert {k: v["ran"] for k, v in r["stages"].items()} == {"rtl": True, "post_synth": True, "post_place": False,
                                                              "post_route": False, "bitstream": False}
    assert r["pass"] is True and r["first_failed_stage"] is None and r["timing"] is None
