"""Brief 56A: the GT gates (flow/gt_gates.py), the link planner (flow/gt_plan.py), the spec.yaml `link:` check and the GT Wizard
exception classification. No Vivado needed: the fixtures are small texts in the shape of the real reports and of the Wizard's .xci
(taken from the brief's K26 build, Vivado 2026.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flow import exceptions_check as ec
from flow import gates, gt_data, gt_gates, gt_plan

ROOT = Path(__file__).resolve().parents[2]
K26 = "xck26-sfvc784-2LV-c"
XCI = """{ "parameters": {
 "CHANNEL_ENABLE": [ { "value": "X0Y6", "value_src": "user" } ],
 "TX_LINE_RATE": [ { "value": "10.3125", "value_src": "user" } ], "RX_LINE_RATE": [ { "value": "10.3125", "value_src": "user" } ],
 "TX_PLL_TYPE": [ { "value": "QPLL0", "value_src": "default" } ], "RX_PLL_TYPE": [ { "value": "QPLL0", "value_src": "default" } ],
 "TX_REFCLK_FREQUENCY": [ { "value": "156.25" } ], "TX_REFCLK_SOURCE": [ { "value": "X0Y6 clk0" } ],
 "TX_INT_DATA_WIDTH": [ { "value": "32" } ], "TX_USER_DATA_WIDTH": [ { "value": "64" } ],
 "RX_INT_DATA_WIDTH": [ { "value": "32" } ], "RX_USER_DATA_WIDTH": [ { "value": "64" } ],
 "C_TX_LINE_RATE": [ { "value": "99" } ] } }"""
XDC = """set_property PACKAGE_PIN Y6 [get_ports refclk_p]
set_property PACKAGE_PIN Y5 [get_ports refclk_n]
create_clock -name ref -period 6.400 [get_ports refclk_p]
set_property PACKAGE_PIN T2 [get_ports rx_p]
set_property PACKAGE_PIN T1 [get_ports rx_n]
set_property -dict {PACKAGE_PIN R4} [get_ports tx_p]
set_property -dict {PACKAGE_PIN R3 IOSTANDARD LVCMOS18} [get_ports {tx_n}]
"""


def cfg(**kw: str) -> dict[str, str]:
    c = gt_gates.read_cfg(XCI)
    c.update(kw)
    return c


def test_config_and_xdc_parsing() -> None:
    c = gt_gates.read_cfg(XCI)
    assert c["TX_LINE_RATE"] == "10.3125" and "C_TX_LINE_RATE" not in c
    pins, clocks = gt_gates.xdc_facts(XDC)
    assert pins["tx_n"] == "R3" and pins["tx_p"] == "R4" and clocks == {"refclk_p": 6.4}


def test_speed_grade_and_windows_for_the_k26() -> None:
    assert gt_data.speed_grade(K26) == "2LV" and gt_data.speed_grade("xczu5ev-sfvc784-2-i") == "2"
    assert gt_data.speed_grade("xczu5ev-sfvc784-2L-e") is None          # 2L is 0.85 or 0.72 V: ambiguous, so no check
    assert gt_data.FGTHMAX["2LV"] == 12.5 and gt_data.windows("QPLL0", "2LV")[1] == (9.8, 12.5)
    assert 16 not in gt_data.windows("CPLL", "2LV")                     # the CPLL has no divide-by-16


@pytest.mark.parametrize("rate,pll,ok", [("10.3125", "QPLL0", True), ("13", "QPLL0", False), ("10.3125", "CPLL", False),
                                         ("9.0", "CPLL", False), ("6.25", "CPLL", True), ("3.125", "CPLL", True), ("12.5", "QPLL1", True), ("0.3", "QPLL0", False)])
def test_rate_window(rate: str, pll: str, ok: bool) -> None:
    r = gt_gates.check_rate(cfg(TX_LINE_RATE=rate, RX_LINE_RATE=rate, TX_PLL_TYPE=pll, RX_PLL_TYPE=pll), "2LV")
    assert r["ok"] is ok, r


def test_rate_unknown_grade_is_not_applicable() -> None:
    assert gt_gates.check_rate(cfg(), None)["ok"] is None


def test_user_clock_limits() -> None:
    r = gt_gates.check_user_clocks(cfg(), "2LV")
    assert r["ok"] and r["expect_mhz"] == [161.133, 161.133]
    r = gt_gates.check_user_clocks(cfg(TX_USER_DATA_WIDTH="32", TX_LINE_RATE="12.5"), "2LV")      # 390.625 MHz: at the limit
    assert r["ok"]
    r = gt_gates.check_user_clocks(cfg(TX_USER_DATA_WIDTH="32"), "1LV")                          # 322.27 MHz is the 1LV limit for 32/32
    assert r["ok"]
    r = gt_gates.check_user_clocks(cfg(TX_USER_DATA_WIDTH="16", TX_INT_DATA_WIDTH="16"), "2LV")  # 644 MHz
    assert not r["ok"] and "exceeds" in r["why"]


def test_pins_and_reference_on_the_k26() -> None:
    pd = gt_data.load_part(K26)
    pins, clocks = gt_gates.xdc_facts(XDC)
    r = gt_gates.check_refclk_and_lanes(cfg(), pd, pins, clocks)
    assert r["refclk"]["ok"] and r["lanes"]["ok"], r
    bad = dict(pins, rx_p="V2", rx_n="V1")                                # channel 1's pins, but channel X0Y6 is enabled
    r = gt_gates.check_refclk_and_lanes(cfg(), pd, bad, clocks)
    assert not r["lanes"]["ok"] and "X0Y5" in r["lanes"]["why"]
    r = gt_gates.check_refclk_and_lanes(cfg(), pd, {k: v for k, v in pins.items() if k != "tx_n"}, clocks)
    assert not r["lanes"]["ok"] and "not assigned" in r["lanes"]["why"]
    r = gt_gates.check_refclk_and_lanes(cfg(), pd, pins, {"refclk_p": 8.0})
    assert not r["refclk"]["ok"] and "156.25" in r["refclk"]["why"]
    r = gt_gates.check_refclk_and_lanes(cfg(), pd, dict(pins, refclk_p="V6", refclk_n="V5"), clocks)    # MGTREFCLK1, not clk0
    assert not r["refclk"]["ok"]
    r = gt_gates.check_refclk_and_lanes(cfg(TX_REFCLK_SOURCE="X0Y6 northclk0"), pd, pins, clocks)
    assert r["refclk"]["ok"] is None
    assert gt_gates.check_refclk_and_lanes(cfg(), None, pins, clocks)["lanes"]["ok"] is None


def test_the_part_table_matches_the_known_sfp_pins() -> None:
    t = gt_data.load_part(K26)["pins"]
    assert t["T2"] == {"func": "MGTHRXP2_224", "site": "GTHE4_CHANNEL_X0Y6"} and t["R4"]["site"] == "GTHE4_CHANNEL_X0Y6"
    assert t["Y6"]["site"] == "GTHE4_COMMON_X0Y1" and gt_data.quad_of_channel("X0Y6") == "GTHE4_COMMON_X0Y1"


RTL = """gth_wiz u_gt (.gtwiz_reset_all_in(rst || (rs != 4'd0)), .gtwiz_reset_tx_done_out(tx_done_t), .gtwiz_reset_rx_done_out(rx_done_r), .loopback_in(lb));"""


def test_reset_sequence() -> None:
    assert gt_gates.check_reset_sequence(RTL, "gth_wiz")["ok"]
    assert not gt_gates.check_reset_sequence(RTL.replace("rst || (rs != 4'd0)", "1'b0"), "gth_wiz")["ok"]
    assert not gt_gates.check_reset_sequence(RTL.replace(".gtwiz_reset_rx_done_out(rx_done_r)", ".gtwiz_reset_rx_done_out()"), "gth_wiz")["ok"]
    assert not gt_gates.check_reset_sequence("module x; endmodule", "gth_wiz")["ok"]
    assert not gt_gates.check_reset_sequence(RTL.replace(".gtwiz_reset_all_in(rst || (rs != 4'd0)), ", ""), "gth_wiz")["ok"]


SUMMARY = """| Clock Summary
| -------------
------------------------------------------------------------------------------------------------

Clock                                      Waveform(ns)           Period(ns)      Frequency(MHz)
-----                                      ------------           ----------      --------------
clk_25                                     {0.000 20.000}         40.000          25.000          
  clk_u                                    {0.000 5.000}          10.000          100.000         
sfp_mgt_refclk                             {0.000 3.200}          6.400           156.250         
      rxusr2                               {0.000 3.103}          6.206           161.133         
      txusr2                               {0.000 3.103}          6.206           161.133         


-----------------------------------------------------
| Intra Clock Table
"""


def test_user_clocks_are_timed() -> None:
    assert [n for n, _ in gt_gates._clock_rows(SUMMARY)][-2:] == ["rxusr2", "txusr2"]
    assert gt_gates.check_clocks_timed(SUMMARY, [161.133, 161.133])["ok"]
    assert not gt_gates.check_clocks_timed(SUMMARY, [322.266])["ok"]
    assert not gt_gates.check_clocks_timed("", [161.133])["ok"]


def test_gt_drc_rows() -> None:
    summary = "| REQP-1839 | Warning | Transceiver channel input ports unconnected | 1 |\n"
    detail = "REQP-1839#1 Warning\nGTHE4_CHANNEL input pin RXP is not connected\n"
    assert not gt_gates.check_drc_rows(summary, "")["ok"]
    assert not gt_gates.check_drc_rows(detail, "")["ok"]
    assert gt_gates.check_drc_rows("| TIMING-6 | Critical Warning | No common primary clock | 1 |\n", "")["ok"]
    assert not gt_gates.check_drc_rows("", "| GTHE-1 | Warning | something about a GT | 2 |\n")["ok"]


def test_util_parser_reads_the_ultrascale_plus_rows() -> None:
    u = gates.parse_utilization("| CLB LUTs*               |  992 |     0 |          0 |    117120 |  0.85 |\n"
                                "| CLB Registers           | 3138 |     0 |          0 |    234240 |  1.34 |\n")
    assert u["lut"] == 992 and u["ff"] == 3138 and u["lut_available"] == 117120


def test_wizard_exception_is_classified() -> None:
    row = {"position": 3, "From": "*", "Through": "*",
           "To": "[get_pins -filter REF_PIN_NAME=~*D -of_objects [get_cells -hierarchical -filter {NAME =~ *reset_synchronizer*inst/rst_in_meta*}]]"}
    assert ec.is_gt_wizard_exception(row)
    mine = dict(row, To="[get_cells -hierarchical -filter {NAME =~ u_sync/meta*}]")
    assert not ec.is_gt_wizard_exception(mine)
    assert not ec.is_gt_wizard_exception(dict(row, To="*", From="*"))     # no NAME pattern: never classified here


def test_plan_for_the_kr260() -> None:
    board = yaml.safe_load((ROOT / "boards/kr260/board.yaml").read_text())
    r = gt_plan.plan({"protocol": "raw", "line_rate_gbps": 10.3125, "lanes": 1}, board)
    assert r["ok"] and r["wizard"]["TX_PLL_TYPE"] == "QPLL0" and r["user_clock_mhz"] == 161.133
    assert r["wizard"]["CHANNEL_ENABLE"] == "X0Y6" and "create_clock -name <refclk> -period 6.400" in r["xdc"]
    r = gt_plan.plan({"protocol": "raw", "line_rate_gbps": 16.0, "lanes": 4, "refclk_mhz": 125}, board)
    assert not r["ok"] and len(r["problems"]) >= 3
    r = gt_plan.plan({"protocol": "ethernet_10g", "line_rate_gbps": 9.0, "lanes": 1}, board)
    assert not r["ok"] and any("10.3125" in p for p in r["problems"])


def test_the_example_link_spec_plans_cleanly() -> None:
    spec = yaml.safe_load((ROOT / "designs/b56a_gth_serdes/link_spec.yaml").read_text())
    board = yaml.safe_load((ROOT / "boards/kr260/board.yaml").read_text())
    assert gt_plan.plan(spec["link"], board)["ok"]


def test_the_plan_agrees_with_the_designs_wizard_tcl() -> None:
    """The planner's answer for the b56a design is the Wizard configuration in the design's reviewed Tcl."""
    board = yaml.safe_load((ROOT / "boards/kr260/board.yaml").read_text())
    w = gt_plan.plan({"protocol": "raw", "line_rate_gbps": 10.3125, "lanes": 1}, board)["wizard"]
    tcl = (ROOT / "designs/b56a_gth_serdes/ip/amd_ip.tcl").read_text()
    for k, v in w.items():
        assert f"CONFIG.{k} {{{v}}}" in tcl, k


def test_link_errors_and_spec_validation() -> None:
    assert gt_plan.link_errors({"protocol": "raw", "line_rate_gbps": 10.3125, "lanes": 1}) == []
    assert gt_plan.link_errors({"protocol": "pcie", "line_rate_gbps": 40, "lanes": 0, "pll": "x"})
    assert gt_plan.link_errors("raw")
    from agent.graph.spec_schema import validate
    errs = validate({"link": {"protocol": "raw", "line_rate_gbps": "fast", "lanes": 1}}, need_proof=False)
    assert any(e.startswith("spec.yaml link.line_rate_gbps") for e in errs)


def test_the_tool_is_registered() -> None:
    from agent.core import registry
    from agent.core import tools  # noqa: F401
    assert "gt_plan" in registry.TOOLS
