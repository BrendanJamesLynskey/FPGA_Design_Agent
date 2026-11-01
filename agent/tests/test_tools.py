"""The tools on a copy of T1, with a fake runner (no simulator, no Vivado, no board)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core import TOOLS, dispatch, tool_list
from agent.core.runner import RunResult
from agent.core.constraints import check_xdc, check_xdc_safety
from agent.core.session import ROOT
from agent.tests.conftest import FakeRunner, stage_hw

BOARD = ROOT / "boards" / "nexys_a7_100t"
# The deliberate hazard of Packt/Bruno Ch. 4 (research/books_assessment_2026-10-31.md): a clock on a button
BTNC_TRAP = """\
set_property -dict { PACKAGE_PIN N17 IOSTANDARD LVCMOS33 } [get_ports { BTNC }];
create_clock -period 10.000 -name btnc_clk [get_ports { BTNC }];
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets BTNC_IBUF];
"""


def test_every_tool_has_a_strict_schema() -> None:
    names = [t["name"] for t in tool_list()]
    assert len(names) == len(set(names)) >= 15
    for t in tool_list():
        sch = t["inputSchema"]
        assert sch["type"] == "object" and sch["additionalProperties"] is False, t["name"]
        assert t["description"] and t["version"]


def test_file_tools(session) -> None:
    assert dispatch(session, "write_file", {"path": "rtl/new.sv", "content": "module m; endmodule\n"})["ok"]
    r = dispatch(session, "read_file", {"path": "rtl/new.sv"})
    assert r["output"] == "module m; endmodule\n"
    assert "rtl/new.sv" in dispatch(session, "list_files", {"path": "rtl"})["output"]
    for bad in ({"path": "../x", "content": "a"}, {"path": "build/gates.json", "content": "{}"}):
        assert dispatch(session, "write_file", bad)["refused"]


def test_constraints_checker_t1_is_clean_and_the_btnc_trap_is_caught() -> None:
    t1 = (ROOT / "designs" / "t1_dimmer_counter" / "design.xdc").read_text()
    assert check_xdc(t1, BOARD) == [] and check_xdc_safety(t1) == []
    rules = {f["rule"] for f in check_xdc(BTNC_TRAP, BOARD)}
    assert {"FDA-CON-1", "FDA-CON-2"} <= rules


def test_constraints_checker_pins_and_iostandard() -> None:
    bad = "set_property -dict { PACKAGE_PIN E3 IOSTANDARD LVCMOS18 } [get_ports { BTNC }];\n"
    msgs = " ".join(f["message"] for f in check_xdc(bad, BOARD))
    assert "FDA-CON-3" in {f["rule"] for f in check_xdc(bad, BOARD)} and "master XDC" in msgs


@pytest.mark.parametrize("line", ["exec rm -rf /tmp/x", "source /tmp/evil.tcl", "set_property X Y [exec id]",
                                  "puts [open /etc/passwd]", "set x [exec ls]", "set_false_path -from $undefined",
                                  "file delete -force /tmp/x"])
def test_xdc_allow_list_refuses_free_form_tcl(line: str) -> None:
    assert any(f["rule"] == "FDA-CON-6" for f in check_xdc_safety(line + "\n")), line


def test_build_refuses_a_hostile_xdc_and_build_yaml(session) -> None:
    (session.design / "design.xdc").write_text("exec touch /tmp/pwned\n")
    r = dispatch(session, "build", {})
    assert r["refused"] and r["rule"] == "tcl-allow-list" and not session.runner.calls
    # build.yaml values reach Tcl
    yml = (session.design / "build.yaml").read_text()
    for old, new in (("top: t1_dimmer_counter_top", "top: t1_dimmer_counter_top; exec x"),
                     ("part: xc7a100tcsg324-1", "part: 'xc7a100tcsg324-1}; exec id; {'")):
        assert old in yml
        (session.design / "build.yaml").write_text(yml.replace(old, new))
        assert dispatch(session, "build", {})["rule"] == "build-yaml"
    (session.design / "build.yaml").write_text(yml.replace("generics: {}", "generics: {X: \"1}; exec id; {\"}"))
    assert dispatch(session, "build", {})["rule"] == "build-yaml"
    (session.design / "build.yaml").write_text(yml.replace("- designs/t1_dimmer_counter/design.xdc", "- ../../../../etc/passwd"))
    assert dispatch(session, "build", {})["rule"] == "build-yaml"


def test_fixed_commands(session) -> None:
    session.runner = FakeRunner()
    for tool, args in (("lint", {}), ("simulate", {"sim": "verilator"}), ("build", {"until": "synth"})):
        r = dispatch(session, tool, args)
        assert r["ok"], (tool, r["output"])
    kinds = dict((k, a) for k, a in session.runner.calls)
    assert kinds["lint"][:4] == ["verilator", "--lint-only", "-Wall", "--top-module"]
    assert kinds["build"][0].endswith("flow/run_vivado.sh") and kinds["build"][2] == "base"
    assert "-m" in kinds["simulate"] and "pytest" in kinds["simulate"]
    assert dispatch(session, "build", {"until": "synth", "variant": "ila"})["refused"]
    assert dispatch(session, "build", {"until": "bogus"})["rule"] == "arguments"


def test_source_scan_refuses_calls_out_of_the_simulator(session) -> None:
    (session.design / "tests" / "evil_rtl_helper.py").write_text("import subprocess\nsubprocess.run(['id'])\n")
    r = dispatch(session, "simulate", {})
    assert r["refused"] and r["rule"] == "source-scan" and "evil_rtl_helper.py" in r["output"]
    (session.design / "tests" / "evil_rtl_helper.py").unlink()
    (session.design / "rtl" / "x.sv").write_text("module x; initial $system(\"id\"); endmodule\n")
    assert dispatch(session, "lint", {})["rule"] == "source-scan"


def test_report_name_is_restricted(session) -> None:
    (session.design / "build" / "base").mkdir(parents=True)
    (session.design / "build" / "base" / "power.rpt").write_text("Total On-Chip Power (W) | 0.15\n")
    assert dispatch(session, "report", {"name": "power.rpt"})["output"].startswith("Total")
    for bad in ("../../../etc/passwd", "a/b.rpt", "x.sh"):
        assert dispatch(session, "report", {"name": bad})["rule"] == "arguments"


def test_knowledge_text_is_data(session) -> None:
    r = dispatch(session, "search_docs", {"query": "clock"})
    assert r["ok"] and r["untrusted"] and "untrusted data" in r["output"]
    assert dispatch(session, "load_skill", {"sections": ["clocking"]})["untrusted"]


def test_stage_note_sets_the_stage(session) -> None:
    assert session.stage == "clarify"
    dispatch(session, "stage_note", {"stage": "synthesis", "text": "run synth"})
    assert session.stage == "synthesis" and "run synth" in (session.design / "BUILD_NOTE.md").read_text()
    assert dispatch(session, "stage_note", {"stage": "party", "text": "x"})["rule"] == "arguments"


# --- hardware ------------------------------------------------------------------------------------------------------

def test_program_policy(session, board_file) -> None:
    assert dispatch(session, "program", {"variant": "base"})["rule"] == "hardware-stage"   # wrong stage
    stage_hw(session)
    for bad in ("flash", "qspi", "sram; write_cfgmem"):
        assert dispatch(session, "program", {"target": bad})["rule"] == "hardware-flash"
    assert dispatch(session, "program", {"serial": "X"})["rule"] == "arguments"            # no serial argument exists
    session.runner = FakeRunner({"program": RunResult(0, "ok", "", 1.0)})
    r = dispatch(session, "program", {"variant": "base"})
    assert r["ok"], r["output"]
    argv = session.runner.calls[-1][1]
    assert argv[1].endswith("flow/program.py") and "--flash" not in argv and "210292AE3B73" not in argv
    assert session.hw.used == 1


def test_program_refuses_over_power(session, board_file) -> None:
    stage_hw(session, power_report="bad_power.rpt")
    r = dispatch(session, "program", {})
    assert r["rule"] == "hardware-power" and not session.runner.calls and session.hw.used == 0


def test_program_needs_a_board_and_a_build(session, tmp_path, monkeypatch) -> None:
    from flow import hw
    monkeypatch.setattr(hw, "BOARDS_FILE", tmp_path / "none.yaml")
    session.stage = "configuration-and-debug"
    assert dispatch(session, "program", {})["rule"] == "hardware-board"


def test_hardware_budget_is_enforced_in_dispatch(session, board_file) -> None:
    stage_hw(session)
    session.hw.budget = 1
    assert dispatch(session, "program", {})["ok"]
    assert dispatch(session, "program", {})["rule"] == "hardware-budget"


def test_cable_serial_is_redacted_from_output(session, board_file) -> None:
    stage_hw(session)
    session.runner = FakeRunner({"program": RunResult(0, "target 210292AE3B73 programmed", "", 1.0)})
    r = dispatch(session, "program", {})
    assert "210292AE3B73" not in json.dumps(r)
