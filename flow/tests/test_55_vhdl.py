"""Brief 55: VHDL in the flow, the parts that need no simulator (GHDL-dependent checks skip without GHDL).

The simulator tests (GHDL netlist under Icarus, native GHDL, formal) are in test_55_vhdl_rtl.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from flow import vhdl

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "results" / "55_vhdl" / "translations" / "B"
needs_ghdl = pytest.mark.skipif(vhdl.ghdl_exe() is None, reason="GHDL not installed")


def test_generic_values_convert_verilog_literals():
    assert vhdl.generic_value("32'hDEADBEEF") == format(0xDEADBEEF, "032b")
    assert vhdl.generic_value("4'b1010") == "1010"
    assert vhdl.generic_value(8) == "8"
    assert vhdl.generic_value(True) == "true"
    assert vhdl.generic_args({"CLKS_PER_BIT": 8}) == ["-gCLKS_PER_BIT=8"]


def test_order_puts_packages_and_entities_before_their_users(tmp_path):
    use = tmp_path / "a_top.vhd"
    use.write_text("use work.my_pkg.all;\nentity a_top is end;\narchitecture r of a_top is begin\n"
                   "u : entity work.leaf port map (x => open);\nend;\n")
    leaf = tmp_path / "b_leaf.vhd"
    leaf.write_text("entity leaf is port (x : out bit); end;\narchitecture r of leaf is begin x <= '0'; end;\n")
    pkg = tmp_path / "c_pkg.vhd"
    pkg.write_text("package my_pkg is constant N : integer := 3; end package;\n")
    order = [p.name for p in vhdl.order_vhdl([use, leaf, pkg])]
    assert order.index("c_pkg.vhd") < order.index("a_top.vhd") and order.index("b_leaf.vhd") < order.index("a_top.vhd")
    mixed = vhdl.order_sources([use, ROOT / "shell" / "rtl" / "fpga_shell.sv", pkg])
    assert mixed[0].suffix == ".sv"


def test_top_entity_and_ports_of_a_translation():
    vh = sorted((B / "t1_gray_stepper" / "rtl").glob("*.vhd"))
    assert vhdl.top_entity(vh, "T1_GRAY_STEPPER_TOP").lower() == "t1_gray_stepper_top"
    ports = vhdl.entity_ports((B / "t1_gray_stepper" / "rtl" / "t1_gray_stepper_top.vhd").read_text(), "t1_gray_stepper_top")
    assert {"CLK100MHZ", "CPU_RESETN", "LED", "UART_TXD_IN", "UART_RXD_OUT"} <= set(ports)
    assert ports["LED"] == "out"


def test_shell_name_clash_is_found(tmp_path):
    f = tmp_path / "sync2.vhd"
    f.write_text("library ieee; use ieee.std_logic_1164.all;\nentity sync2 is port (clk : in std_logic); end;\n")
    clash = vhdl.shell_name_clashes([f])
    assert clash and "sync2" in clash[0]
    assert vhdl.shell_modules() >= {"fpga_shell", "sync2", "reset_sync", "uart_rx", "uart_tx", "shell_core"}


def test_design_language(tmp_path):
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    assert vhdl.design_language(d) == "sv"
    (d / "rtl" / "top.vhd").write_text("--\n")
    assert vhdl.design_language(d) == "vhdl"
    (d / "spec.yaml").write_text("language: systemverilog\n")
    assert vhdl.design_language(d) == "sv"
    (d / "spec.yaml").write_text("language: vhdl\n")
    assert vhdl.design_language(d) == "vhdl"


def test_declare_params_adds_a_header():
    net = "module t1_top\n  (input clk);\nendmodule\n"
    out = vhdl.declare_params(net, "t1_top", {"CLKS_PER_BIT": 8, "BUILD_STAMP": "32'h0"})
    assert out.startswith("module t1_top #(parameter CLKS_PER_BIT = 8, parameter BUILD_STAMP = 32'h0)")


def test_vhdl_mutation_operators():
    from flow import mutate
    cands = mutate.generate_candidates(B / "t1_sync_fifo_regs" / "rtl")
    classes = {c["class"] for c in cands}
    assert {"eq_to_ne", "bit0_to_1", "bit1_to_0"} <= classes
    c = next(x for x in cands if x["class"] == "eq_to_ne")
    src = (B / "t1_sync_fifo_regs" / "rtl" / c["file"]).read_text()
    new = mutate.apply_mutant(c, src)
    assert new is not None and new != src and "/=" in new.splitlines()[c["line"] - 1]


def test_vhdl_conventions_name_the_boundary():
    from agent.graph.run import conventions_text
    fmt = {"board": "nexys_a7_100t", "name": "x", "stage": 2, "stage_name": "rtl-design-creation", "allowed": "",
           "fails": "none", "note": "none", "design_rel": "runs/r/x", "no_shell": False}
    sv = conventions_text(fmt)
    vh = conventions_text({**fmt, "hdl": "vhdl"})
    assert "VHDL-2008" not in sv
    assert "THIS DESIGN IS WRITTEN IN VHDL-2008" in vh and "component fpga_shell" in vh
    assert "runs/r/x/rtl/*.vhd" in vh and 'glob("*.vhd")' in vh
    assert "std_logic_vector(31 downto 0)" in vh


def test_spec_language_key():
    from agent.graph.spec_schema import validate
    assert not any("language" in e for e in validate({"language": "vhdl"}))
    assert any("language" in e for e in validate({"language": "verilog-2001"}))


@needs_ghdl
def test_lint_refuses_a_latch_and_a_second_driver(tmp_path):
    lat = tmp_path / "lat.vhd"
    lat.write_text("library ieee; use ieee.std_logic_1164.all;\nentity lat is port (en, d : in std_logic; q : out std_logic); end;\n"
                   "architecture rtl of lat is begin process (en, d) begin if en = '1' then q <= d; end if; end process; end;\n")
    r = vhdl.lint([lat], "lat", workdir=tmp_path / "w1")
    assert not r["ok"] and "latch" in r["output"]
    md = tmp_path / "md.vhd"
    md.write_text("library ieee; use ieee.std_logic_1164.all;\nentity md is port (clk, a, b : in std_logic; q : out std_logic); end;\n"
                  "architecture rtl of md is signal s : std_logic; begin\n"
                  "p1 : process (clk) begin if rising_edge(clk) then s <= a; end if; end process;\n"
                  "p2 : process (clk) begin if rising_edge(clk) then s <= b; end if; end process;\nq <= s; end;\n")
    r = vhdl.lint([md], "md", workdir=tmp_path / "w2")
    assert not r["ok"] and "multiple assignments" in r["output"]


@needs_ghdl
def test_lint_passes_a_translation_and_names_the_shell_clash():
    vh = sorted((B / "t1_gray_stepper" / "rtl").glob("*.vhd"))
    assert vhdl.lint(vh, "t1_gray_stepper_top", {"CLKS_PER_BIT": 8})["ok"]
    a = sorted((ROOT / "results" / "55_vhdl" / "translations" / "A" / "t1_gray_stepper" / "rtl").glob("*.vhd"))
    r = vhdl.lint(a, "t1_gray_stepper_top")
    assert not r["ok"] and "[vhdl boundary]" in r["output"]


@needs_ghdl
def test_netlist_keeps_the_shell_as_a_black_box(tmp_path):
    vh = sorted((B / "t1_gray_stepper" / "rtl").glob("*.vhd"))
    net = vhdl.to_verilog(vh, "t1_gray_stepper_top", {"CLKS_PER_BIT": 8, "BUILD_STAMP": "32'h12345678"}, tmp_path)
    text = net.read_text()
    assert "module t1_gray_stepper_top #(parameter CLKS_PER_BIT = 8" in text
    assert "fpga_shell #(" in text and "module fpga_shell" not in text
