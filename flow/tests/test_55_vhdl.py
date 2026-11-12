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


def test_integer_value_for_a_vector_generic_is_fitted(tmp_path):
    """Mistake M3 (an agent run, brief 55): the bench passed BUILD_STAMP=0 and GHDL 4.1 synthesis crashed."""
    f = tmp_path / "t.vhd"
    f.write_text("library ieee; use ieee.std_logic_1164.all;\nentity t is\n  generic (N : integer := 4;\n"
                 "    BUILD_STAMP : std_logic_vector(31 downto 0) := x\"00000000\");\n  port (q : out std_logic); end;\n"
                 "architecture r of t is begin q <= BUILD_STAMP(0); end;\n")
    assert vhdl.entity_generics(f.read_text(), "t") == {"n": "integer", "build_stamp": "std_logic_vector(31 downto 0)"}
    assert vhdl.fit_generics([f], "t", {"BUILD_STAMP": 5, "N": 3}) == {"BUILD_STAMP": format(5, "032b"), "N": 3}


@needs_ghdl
def test_netlist_with_an_integer_build_stamp(tmp_path):
    vh = sorted((B / "t1_gray_stepper" / "rtl").glob("*.vhd"))
    net = vhdl.to_verilog(vh, "t1_gray_stepper_top", {"CLKS_PER_BIT": 8, "BUILD_STAMP": 0}, tmp_path)
    assert "parameter BUILD_STAMP = 0" in net.read_text()


@needs_ghdl
def test_lint_refuses_an_unbound_component_that_is_not_the_shell(tmp_path):
    """Review fix S4: only the test shell's modules may stay black boxes."""
    f = tmp_path / "top.vhd"
    f.write_text("library ieee; use ieee.std_logic_1164.all;\nentity top is port (a : in std_logic; y : out std_logic); end;\n"
                 "architecture r of top is\n  component my_missing_blk is port (a : in std_logic; y : out std_logic); end component;\n"
                 "begin\n  u : my_missing_blk port map (a => a, y => y);\nend;\n")
    r = vhdl.lint([f], "top", workdir=tmp_path / "w")
    assert not r["ok"] and "[vhdl unbound] component my_missing_blk" in r["output"]
    vh = sorted((B / "t1_gray_stepper" / "rtl").glob("*.vhd"))     # the shell (and sync2) stay allowed
    assert vhdl.lint(vh, "t1_gray_stepper_top", workdir=tmp_path / "w2")["ok"]


@needs_ghdl
def test_lint_fits_generic_values(tmp_path):
    """Review fix S5: BUILD_STAMP=0 or a literal of another width no longer crashes GHDL in the lint."""
    vh = sorted((B / "t1_gray_stepper" / "rtl").glob("*.vhd"))
    for v in (0, "8'hFF", "4'd20"):
        r = vhdl.lint(vh, "t1_gray_stepper_top", {"BUILD_STAMP": v, "CLKS_PER_BIT": 8}, workdir=tmp_path / "w")
        assert r["ok"], (v, r["output"])
    assert vhdl.fit_generics(vh, "t1_gray_stepper_top", {"BUILD_STAMP": "8'hFF"})["BUILD_STAMP"] == format(0xFF, "032b")


@needs_ghdl
def test_agent_lint_tool_on_vhdl(tmp_path):
    """The agent's `lint` tool on a VHDL design: a translation passes; an unbound non-shell component and a BUILD_STAMP=0
    generic are handled (review fixes S4, S5)."""
    import shutil
    from agent.core import tools as T
    from agent.core.session import Session
    d = ROOT / "runs" / f"_t55_{tmp_path.name}"
    shutil.rmtree(d, ignore_errors=True)
    try:
        (d / "rtl").mkdir(parents=True)
        for f in (B / "t1_gray_stepper" / "rtl").glob("*.vhd"):
            shutil.copy(f, d / "rtl" / f.name)
        (d / "design.xdc").write_text("# none\n")
        rel = d.relative_to(ROOT)
        (d / "build.yaml").write_text(f"top: t1_gray_stepper_top\npart: xc7a100tcsg324-1\nsources: [shell/rtl/*.sv, {rel}/rtl/*.vhd]\n"
                                      f"constraints: [{rel}/design.xdc]\ngenerics: {{BUILD_STAMP: 0}}\n")
        (d / ".hdl").write_text("vhdl\n")
        r = T.lint(Session(design=d))
        assert r["ok"], r["output"]
        top = d / "rtl" / "t1_gray_stepper_top.vhd"
        top.write_text(top.read_text().replace("architecture", "-- extra\narchitecture", 1).replace(
            "begin", "  component nowhere is port (q : out std_logic); end component;\n  signal nq : std_logic;\nbegin\n"
            "  u_nowhere : nowhere port map (q => nq);", 1))
        r = T.lint(Session(design=d))
        assert not r["ok"] and "[vhdl unbound] component nowhere" in r["output"], r["output"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_spec_language_switches_the_run_to_vhdl(tmp_path):
    """Review fix S3: `language: vhdl` in spec.yaml without --hdl vhdl gives the VHDL conventions, the marker and the GHDL image."""
    from types import SimpleNamespace
    from agent.core.runner import SIM_IMAGE, SIM_IMAGE_VHDL, ContainerRunner, container_available
    from agent.graph.run import Config, follow_spec_language
    d = tmp_path / "des"
    d.mkdir()
    runner = ContainerRunner(d, ROOT, image=SIM_IMAGE)
    rt = SimpleNamespace(cfg=Config(spec_md=d / "spec.md", name="des", board="nexys_a7_100t", interview="off",
                                    review="off", model="m", hidden_spec=None, stop_after=None),
                         design=d, session=SimpleNamespace(runner=runner))
    assert not follow_spec_language(rt) and rt.cfg.hdl == "sv"           # no spec.yaml yet
    (d / "spec.yaml").write_text("language: systemverilog\n")
    assert not follow_spec_language(rt) and rt.cfg.hdl == "sv"
    (d / "spec.yaml").write_text("language: VHDL\n")
    assert follow_spec_language(rt) and rt.cfg.hdl == "vhdl"
    assert vhdl.design_language(d) == "vhdl"
    assert runner.image == (SIM_IMAGE_VHDL if container_available(image=SIM_IMAGE_VHDL) else SIM_IMAGE)
    assert not follow_spec_language(rt)                                  # once only


def test_lint_command_line_reads_a_directory(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.vhd").write_text("entity a is end entity;\n")
    seen = {}
    monkeypatch.setattr(vhdl, "lint", lambda files, top: seen.update(files=files, top=top) or {"ok": True, "output": ""})
    assert vhdl.main(["lint", str(tmp_path), "--top", "a"]) == 0
    assert seen == {"files": [tmp_path / "a.vhd"], "top": "a"} and capsys.readouterr().out.strip() == "ok"
