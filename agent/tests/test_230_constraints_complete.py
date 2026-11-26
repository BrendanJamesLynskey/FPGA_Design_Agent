"""Brief 230: every top port and every clock source is accounted for before synthesis; the flow writes what it knows.
No model, no Vivado: fixtures in a temporary tree (a copy of the KR260 board file, a small top module, an XDC)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from flow import known_constraints as KC  # noqa: E402

TOP = """
module top (
    input  logic clk_c3,
    input  logic rst_n,
    input  logic din,
    output logic dout,
    output logic [1:0] led,
    input  logic refclk_p,
    input  logic refclk_n,
    input  logic gt_rxp,
    input  logic gt_rxn,
    output logic gt_txp,
    output logic gt_txn,
    input  logic btn
);
    logic refclk;
    IBUFDS_GTE4 u_ref (.I(refclk_p), .IB(refclk_n), .CEB(1'b0), .O(refclk), .ODIV2());
    GTHE4_CHANNEL u_gt (.GTHRXP(gt_rxp), .GTHRXN(gt_rxn), .GTHTXP(gt_txp), .GTHTXN(gt_txn));
    jtag_bus u_jtag (.clk(clk_c3));
    logic [31:0] build;
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build), .DATAVALID());
endmodule
"""
JTAG = """
module jtag_bus (input logic clk);
    logic tck;
    BSCANE2 #(.JTAG_CHAIN(4)) u_bscan (.TCK(tck));
    always_ff @(posedge tck) begin end
endmodule
"""
XDC_FULL = """
create_clock -name sys -period 40.000 [get_ports clk_c3]
create_clock -name ref -period 6.400 [get_ports refclk_p]
set_input_delay -clock [get_clocks sys] -max 2.0 [get_ports din]
set_input_delay -clock [get_clocks sys] -min 0.5 [get_ports din]
# the reset is asynchronous into a synchroniser
set_input_delay -clock [get_clocks sys] 0.000 [get_ports rst_n]
set_false_path -from [get_ports rst_n]
set_output_delay -clock [get_clocks sys] -max 3.0 [get_ports dout]
set_output_delay -clock [get_clocks sys] -min 0.0 [get_ports dout]
set_input_delay -clock [get_clocks sys] 0.000 [get_ports btn]
set_false_path -from [get_ports btn]
"""


def make(tmp: Path, xdc: str = XDC_FULL, spec: dict | None = None, board_slow: list[str] | None = None, top: str = TOP) -> tuple[Path, Path]:
    (tmp / "boards").mkdir(exist_ok=True)
    shutil.copytree(ROOT / "boards" / "kr260", tmp / "boards" / "kr260", dirs_exist_ok=True)
    if board_slow is not None:
        b = yaml.safe_load((tmp / "boards" / "kr260" / "board.yaml").read_text())
        b["slow_ports"] = board_slow
        (tmp / "boards" / "kr260" / "board.yaml").write_text(yaml.safe_dump(b))
    d = tmp / "d"
    (d / "rtl").mkdir(parents=True, exist_ok=True)
    (d / "rtl" / "top.sv").write_text(top)
    (d / "rtl" / "jtag_bus.sv").write_text(JTAG)
    (d / "design.xdc").write_text(xdc)
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "top", "part": "xck26-sfvc784-2LV-c", "board": "kr260",
                                                  "sources": ["d/rtl/*.sv"], "constraints": ["d/design.xdc"]}))
    if spec is not None:
        (d / "spec.yaml").write_text(yaml.safe_dump(spec))
    return tmp, d


def rows(tmp_path, **kw):
    root, d = make(tmp_path, **kw)
    ctx = KC.Ctx(d, root)
    return {r["port"]: r for r in KC.port_classes(ctx, KC.constraint_text(d, ctx.cfg, root))}, ctx


def test_every_class_is_assigned_and_covered(tmp_path):
    r, _ = rows(tmp_path, board_slow=[r"led\[\d+\]"])
    assert r["clk_c3"]["class"] == "clock" and r["clk_c3"]["covered"]
    assert r["refclk_p"]["class"] == "gt_refclk" and r["refclk_p"]["covered"]
    assert r["refclk_n"]["class"] == "gt_refclk" and r["refclk_n"]["covered"]       # the N pin takes no clock of its own
    assert r["rst_n"]["class"] == "reset" and r["rst_n"]["covered"]
    assert r["din"]["class"] == "input" and r["din"]["covered"]
    assert r["dout"]["class"] == "output" and r["dout"]["covered"]
    for p in ("gt_rxp", "gt_rxn", "gt_txp", "gt_txn"):                              # transceiver pads: no fabric timing
        assert r[p]["class"] == "gt_serial" and r[p]["covered"]
    assert r["led"]["class"] == "slow" and not r["led"]["covered"]                  # nothing in the XDC yet: the flow writes it


def test_a_port_with_no_class_is_a_finding_before_synthesis(tmp_path):
    xdc = XDC_FULL.replace("set_output_delay -clock [get_clocks sys] -max 3.0 [get_ports dout]\n", "").replace(
        "set_output_delay -clock [get_clocks sys] -min 0.0 [get_ports dout]\n", "")
    root, d = make(tmp_path, xdc=xdc, board_slow=[r"led\[\d+\]"])
    f = KC.findings(d, root)
    msgs = {x["text"]: x for x in f if x["rule"] == "FDA-CON-14"}
    assert "port dout (output, class output)" in msgs
    assert "set_output_delay" in msgs["port dout (output, class output)"]["message"]
    assert not any("led" in t for t in msgs)                                        # the flow writes the led constraint itself
    assert not any("gt_" in t for t in msgs)                                        # a transceiver pad takes no constraint


def test_a_false_path_alone_does_not_cover_a_port(tmp_path):
    """Measured: p5 arm run 1, check_timing lists led[0], led[1] ('no output delay but user has a false path constraint')."""
    xdc = XDC_FULL + "set_false_path -to [get_ports { dout }]\n"
    xdc = xdc.replace("set_output_delay -clock [get_clocks sys] -max 3.0 [get_ports dout]\n", "").replace(
        "set_output_delay -clock [get_clocks sys] -min 0.0 [get_ports dout]\n", "")
    root, d = make(tmp_path, xdc=xdc, board_slow=[])
    f = [x for x in KC.findings(d, root) if x["text"].startswith("port dout")]
    assert f and "placeholder" in f[0]["message"]


def test_slow_ports_are_written_with_delay_and_false_path(tmp_path):
    root, d = make(tmp_path, board_slow=[r"led\[\d+\]"])
    ctx = KC.Ctx(d, root)
    xdc = KC.constraint_text(d, ctx.cfg, root)
    post = KC.known_post_xdc(ctx, xdc)
    assert "set_output_delay -clock [get_clocks -of_objects [get_ports {clk_c3}]] 0.000 [get_ports {led[*]}]" in post
    assert "set_false_path -to [get_ports {led[*]}]" in post
    assert "board.yaml slow_ports" in post                                          # the reason is in a comment
    # with that text added the port is covered, and the finding list is empty
    rows_ = {r["port"]: r for r in KC.port_classes(ctx, xdc + [("known_post.xdc", post)])}
    assert rows_["led"]["covered"]
    assert [x for x in KC.findings(d, root) if "led" in x["text"]] == []


def test_a_port_the_design_already_constrains_is_left_alone(tmp_path):
    xdc = XDC_FULL + "set_output_delay -clock [get_clocks sys] 0.000 [get_ports {led[*]}]\nset_false_path -to [get_ports {led[*]}]\n"
    root, d = make(tmp_path, xdc=xdc, board_slow=[r"led\[\d+\]"])
    ctx = KC.Ctx(d, root)
    assert KC.known_post_xdc(ctx, KC.constraint_text(d, ctx.cfg, root)) == ""


def test_spec_async_port_gets_its_reason_in_the_comment(tmp_path):
    spec = {"ports": [{"name": "btn", "direction": "in", "async": True, "reason": "a push button, read by a synchroniser"},
                      {"name": "din", "direction": "in", "async": True}]}
    root, d = make(tmp_path, xdc=XDC_FULL.replace("set_input_delay -clock [get_clocks sys] 0.000 [get_ports btn]\nset_false_path -from [get_ports btn]\n", ""),
                   spec=spec, board_slow=[])
    ctx = KC.Ctx(d, root)
    post = KC.known_post_xdc(ctx, KC.constraint_text(d, ctx.cfg, root))
    assert "a push button, read by a synchroniser" in post
    assert "no reason given" not in post.split("# btn")[1].split("# din")[0]
    assert "no reason given: add one to the spec" in post.split("# din")[1]         # an async port without a reason is called out


def test_jtag_and_usr_clocks_are_written_from_the_primitives(tmp_path):
    root, d = make(tmp_path, board_slow=[])
    ctx = KC.Ctx(d, root)
    pre = KC.known_pre_xdc(ctx, KC.constraint_text(d, ctx.cfg, root))
    assert "create_clock -name jtag_tck -period 33.333 [get_pins u_jtag/u_bscan/INTERNAL_TCK]" in pre   # the path follows the instance
    assert "create_clock -name usr_cclk -period 10.000 [get_pins u_usr/CCLK]" in pre
    assert "set_false_path -from [get_clocks usr_cclk]" in pre
    assert "constant afterwards" in pre                                              # the reason sits above the false path


def test_a_clock_the_design_already_defines_on_the_pin_is_not_written_twice(tmp_path):
    xdc = XDC_FULL + "create_clock -name my_tck -period 33.0 [get_pins u_jtag/u_bscan/INTERNAL_TCK]\n"
    root, d = make(tmp_path, xdc=xdc, board_slow=[])
    ctx = KC.Ctx(d, root)
    pre = KC.known_pre_xdc(ctx, KC.constraint_text(d, ctx.cfg, root))
    assert "jtag_tck" not in pre and "usr_cclk" in pre


def test_tcl_variables_in_the_xdc_mean_no_port_finding(tmp_path):
    xdc = "set ports {din dout}\nforeach p $ports { set_input_delay -clock [get_clocks sys] 0 [get_ports $p] }\ncreate_clock -name sys -period 40 [get_ports clk_c3]\n"
    root, d = make(tmp_path, xdc=xdc, board_slow=[])
    assert [x for x in KC.findings(d, root) if x["rule"] == "FDA-CON-14"] == []      # cannot be read as text: no false finding


def test_no_xdc_or_no_top_means_nothing_is_reported(tmp_path):
    root, d = make(tmp_path)
    (d / "design.xdc").unlink()
    assert KC.findings(d, root) == []


def test_explain_unconstrained_gives_class_and_line(tmp_path):
    root, d = make(tmp_path, board_slow=[r"led\[\d+\]"])
    ctx = KC.Ctx(d, root)
    lines = KC.explain_unconstrained({"no_clock": ["u_usr/CCLK", "u_jtag/cmd_reg[0]/C"], "unconstrained_internal_endpoints": ["u_jtag/cmd_reg[0]/D"],
                                      "no_output_delay": ["led[0]", "led[1]"], "no_input_delay": ["mystery"]}, ctx)
    text = "\n".join(lines)
    assert "create_clock -name usr_cclk -period 10.000 [get_pins u_usr/CCLK]" in text
    assert "create_clock -name jtag_tck" in text
    assert "led (2 bits: led[0], led[1]): class slow" in text
    assert "not a top port of the RTL I can read; question" in text                  # an unknown endpoint gets a question, not a guess


def test_unknown_clock_source_is_a_question(tmp_path):
    root, d = make(tmp_path)
    ctx = KC.Ctx(d, root)
    lines = KC.explain_unconstrained({"no_clock": ["u_div/q_reg/C"]}, ctx)
    assert "Question: which port, primitive or generated clock should clock u_div" in lines[0]


def test_xdc_parser_reads_braced_lists_and_nested_brackets():
    cmds = KC.xdc_commands("set_false_path -to [get_ports { led[*] sfp_tx_disable }]\nset_output_delay -clock [get_clocks c] 1 [get_ports {a b}] ;# x\n")
    assert cmds[0]["opts"]["to"] == ["led[*]", "sfp_tx_disable"]
    assert cmds[1]["ports"] == ["a", "b"]
    s, w = KC.covers(cmds, "led", "output")
    assert not s and w
    s, w = KC.covers(cmds, "a", "output")
    assert s and not w


def test_tool_hooks_refuse_build_and_report_notes(tmp_path):
    """complete_findings is what the build tool calls: findings stop the build, notes list what the flow writes."""
    from agent.core import tools
    root, d = make(tmp_path, xdc=XDC_FULL.replace("create_clock -name ref -period 6.400 [get_ports refclk_p]\n", ""), board_slow=[r"led\[\d+\]"])
    s = SimpleNamespace(design=d, root=root, board="kr260")
    found, notes = tools.complete_findings(s, yaml.safe_load((d / "build.yaml").read_text()))
    assert any(x["rule"] == "FDA-CON-14" and "refclk_p" in x["text"] for x in found)
    assert any("create_clock -name usr_cclk" in n for n in notes) and any("false path on led" in n for n in notes)
    import os
    os.environ["FDA_KNOWN_XDC"] = "0"
    try:
        assert tools.complete_findings(s, {}) == ([], [])
    finally:
        del os.environ["FDA_KNOWN_XDC"]


def test_prepare_writes_the_known_files_in_read_order(tmp_path, monkeypatch):
    from flow import prepare
    root, d = make(tmp_path, board_slow=[r"led\[\d+\]"])
    monkeypatch.setattr(prepare, "ROOT", root)
    cfg = yaml.safe_load((d / "build.yaml").read_text())
    out = tmp_path / "out"
    out.mkdir()
    pre, post = prepare.known_xdcs(d, cfg, [d / "design.xdc"], out)
    assert pre.name == "known_pre.xdc" and post.name == "known_post.xdc" and pre.read_text() and post.read_text()
    monkeypatch.setenv("FDA_KNOWN_XDC", "0")
    assert prepare.known_xdcs(d, cfg, [d / "design.xdc"], out) == (None, None)


def test_gates_advice_names_class_and_line(tmp_path):
    from agent.core import tools
    root, d = make(tmp_path, board_slow=[r"led\[\d+\]"])
    s = SimpleNamespace(design=d, root=root, board="kr260")
    data = {"stages": {"post_synth": {"unconstrained_ports": {"no_clock": ["u_usr/CCLK"], "no_output_delay": ["led[0]", "led[1]"]}}}}
    text = tools._unconstrained_advice(s, data)
    assert "unconstrained endpoints explained" in text and "create_clock -name usr_cclk" in text and "class slow" in text
    assert tools._unconstrained_advice(s, {"stages": {"post_synth": {"unconstrained_ports": {}}}}) == ""
    assert tools._unconstrained_advice(s, None) == ""


def test_a_forwarded_clock_output_is_covered_by_its_generated_clock(tmp_path):
    top = TOP.replace("output logic dout,", "output logic dout,\n    output logic fwd_clk,")
    xdc = XDC_FULL + "create_generated_clock -name fwd -source [get_pins u_jtag/x] -divide_by 1 [get_ports fwd_clk]\n"
    r, _ = rows(tmp_path, xdc=xdc, top=top)
    assert r["fwd_clk"]["class"] == "fwd_clock" and r["fwd_clk"]["covered"]
