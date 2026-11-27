"""Brief 235: goal kind "block for a shell". A block inside a supplied shell (the Red Pitaya vendor shell) is not a board top: the constraints gate
checks its interface to the shell (clock, reset, bus ports), not board pins. Brief 225 saw the board-top gate fail stage 1 in 3 of 7 runs, because the
agent pinned the block's ports to the board or defined a clock on them."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from agent.core import constraints as con
from agent.core import dispatch
from agent.core import tools as tl
from flow import srcorder

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "boards" / "redpitaya_stemlab_125_14"
SHELL = con.load_shell_interface(BOARD)
GOOD = {p["name"]: {"dir": p["dir"], "width": "" if p["width"] == 1 else f"[{p['width'] - 1}:0]"} for p in SHELL["ports"]}


def rules(f):
    return sorted(x["rule"] for x in f)


def test_the_shell_interface_is_the_user_block_template_ports() -> None:
    from flow.standards_check import parse_modules
    m = parse_modules((BOARD / "shell" / "rp_user_block.sv").read_text(), "rp_user_block")[0]
    assert {k: v["dir"] for k, v in m.ports.items()} == {p["name"]: p["dir"] for p in SHELL["ports"]}
    assert {k: con._width_of(v["width"]) for k, v in m.ports.items()} == {p["name"]: p["width"] for p in SHELL["ports"]}
    assert SHELL["clock"]["port"] == "clk" and SHELL["reset"]["port"] == "rstn"


def test_an_empty_or_absent_xdc_passes_and_comments_are_ignored() -> None:
    assert con.check_block_xdc("") == []
    assert con.check_block_xdc("# a block has no constraints\n\n") == []


@pytest.mark.parametrize("line,rule", [
    ("set_property -dict { PACKAGE_PIN U18 IOSTANDARD LVCMOS33 } [get_ports { clk }];", "FDA-BLK-1"),   # brief 225 rp_patgen_r1: clk pinned to the board clock pin
    ("set_property IOSTANDARD LVCMOS33 [get_ports dac_a[*]]", "FDA-BLK-1"),                              # rp_patgen_r1: dac_a pinned to the DAC pins
    ("create_clock -period 8.000 -name clk [get_ports clk]", "FDA-BLK-2"),                              # rp_freqcount_r2 / rp_patgen_r3
    ("create_generated_clock -name g -source [get_ports clk] -divide_by 2 [get_pins x/Q]", "FDA-BLK-2"),
    ("set_input_delay -clock clk 2 [all_inputs]", "FDA-BLK-3"),
    ("set_false_path -from [get_clocks a] -to [get_clocks b]", "FDA-BLK-3"),
    ("set_max_delay -datapath_only 8 -from [get_pins a/C] -to [get_pins b/D]", "FDA-BLK-3"),
])
def test_a_block_has_no_pins_clock_or_timing_commands(line, rule) -> None:
    f = con.check_block_xdc(line + "\n")
    assert rule in rules(f), f


def test_the_board_top_gate_would_pass_what_the_block_gate_refuses_and_the_reverse() -> None:
    clk = "create_clock -period 8.000 -name sys_clk_pin [get_ports clk]\n"
    assert "FDA-BLK-2" in rules(con.check_block_xdc(clk))                      # the shell owns the clock
    assert con.check_block_xdc("") == [] and con.check_block_xdc("# nothing\n") == []


def test_the_shell_ports_pass_and_a_missing_wrong_or_extra_port_is_named() -> None:
    assert con.check_block_ports("b", GOOD, SHELL) == []
    assert con.check_block_ports("b", None, SHELL) == []                      # the top's source does not exist yet
    miss = {k: v for k, v in GOOD.items() if k != "rstn"}
    f = con.check_block_ports("b", miss, SHELL)
    assert rules(f) == ["FDA-BLK-4"] and "rstn" in f[0]["message"]
    f = con.check_block_ports("b", {**GOOD, "dac_a": {"dir": "input", "width": "[13:0]"}}, SHELL)
    assert rules(f) == ["FDA-BLK-5"] and "dac_a" in f[0]["message"] and "input" in f[0]["message"]
    f = con.check_block_ports("b", {**GOOD, "sys_addr": {"dir": "input", "width": "[19:0]"}}, SHELL)
    assert rules(f) == ["FDA-BLK-5"] and "20 bit" in f[0]["message"] and "32" in f[0]["message"]
    f = con.check_block_ports("b", {**GOOD, "led": {"dir": "output", "width": "[7:0]"}}, SHELL)
    assert rules(f) == ["FDA-BLK-6"] and "led" in f[0]["message"]
    assert con.check_block_ports("b", {**GOOD, "sys_addr": {"dir": "input", "width": "[W-1:0]"}}, SHELL) == []     # a width that is not a number is not judged


def test_the_marker_is_read_and_defaults(tmp_path: Path) -> None:
    assert srcorder.block_shell(tmp_path) is None
    (tmp_path / srcorder.BLOCK_SHELL_MARKER).write_text("\n")
    assert srcorder.block_shell(tmp_path) == "shell.yaml"
    (tmp_path / srcorder.BLOCK_SHELL_MARKER).write_text("other.yaml\n")
    assert srcorder.block_shell(tmp_path) == "other.yaml"


def _block_session(session, top_src: str | None, xdc: str | None):
    root = session.root
    shutil.copytree(BOARD, root / "boards" / "redpitaya_stemlab_125_14", dirs_exist_ok=True)
    session.board = "redpitaya_stemlab_125_14"
    d = session.design
    (d / srcorder.BLOCK_SHELL_MARKER).write_text("shell.yaml\n")
    (d / srcorder.NO_SHELL_MARKER).write_text("")
    cfg = yaml.safe_load((d / "build.yaml").read_text())
    for p in (d / "rtl").glob("*"):
        p.unlink()
    cfg["top"], cfg["sources"] = "blk", [f"{d.relative_to(root)}/rtl/*.sv"]
    (d / "build.yaml").write_text(yaml.safe_dump(cfg))
    if top_src is not None:
        (d / "rtl" / "blk.sv").write_text(top_src)
    for p in d.glob("*.xdc"):
        p.unlink()
    if xdc is not None:
        (d / "design.xdc").write_text(xdc)
    return session


BLOCK_SV = (BOARD / "shell" / "rp_user_block.sv").read_text().replace("module rp_user_block", "module blk")


def test_the_tool_passes_a_block_with_no_xdc_and_the_shell_ports(session) -> None:
    s = _block_session(session, BLOCK_SV, None)
    r = dispatch(s, "check_constraints", {})
    assert r["ok"] is True and r["findings"] == [], r
    s = _block_session(session, BLOCK_SV, "# nothing: the shell has the pins\n")
    assert dispatch(s, "check_constraints", {})["ok"] is True


def test_the_tool_refuses_what_stage_1_failed_on_in_brief_225(session) -> None:
    pinned = "set_property -dict { PACKAGE_PIN U18 IOSTANDARD LVCMOS33 } [get_ports { clk }];\ncreate_clock -period 8.000 -name clk [get_ports clk]\n"
    s = _block_session(session, BLOCK_SV, pinned)
    r = dispatch(s, "check_constraints", {})
    assert r["ok"] is False and rules(r["findings"]) == ["FDA-BLK-1", "FDA-BLK-2"]
    assert "block" in r["output"] and "FDA-BLK-2" in r["output"]


def test_the_tool_reports_the_ports_the_top_misses(session) -> None:
    s = _block_session(session, BLOCK_SV.replace("    input  logic               rstn,                 // active low, synchronous to clk\n", ""), None)
    r = dispatch(s, "check_constraints", {})
    assert r["ok"] is False and "FDA-BLK-4" in rules(r["findings"]) and "rstn" in r["output"]


def test_a_block_does_not_fail_while_its_source_does_not_exist_yet(session) -> None:
    s = _block_session(session, None, None)
    assert dispatch(s, "check_constraints", {})["ok"] is True


def test_board_constraints_says_a_block_has_no_pins(session) -> None:
    s = _block_session(session, BLOCK_SV, None)
    r = dispatch(s, "board_constraints", {"map": [{"resource": "led", "port": "led"}]})
    assert r["ok"] is False and "no board pins" in r["output"]
    assert not (s.design / "design.xdc").exists()


def test_a_board_top_design_is_unchanged_by_the_new_kind(session) -> None:
    r = dispatch(session, "check_constraints", {})
    assert "FDA-BLK" not in r["output"]


def test_the_cli_flag_and_the_run_marker(tmp_path: Path, monkeypatch) -> None:
    from agent.__main__ import build_parser
    a = build_parser().parse_args(["run", "x.md", "--board", "redpitaya_stemlab_125_14", "--block-for-shell"])
    assert a.block_for_shell == "shell.yaml"
    a = build_parser().parse_args(["run", "x.md"])
    assert a.block_for_shell == ""
    from agent.graph.run import Config
    assert Config(spec_md=Path("x.md"), name="d").block_shell == ""
