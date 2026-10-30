"""Gates parser tests against saved snippets of real Vivado 2025.2 reports.

good_*: the T1 base build (every gate passes).
bad_*:  flow/tests/fixtures/bad_design, built once to make every gate fail.
The snippets are cut from the reports, not written by hand (see data/README.md).
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


def _build_dir(tmp: Path, prefix: str, top: str, bit: bool, variant: str = "base") -> Path:
    d = tmp / prefix
    d.mkdir()
    for name in ("timing_summary", "check_timing", "utilization", "drc", "methodology", "cdc", "power"):
        shutil.copy(DATA / f"{prefix}_{name}.rpt", d / f"{name}.rpt")
    (d / "prepare.json").write_text(json.dumps({"top": top, "variant": variant, "build_stamp": "0"}))
    if bit:
        (d / f"{top}.bit").write_bytes(b"\x00" * 16)
    return d


def test_every_gate_passes_on_the_good_build(tmp_path: Path) -> None:
    r = gates.evaluate(_build_dir(tmp_path, "good", "t1_dimmer_counter_top", bit=True))
    assert r["pass"] and all(r["gates"].values())
    assert r["methodology"]["warnings"] == 54 and r["drc"]["errors"] == r["drc"]["critical_warnings"] == 0


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
