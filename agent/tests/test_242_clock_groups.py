"""Brief 242: the flow writes set_clock_groups from the declared clock relations, only where every crossing is synchronised.
No model, no Vivado: fixtures in a temporary tree."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from flow import architecture as A  # noqa: E402
from flow import known_constraints as KC  # noqa: E402
from agent.graph.interview import ensure_clock_relation_question  # noqa: E402

TOP = """
module top (input logic clk_a, input logic clk_b, input logic d, output logic q);
    logic s;
    xpm_cdc_single u_s (.src_clk(clk_a), .src_in(d), .dest_clk(clk_b), .dest_out(s));
    always_ff @(posedge clk_b) q <= s;
endmodule
"""
XDC = """create_clock -name clk_a -period 10.0 [get_ports clk_a]
create_clock -name clk_b -period 7.0 [get_ports clk_b]
"""


def design(tmp_path, arch, xdc=XDC, top=TOP):
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "top.sv").write_text(top)
    (d / "design.xdc").write_text(xdc)
    cfg = {"top": "top", "part": "xck26-sfvc784-2LV-c", "sources": [str(d / "rtl" / "*.sv")], "constraints": [str(d / "design.xdc")]}
    (d / "build.yaml").write_text(yaml.safe_dump(cfg))
    base = {"clock_domains": [{"name": "a", "clock": "clk_a"}, {"name": "b", "clock": "clk_b"}]}
    (d / "architecture.yaml").write_text(yaml.safe_dump({**base, **arch}))
    ctx = KC.Ctx(d, tmp_path, cfg=cfg)
    return ctx, [("design.xdc", xdc)]


REL = {"clock_relations": [{"between": ["a", "b"], "kind": "async", "reason": "unrelated oscillators"}]}
XING = {"crossings": [{"from": "a", "to": "b", "signal": "d", "primitive": "xpm_cdc_single"}]}


def test_async_with_synchronised_crossing_is_written(tmp_path):
    ctx, xdc = design(tmp_path, {**REL, **XING})
    plan = KC.clock_group_plan(ctx, xdc)
    assert not plan["refused"] and len(plan["written"]) == 1
    line = plan["written"][0]["line"]
    assert line.startswith("set_clock_groups -asynchronous") and "[get_ports {clk_a}]" in line and "[get_ports {clk_b}]" in line
    assert "set_clock_groups" in KC.known_post_xdc(ctx, xdc)


def test_unrecognised_crossing_is_refused_and_reported(tmp_path):
    ctx, xdc = design(tmp_path, {**REL, "crossings": [{"from": "a", "to": "b", "signal": "d", "primitive": "xpm_cdc_gray"}]})
    plan = KC.clock_group_plan(ctx, xdc)        # xpm_cdc_gray is a bank primitive but the RTL does not instantiate it
    assert not plan["written"] and "not instantiated" in plan["refused"][0]["why"]
    assert "set_clock_groups" not in "\n".join(ln for ln in KC.known_post_xdc(ctx, xdc).splitlines() if not ln.startswith("#"))
    assert any("NOT written" in ln for ln in KC.info_lines(ctx, xdc))


def test_no_declared_crossing_is_refused_unless_stated(tmp_path):
    ctx, xdc = design(tmp_path, REL)
    assert KC.clock_group_plan(ctx, xdc)["refused"]
    rel = {"clock_relations": [{"between": ["a", "b"], "kind": "async", "no_crossings": True}]}
    ctx, xdc = design(tmp_path / "x", rel)
    plan = KC.clock_group_plan(ctx, xdc)
    assert not plan["written"] and not plan["refused"] and "cut no path" in plan["skipped"][0]["why"]


def test_related_is_never_written(tmp_path):
    ctx, xdc = design(tmp_path, {"clock_relations": [{"between": ["a", "b"], "kind": "related"}], **XING})
    plan = KC.clock_group_plan(ctx, xdc)
    assert not plan["written"] and not plan["refused"] and plan["skipped"]


def test_designs_own_clock_groups_win(tmp_path):
    ctx, xdc = design(tmp_path, {**REL, **XING}, xdc=XDC + "set_clock_groups -asynchronous -group [get_clocks clk_a] -group [get_clocks clk_b]\n")
    plan = KC.clock_group_plan(ctx, xdc)
    assert not plan["written"] and "design's constraint wins" in plan["skipped"][0]["why"]


def test_exclusive_needs_a_declared_clock_mux(tmp_path):
    ctx, xdc = design(tmp_path, {"clock_relations": [{"between": ["a", "b"], "kind": "exclusive"}]})
    assert "clock mux" in KC.clock_group_plan(ctx, xdc)["refused"][0]["why"]
    mux = {"clock_muxes": [{"instance": "u_mux", "primitive": "BUFGCTRL", "inputs": ["a", "b"], "output": "a", "condition": "static", "reason": "test"}]}
    ctx, xdc = design(tmp_path / "y", mux)           # derived: the mux inputs are exclusive with no explicit relation
    plan = KC.clock_group_plan(ctx, xdc)
    assert plan["written"][0]["line"].startswith("set_clock_groups -physically_exclusive")


def test_unnameable_clock_is_refused(tmp_path):
    ctx, xdc = design(tmp_path, {**REL, **XING}, xdc="create_clock -name clk_a -period 10 [get_ports clk_a]\n")
    assert "cannot name the Vivado clock of b" in KC.clock_group_plan(ctx, xdc)["refused"][0]["why"]


def test_no_relations_no_crossings_no_output(tmp_path):
    ctx, xdc = design(tmp_path, {})
    assert KC.clock_group_plan(ctx, xdc) == {"written": [], "refused": [], "skipped": []}


def test_a_declared_crossing_alone_gives_a_derived_async_pair(tmp_path):
    ctx, xdc = design(tmp_path, XING)
    plan = KC.clock_group_plan(ctx, xdc)
    assert len(plan["written"]) == 1 and "declared in architecture.yaml" in plan["written"][0]["reason"]
    ctx, xdc = design(tmp_path / "r", {**XING, "clock_relations": [{"between": ["a", "b"], "kind": "related"}]})      # the explicit relation wins
    assert not KC.clock_group_plan(ctx, xdc)["written"]


def test_architecture_schema_checks_clock_relations():
    base = {"blocks": [{"name": "x"}], "interfaces": [], "clock_domains": [{"name": "a", "clock": "c"}, {"name": "b", "clock": "d"}], "crossings": [],
            "predicted_resources": {"lut": 1, "ff": 1, "bram_tile": 0, "dsp": 0}}
    assert not [e for e in A.check_architecture({**base, "clock_relations": [{"between": ["a", "b"], "kind": "async"}]}) if "clock_relations" in e]
    bad = A.check_architecture({**base, "clock_relations": [{"between": ["a", "z"], "kind": "sideways"}]})
    assert any("clock_relations[0]" in e for e in bad)


def test_interview_asks_the_relation_once():
    spec = {"clocks": [{"name": "clk_a"}, {"name": "clk_b"}]}
    out, added = ensure_clock_relation_question(spec)
    assert added and "asynchronous" in out["open_questions"][0]["question"]
    assert ensure_clock_relation_question(out)[1] is False
    assert ensure_clock_relation_question({"clocks": [{"name": "clk_a"}]})[1] is False
    assert ensure_clock_relation_question({**spec, "clock_relations": [{"between": ["clk_a", "clk_b"], "kind": "async"}]})[1] is False


def test_domain_clock_object_names_a_derived_clock(tmp_path):
    ctx, xdc = design(tmp_path, {"clock_domains": [{"name": "a", "clock": "clk_a"}, {"name": "b", "clock": "TXUSRCLK2 from the GT", "clock_object": "[get_clocks txusr2]"}],
                                 "crossings": [{"from": "a", "to": "b", "signal": "d", "primitive": "xpm_cdc_single"}], **REL})
    plan = KC.clock_group_plan(ctx, xdc)
    assert plan["written"] and "[get_clocks txusr2]" in plan["written"][0]["line"]


def test_pair_with_a_bounding_macro_is_bounded_in_both_directions_not_grouped(tmp_path):
    xs = [{"from": "a", "to": "b", "signal": "d", "primitive": "xpm_cdc_single"}, {"from": "b", "to": "a", "signal": "bus", "primitive": "xpm_cdc_handshake"}]
    top = TOP + "\nmodule m2 (input logic clk_a, input logic clk_b);\n  xpm_cdc_handshake u_h (.src_clk(clk_b), .dest_clk(clk_a));\nendmodule\n"
    ctx, xdc = design(tmp_path, {**REL, "crossings": xs}, top=top)
    w = KC.clock_group_plan(ctx, xdc)["written"][0]
    assert w["mode"] == "bound" and "set_clock_groups" not in w["line"] and w["line"].count("set_max_delay -datapath_only") == 2


def test_exceptions_check_reports_the_flows_overridden_pair_bound_as_information():
    from flow import exceptions_check as E
    loc = {"file": "known_post.xdc", "line": 9, "text": "set_max_delay -datapath_only -from [get_clocks a] -to [get_clocks b] 5.0"}
    row = {"Status": "Totally overridden path by FP 10 - DPO 11 - DPO 13"}
    assert E.is_flow_pair_bound(row, loc)
    assert not E.is_flow_pair_bound({"Status": "Totally overridden path by CG 7 - CG 8"}, loc)
    assert not E.is_flow_pair_bound(row, {**loc, "file": "design.xdc"})
    assert not E.is_flow_pair_bound({"Status": "Non-existent path"}, loc)
