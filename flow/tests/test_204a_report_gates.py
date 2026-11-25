"""Brief 204a: the report-driven checks of flow/report_gates.py, on recorded reports (flow/tests/data/204a).

Real reports (Vivado 2025.2): the bench builds' post-synthesis timing, high-fanout and utilisation reports, and the reports of one
Vivado session that opened their checkpoints; toy designs (``toy_*``) made for this brief: a 12-level path, a cascaded BUFG and a
fabric-divided clock, a 6000-load net, 100/500/900 control sets, one IP. Where a failing report could not be made cheaply (a congested
window, an out-of-date IP) the test edits a real passing one and says so.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import checks as C
from flow import report_gates as R
from flow.gates import parse_utilization

D = Path(__file__).parent / "data" / "204a"


def t(name: str) -> str:
    return (D / name).read_text()


def codes(fs):
    return sorted({f["code"] for f in fs})


# ---- logic levels (RPT-LL-01 advisory, RPT-LL-02 gate) -------------------------------------------------------------------
def test_logic_level_table_parses():
    rows = R.parse_logic_levels(t("toy_lvl12_tight_logic_levels.rpt"))
    assert rows == [{"clock": "clk", "requirement_ns": 1.6, "counts": {12: 1}}]


def test_deep_distribution_at_100mhz_is_flagged_and_shallow_one_is_not():
    deep = R.logic_level_findings(R.parse_logic_levels(t("logic_levels_c15_deep.rpt")))
    assert codes(deep) == ["RPT-LL-01"] and not any(f["blocking"] for f in deep)
    assert R.logic_level_findings(R.parse_logic_levels(t("logic_levels_ok.rpt"))) == []


@pytest.mark.parametrize("req,levels,hit", [(10.0, 12, False), (10.0, 13, True), (8.0, 13, True), (7.9, 6, True), (7.9, 5, False), (4.0, 5, False), (4.0, 6, True)])
def test_logic_level_threshold_follows_the_requirement(req, levels, hit):
    rows = [{"clock": "c", "requirement_ns": req, "counts": {levels: 3}}]
    assert bool(R.logic_level_findings(rows)) is hit


def test_toy_fast_clock_flags_depth_but_the_same_netlist_on_a_slow_clock_does_not():
    assert R.logic_level_findings(R.parse_logic_levels(t("toy_lvl12_tight_logic_levels.rpt")))
    assert not R.logic_level_findings(R.parse_logic_levels(t("toy_lvl12_loose_logic_levels.rpt")))
    assert not R.logic_level_findings(R.parse_logic_levels(t("toy_lvl5_250mhz_logic_levels.rpt")))


def test_a_path_that_fails_with_no_net_delay_is_a_gate():
    fs = R.zero_net_delay_findings(t("toy_lvl12_tight_timing.rpt"))
    assert fs and all(f["code"] == "RPT-LL-02" and f["blocking"] for f in fs)
    assert "cannot" in fs[0]["message"] or "no placement can close" in fs[0]["message"]
    real = R.zero_net_delay_findings(t("timing_synth_deep_fails.rpt"))      # a recorded build (c15_rmsnorm_unit) whose depth cannot close at 100 MHz
    assert real and all(f["blocking"] for f in real)


def test_a_path_that_only_fails_because_of_its_net_delay_is_not_a_gate():
    assert R.zero_net_delay_findings(t("toy_lvl12_loose_timing.rpt")) == []      # met
    assert R.zero_net_delay_findings(t("timing_synth_ok.rpt")) == []
    # violated at 5 ns with 5.4 ns of net delay: the logic alone (slack + net) would pass
    txt = t("toy_lvl12_tight_timing.rpt").replace("Slack (VIOLATED) :        -5.986ns", "Slack (VIOLATED) :        -0.100ns")
    assert R.zero_net_delay_findings(txt) == []


# ---- clock tree (RPT-CLK-01, RPT-CLK-02) --------------------------------------------------------------------------------
def test_cascaded_bufg_and_local_clock_are_found():
    u = R.parse_clock_utilization(t("toy_clk_cascade_clock_utilization.rpt"))
    assert u["has_local_section"] and len(u["global_clocks"]) == 2
    nets = R.parse_clock_networks(t("toy_clk_cascade_clock_networks.rpt"))
    fs = R.clock_tree_findings(u, nets)
    msgs = " ".join(f["message"] for f in fs)
    assert codes(fs) == ["RPT-CLK-01"] and "cascaded" in msgs and "local" in msgs and not any(f["blocking"] for f in fs)


@pytest.mark.parametrize("name", ["clock_utilization_ok.rpt", "clock_utilization_ila.rpt"])
def test_plain_single_buffer_clocks_are_clean(name):
    assert R.clock_tree_findings(R.parse_clock_utilization(t(name)), None) == []


def test_hold_skew_over_300ps_is_advisory_and_uncertainty_thresholds_are_the_guides():
    ps = R.T.parse_paths(t("timing_route_hold_skew.rpt"))
    fs = R.path_clock_findings(ps, "timing_summary.rpt")
    assert codes(fs) == ["RPT-CLK-02"] and "skew" in fs[0]["message"] and not fs[0]["blocking"]
    base = {"kind": "setup", "met": True, "source": "a", "destination": "b", "skew_ns": 0.0}
    assert R.path_clock_findings([{**base, "uncertainty_ns": 0.100}], "x") == []
    assert R.path_clock_findings([{**base, "uncertainty_ns": 0.101}], "x")
    hold = {**base, "kind": "hold"}
    assert R.path_clock_findings([{**hold, "uncertainty_ns": 0.200}], "x") == []
    assert R.path_clock_findings([{**hold, "uncertainty_ns": 0.201}], "x")
    assert R.path_clock_findings([{**hold, "uncertainty_ns": 0.0, "skew_ns": 0.301}], "x")
    # setup skew only counts on a violated path
    assert R.path_clock_findings([{**base, "uncertainty_ns": 0.0, "skew_ns": -0.6}], "x") == []
    assert R.path_clock_findings([{**base, "met": False, "uncertainty_ns": 0.0, "skew_ns": -0.6}], "x")


# ---- fan-out (RPT-FO-01) ------------------------------------------------------------------------------------------------
def test_fanout_over_5000_is_flagged_with_the_guides_fixes_and_clean_report_is_not():
    nets = R.parse_high_fanout(t("toy_fanout6000_high_fanout.rpt"))
    fs = R.fanout_findings(nets, R.parse_clock_summary(t("toy_fanout6000_timing.rpt")))
    assert fs and fs[0]["code"] == "RPT-FO-01" and "KEEP" in fs[0]["message"] and "MAX_FANOUT" in fs[0]["message"] and not fs[0]["blocking"]
    assert R.fanout_findings(R.parse_high_fanout(t("high_fanout_19391.rpt")), [])          # 19391 loads: any clock
    assert R.fanout_findings(R.parse_high_fanout(t("high_fanout_ok.rpt")), R.parse_clock_summary(t("timing_synth_ok.rpt"))) == []


@pytest.mark.parametrize("fo,mhz,hit", [(5001, 10, True), (5000, 10, False), (201, 200, True), (201, 100, False), (101, 300, True), (101, 200, False)])
def test_fanout_thresholds_follow_the_clock_frequency(fo, mhz, hit):
    nets = [{"net": "n", "fanout": fo, "driver": "FDRE", "clock_loads": 0, "worst_slack_ns": 1.0}]
    assert bool(R.fanout_findings(nets, [{"clock": "c", "period_ns": 1000 / mhz, "mhz": float(mhz)}])) is hit


def test_clock_nets_are_left_to_the_clock_checks():
    nets = [{"net": "clk", "fanout": 9000, "driver": "BUFG", "clock_loads": 9000, "worst_slack_ns": 1.0}]
    assert R.fanout_findings(nets, []) == []


# ---- synthesis log (RPT-LOG-01/02/03) ------------------------------------------------------------------------------------
def test_dropped_logic_and_limit_messages():
    fs = R.log_findings(t("log_unused_generic.txt"))
    assert "RPT-LOG-01" in codes(fs)
    lim = R.log_findings(t("log_limit_physopt.txt"))
    assert codes(lim) == ["RPT-LOG-02"] and len(lim) == 2 and not any(f["blocking"] for f in lim)


def test_constant_ports_are_not_logic_dropped():
    assert R.log_findings("WARNING: [Synth 8-3917] design x_top has port LED[3] driven by constant 0\n") == []


def test_a_generic_the_top_does_not_have_is_a_gate():
    """Brief 203: EARLY_MAC and FAST_PRE were set on a top without them and Vivado only warned (Synth 8-3301)."""
    log = ("WARNING: [Synth 8-3301] Unused top level parameter/generic EARLY_MAC\n"
           "WARNING: [Synth 8-3301] Unused top level parameter/generic FAST_PRE\n")
    fs = R.log_findings(log, generics=["EARLY_MAC", "FAST_PRE", "WIDTH"])
    assert [f["code"] for f in fs] == ["RPT-LOG-03", "RPT-LOG-03"] and all(f["blocking"] for f in fs)
    assert "never reached" in fs[0]["message"]
    # a name the build did not set is not the build's fault; with no inputs.tcl every name counts
    assert R.log_findings(log, generics=["WIDTH"]) == []
    assert len(R.log_findings(log, generics=None)) == 2


def test_the_flows_own_build_stamp_is_listed_not_gated():
    fs = R.log_findings(t("log_unused_generic.txt"), generics=R.build_generics(t("inputs_unused_generic.tcl")))
    stamp = [f for f in fs if f["code"] == "RPT-LOG-03"]
    assert len(stamp) == 1 and not stamp[0]["blocking"] and "BUILD_STAMP" in stamp[0]["where"]


def test_build_generics_reads_inputs_tcl():
    assert R.build_generics("set generics [list {A=1} {B=32'h4}]\n") == ["A", "B"]
    assert R.build_generics("set generics [list]\n") == []


# ---- congestion and utilisation (RPT-CONG-01/02) ------------------------------------------------------------------------
def test_region_levels_follow_the_guides_table():
    assert [R.region_level(s) for s in (1, 2, 4, 8, 16, 32, 64, 128)] == [0, 1, 2, 3, 4, 5, 6, 7]


def test_recorded_placer_table_is_clean_and_a_level5_table_is_flagged():
    ok = t("log_congestion_ok.txt")
    tabs = R.parse_placer_congestion(ok)
    assert len(tabs) == 8 and max(x["level"] for x in tabs) <= 1 and R.congestion_findings(tabs, []) == []
    seeded = ok.replace("|      North|                1x1|                1x1|", "|      North|                1x1|              32x32|")   # illustrative edit of a real table
    fs = R.congestion_findings(R.parse_placer_congestion(seeded), [])
    assert codes(fs) == ["RPT-CONG-01"] and "likely degrades" in fs[0]["message"] and not fs[0]["blocking"]
    lvl4 = ok.replace("|      North|                1x1|                1x1|", "|      North|                1x1|              16x16|")
    assert "small QoR" in R.congestion_findings(R.parse_placer_congestion(lvl4), [])[0]["message"]


def test_congestion_report_windows_and_short_share():
    assert R.parse_congestion_report(t("congestion_empty.rpt")) == []
    wins = [{"stage": "router", "direction": "South", "type": "Short", "level": 5, "share": 7.0, "combined_luts": 50.0, "lut": 100.0, "muxf": 3.0, "window": "x"}]
    fs = R.congestion_findings([], wins)
    assert {f["code"] for f in fs} == {"RPT-CONG-01", "RPT-CONG-02"}
    assert R.congestion_findings([], [{**wins[0], "level": 3, "share": 4.0, "combined_luts": 10.0}]) == []


def test_router_table_parses_with_its_columns():
    txt = ("2. Initial Estimated Router Congestion Reporting\n------\n\n"
           "+-----------+------+-------+------------------+--------+---------------+----------------+-----+--------+------+------+------+-----+-------+-----+------------+\n"
           "| Direction | Type | Level | Percentage Tiles | Window | Combined LUTs | Avg LUT Inputs | LUT | LUTRAM | Flop | MUXF | RAMB | DSP | CARRY | SRL | Cell Names |\n"
           "+-----------+------+-------+------------------+--------+---------------+----------------+-----+--------+------+------+------+-----+-------+-----+------------+\n"
           "| South     | Short | 5    | 7.5 | [a:b] | 40 | 4.2 | 100 | 0 | 90 | 26 | 0 | 0 | 0 | 0 | u_x |\n"
           "+-----------+------+-------+------------------+--------+---------------+----------------+-----+--------+------+------+------+-----+-------+-----+------------+\n")
    w = R.parse_congestion_report(txt)
    assert w and w[0]["level"] == 5 and w[0]["share"] == 7.5 and w[0]["muxf"] == 26.0


def test_utilisation_advisories():
    base = {"lut": 10, "lut_available": 100, "ff": 10, "ff_available": 100, "bram_tile": 0, "bram_tile_available": 135, "dsp": 0, "dsp_available": 240}
    assert R.utilization_findings(base) == []
    assert codes(R.utilization_findings({**base, "lut": 80, "ff": 80})) == ["RPT-CONG-02"]            # average 80 %
    assert codes(R.utilization_findings({**base, "lut": 65, "dsp": 200})) == ["RPT-CONG-02"]          # LUT 65 %, DSP 83 %
    assert R.utilization_findings({**base, "lut": 55, "dsp": 200}) == []
    assert R.utilization_findings(parse_utilization(t("utilization_ok.rpt"))) == []


# ---- IP status (RPT-IP-01) -----------------------------------------------------------------------------------------------
def test_ip_status_up_to_date_passes_and_an_edited_status_is_a_gate():
    rows = R.parse_ip_status(t("toy_ip_status_current.rpt"))
    assert len(rows) == 1 and rows[0]["Instance Name"] == "cnt_cur" and rows[0]["Status"] == "Up-to-date"
    assert R.ip_status_findings(rows) == []
    edited = t("toy_ip_status_current.rpt").replace("| Up-to-date |", "| Major version change |")     # illustrative: no older IP version can be created
    fs = R.ip_status_findings(R.parse_ip_status(edited))
    assert fs and fs[0]["code"] == "RPT-IP-01" and fs[0]["blocking"]
    locked = t("toy_ip_status_current.rpt").replace("No changes required", "Locked: upgrade needed")
    assert R.ip_status_findings(R.parse_ip_status(locked))


# ---- control sets (RPT-CS-01 advisory, RPT-CS-02 gate) ---------------------------------------------------------------------
@pytest.mark.parametrize("n,expect", [(100, []), (500, ["RPT-CS-01"]), (900, ["RPT-CS-02"])])
def test_control_set_bands_on_toy_designs(n, expect):
    sets = R.parse_control_sets(t(f"toy_cs{n}_control_sets.rpt"))
    ff_av = parse_utilization(t(f"toy_cs{n}_utilization.rpt"))["ff_available"]
    fs = R.control_set_findings(sets, ff_av)
    assert codes(fs) == expect
    assert all(f["blocking"] for f in fs if f["code"] == "RPT-CS-02")


@pytest.mark.parametrize("sets,hit", [(389, None), (390, "RPT-CS-01"), (779, "RPT-CS-01"), (781, "RPT-CS-02")])
def test_control_set_band_edges(sets, hit):
    fs = R.control_set_findings(sets, 41600)          # xc7a35t: capacity 5200 sets, 7.5 % = 390, 15 % = 780
    assert (fs[0]["code"] if fs else None) == hit


# ---- the registry --------------------------------------------------------------------------------------------------------
def build(tmp_path: Path, files: dict[str, str]) -> Path:
    d = tmp_path / "design"
    b = d / "build" / "base"
    b.mkdir(parents=True)
    for n, txt in files.items():
        (b / n).write_text(txt)
    return d


def run(d: Path, name: str, scope: str):
    return C.run_one(name, d, scope)


def test_registry_logic_levels_gate_and_advisory(tmp_path):
    d = build(tmp_path, {"logic_levels_synth.rpt": t("toy_lvl12_tight_logic_levels.rpt"), "timing_summary_synth.rpt": t("toy_lvl12_tight_timing.rpt")})
    r = run(d, "logic_levels", "synth")
    assert r["status"] == "fail" and {f["code"] for f in r["findings"]} == {"RPT-LL-01", "RPT-LL-02"}
    assert {f["code"]: f["blocking"] for f in r["findings"]} == {"RPT-LL-01": False, "RPT-LL-02": True}
    assert {f["rule"] for f in r["findings"]} == {"HDL-TIM-01"} and r["findings"][0]["fix"]
    ok = build(tmp_path / "ok", {"logic_levels_synth.rpt": t("toy_lvl12_loose_logic_levels.rpt"), "timing_summary_synth.rpt": t("toy_lvl12_loose_timing.rpt")})
    assert run(ok, "logic_levels", "synth")["status"] == "pass"


def test_registry_without_the_reports_is_incomplete_not_a_pass(tmp_path):
    d = build(tmp_path, {"timing_summary_synth.rpt": t("timing_synth_ok.rpt")})
    r = run(d, "logic_levels", "synth")
    assert r["status"] == "pass" and r["incomplete"] == ["logic_levels"]


def test_registry_clock_tree_fanout_log_ip_and_control_sets(tmp_path):
    d = build(tmp_path, {"clock_utilization_synth.rpt": t("toy_clk_cascade_clock_utilization.rpt"), "clock_networks_synth.rpt": t("toy_clk_cascade_clock_networks.rpt"),
                         "timing_summary_synth.rpt": t("toy_fanout6000_timing.rpt"), "high_fanout_synth.rpt": t("toy_fanout6000_high_fanout.rpt"),
                         "vivado.log": t("log_unused_generic.txt") + t("log_limit_physopt.txt"), "inputs.tcl": "set generics [list {EARLY_MAC=1}]\n",
                         "ip_status_synth.rpt": t("toy_ip_status_current.rpt").replace("| Up-to-date |", "| Major version change |"),
                         "control_sets_synth.rpt": t("toy_cs900_control_sets.rpt"), "utilization_synth.rpt": t("toy_cs900_utilization.rpt")})
    assert {f["rule"] for f in run(d, "clock_tree", "synth")["findings"]} == {"HDL-CLK-03"}
    fo = run(d, "fanout", "synth")
    assert fo["status"] == "pass" and fo["findings"][0]["rule"] == "HDL-FO-01"
    lg = run(d, "synth_log", "synth")
    assert lg["status"] == "pass" and {f["code"] for f in lg["findings"]} == {"RPT-LOG-01", "RPT-LOG-02"}
    assert run(d, "ip_status", "synth")["status"] == "fail"
    cs = run(d, "control_sets", "synth")
    assert cs["status"] == "fail" and any(f["code"] == "RPT-CS-02" and f["rule"] == "HDL-CS-01" for f in cs["findings"])
    gen = build(tmp_path / "g", {"vivado.log": "WARNING: [Synth 8-3301] Unused top level parameter/generic EARLY_MAC\n", "inputs.tcl": "set generics [list {EARLY_MAC=1}]\n"})
    r = run(gen, "synth_log", "synth")
    assert r["status"] == "fail" and r["findings"][0]["code"] == "RPT-LOG-03"


def test_registry_congestion_reads_log_and_utilisation(tmp_path):
    seeded = t("log_congestion_ok.txt").replace("|      North|                1x1|                1x1|", "|      North|                1x1|              32x32|")
    d = build(tmp_path, {"vivado.log": seeded, "utilization_synth.rpt": t("utilization_ok.rpt")})
    r = run(d, "congestion", "synth")
    assert r["status"] == "pass" and [f["code"] for f in r["findings"]] == ["RPT-CONG-01"]


def test_ip_status_applies_only_to_builds_with_the_report(tmp_path):
    d = build(tmp_path, {"timing_summary_synth.rpt": t("timing_synth_ok.rpt")})
    assert C.CHECKS["ip_status"].applies(d)
    (d / "build" / "base" / "ip_status_synth.rpt").write_text(t("toy_ip_status_current.rpt"))
    assert C.CHECKS["ip_status"].applies(d) is None


def test_every_new_code_is_documented_with_level_and_source():
    for cid, (level, source, what) in R.INFO.items():
        assert level in ("gate", "advisory") and source and what
        assert cid in (Path(R.__file__).read_text()), cid
    assert {c for c, v in R.INFO.items() if v[0] == "gate"} == {"RPT-LL-02", "RPT-LOG-03", "RPT-IP-01", "RPT-CS-02"}
