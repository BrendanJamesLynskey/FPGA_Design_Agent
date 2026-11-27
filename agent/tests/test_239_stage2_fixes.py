"""Brief 239: the stage-2 failure census found rules that fire on correct work (FDA-CON-8 on internal ports, STD-CDC-01 on a supplied module,
Verilator style warnings in a supplied read-only file) and a harness gap (the independent bench's build omitted data/). Each fix is tested here;
none of them weakens a rule for the design's own code. Evidence: results/239_stage2_diagnosis/."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from agent.core import constraints as con


def test_internal_spec_ports_are_not_top_ports() -> None:
    spec = {"ports": [{"name": "clk_in", "direction": "input"}, {"name": "jtag_bus.h_we", "direction": "internal"},
                      {"name": "led", "direction": "output"}, {"name": "jtag_bus internal (clk, rst)", "direction": "Internal"}]}
    assert con.spec_port_names(spec) == ["clk_in", "led"]
    assert con.spec_port_names({"ports": {"a": {"direction": "internal"}, "b": {"direction": "in"}}}) == ["b"]
    f = con.check_top_ports("top", {"clk_in", "led"}, con.spec_port_names(spec), None, Path(__file__).resolve().parents[2] / "boards" / "nexys_a7_100t", shell=False)
    assert not [x for x in f if x["rule"] == "FDA-CON-8"]


def test_a_missing_real_port_is_still_fda_con_8() -> None:
    spec = {"ports": [{"name": "clk_in", "direction": "input"}, {"name": "led", "direction": "output"}, {"name": "h_we", "direction": "internal"}]}
    f = con.check_top_ports("top", {"clk_in"}, con.spec_port_names(spec), None, Path(__file__).resolve().parents[2] / "boards" / "nexys_a7_100t", shell=False)
    assert [x["rule"] for x in f] == ["FDA-CON-8"] and "led" in f[0]["message"]


def test_the_waiver_names_supplied_data_files_only_for_the_style_rules(tmp_path) -> None:
    from agent.core.tools import STUB_RULES, stub_waiver_vlt
    d = tmp_path / "d"
    t = stub_waiver_vlt([str(d / "rtl" / "top.sv"), str(d / "data" / "jtag_bus.sv")], d / "data")
    assert "jtag_bus.sv" in t and "top.sv" not in t and t.count("\n") == len(STUB_RULES) + 1
    assert stub_waiver_vlt([str(d / "rtl" / "top.sv")], d / "data") == ""
    assert stub_waiver_vlt([str(d / "data" / "jtag_bus.sv")]) == ""            # no supplied directory given: unchanged from brief 231


def test_verilator_ignores_style_in_the_supplied_file_but_not_in_the_design(tmp_path) -> None:
    exe = shutil.which("verilator")
    if not exe:
        pytest.skip("verilator not installed")
    from agent.core.tools import stub_waiver_vlt
    (tmp_path / "data").mkdir()
    (tmp_path / "rtl").mkdir()
    sup, top = tmp_path / "data" / "jtag_bus.sv", tmp_path / "rtl" / "top.sv"
    sup.write_text("module jtag_bus (input logic clk, input logic tdo, output logic y);\n  logic [3:0] cmd_s;\n  assign y = clk;\nendmodule\n")
    top.write_text("module top (input logic clk, input logic a, output logic y);\n  logic [1:0] spare;\n  jtag_bus u (.clk(clk), .tdo(a), .y(y));\nendmodule\n")
    (tmp_path / "w.vlt").write_text(stub_waiver_vlt([str(sup), str(top)], tmp_path / "data"))
    r = subprocess.run([exe, "--lint-only", "-Wall", "--top-module", "top", str(tmp_path / "w.vlt"), str(top), str(sup)], capture_output=True, text=True)
    assert "jtag_bus.sv" not in r.stderr, r.stderr
    assert "'spare'" in r.stderr                                                # the design's own unused signal is still reported


def test_standards_cdc_01_accepts_a_supplied_module_and_still_rejects_an_unknown_one(tmp_path) -> None:
    from flow import standards_check as sc
    from flow.tests.test_standards_check import CLEAN, make

    def msgs(root: Path, inline_in: str) -> list[str]:
        arch = {"crossings": [{"from": "async", "to": "sys", "signal": "tck", "primitive": "xpm_cdc_single", "inline_in": inline_in}]}
        d = make(root, CLEAN, arch)
        (d / "data").mkdir()
        (d / "data" / "jtag_bus.sv").write_text("module jtag_bus(input logic clk, output logic q);\nendmodule\n")
        res = {r["id"]: r for r in sc.evaluate(d, root, stages=("rtl",))["rules"]}
        return [f["message"] for f in res["STD-CDC-01"]["findings"]]
    assert not any("not a module" in m for m in msgs(tmp_path / "a", "jtag_bus"))
    assert any("not a module" in m for m in msgs(tmp_path / "b", "no_such_module"))


def test_the_spec_bench_entry_builds_the_supplied_data_sources() -> None:
    from agent.graph.spectest import ENTRY_TEMPLATE
    assert "srcorder.data_files(DESIGN_DIR)" in ENTRY_TEMPLATE and '(".sv", ".v")' in ENTRY_TEMPLATE
    compile(ENTRY_TEMPLATE, "entry", "exec")                                   # still valid Python


def test_the_rules_note_lists_ids_codes_fixes_and_the_waiver_file(monkeypatch) -> None:
    from agent.graph.run import stage2_rules_note
    t = stage2_rules_note()
    assert "FDA-CON-8" in t and "lint/waivers.yaml" in t and "direction: internal" in t
    assert "HDL-SIG-01 (Verilator UNDRIVEN" in t and "HDL-SYN-01 (Verilator LATCH" in t
    assert "-00" not in t                                                      # the catch-all rules are not advice
    from flow.lint_ruleset import load_rules
    ids = [r["id"] for r in load_rules()["rules"] if (r.get("checks") or {}).get("verilator") and not r["id"].endswith("-00")]
    assert all(i in t for i in ids)                                            # built from the rule file, so it cannot drift


def test_a_module_named_like_an_amd_primitive_is_refused_in_a_synthesis_source() -> None:
    f = con.primitive_name_findings({"xilinx_sim_stubs.sv": ["xpm_cdc_async_rst", "BSCANE2", "my_reset_gen"], "top.sv": ["MMCME2_ADV", "freq_top"]})
    assert sorted(x["text"] for x in f) == ["module BSCANE2", "module MMCME2_ADV", "module xpm_cdc_async_rst"]
    assert all(x["rule"] == "FDA-CON-16" and "sim/" in x["message"] for x in f)
    assert con.primitive_name_findings({"top.sv": ["freq_top", "sync_ff"]}) == []


def test_only_build_sources_are_checked_for_primitive_names(tmp_path) -> None:
    from agent.core.tools import primitive_findings

    class S:       # the attributes primitive_findings reads
        root = tmp_path
        design = tmp_path / "d"
    (S.design / "rtl").mkdir(parents=True)
    (S.design / "sim").mkdir()
    (S.design / "data").mkdir()
    (S.design / "rtl" / "top.sv").write_text("module top(input logic a, output logic y);\nassign y = a;\nendmodule\n")
    (S.design / "rtl" / "stubs.sv").write_text("module xpm_cdc_async_rst(input logic a, output logic y);\nassign y = a;\nendmodule\n")
    (S.design / "sim" / "xilinx_sim_stubs.sv").write_text("module BSCANE2(input logic a);\nendmodule\n")
    (S.design / "data" / "jtag_bus.sv").write_text("module BUFG(input logic a);\nendmodule\n")
    f = primitive_findings(S(), {"sources": ["d/rtl/*.sv", "d/data/*.sv"]})
    assert [x["text"] for x in f] == ["module xpm_cdc_async_rst"]            # sim/ is not a source, data/ is supplied


def test_the_primitive_name_rule_is_advisory_in_lint_and_a_warning_in_build() -> None:
    import inspect
    from agent.core import tools
    src = inspect.getsource(tools.lint)
    assert "[advisory]" in src and "primitive_findings" in src
    assert "WARNING" in inspect.getsource(tools.build) and "primitive_findings" in inspect.getsource(tools.build)
