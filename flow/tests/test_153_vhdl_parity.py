"""Brief 153 (review item F9): VHDL parity of the gates. Every reader that was ported to VHDL, and every reader that now says it has no
reader, is tested on a VHDL fixture, with the SystemVerilog behaviour next to it so a port cannot change it."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from flow import checks as C
from flow import derived_constants as DC
from flow import sources as S
from flow import vhdl

ROOT = Path(__file__).resolve().parents[2]
HAVE_GHDL = vhdl.ghdl_exe() is not None
needs_ghdl = pytest.mark.skipif(not HAVE_GHDL, reason="GHDL is not installed")

SPEC = 'The design ID is "GRAY". The register at 0 is the identification word.\n'

TOP_VHDL = """library ieee;
use ieee.std_logic_1164.all;

entity fx_top is
  generic (BUILD_STAMP : std_logic_vector(31 downto 0) := x"00000000");
  port (CLK100MHZ : in std_logic; CPU_RESETN : in std_logic; UART_TXD_IN : in std_logic; UART_RXD_OUT : out std_logic;
        LED : out std_logic_vector(3 downto 0));
end entity fx_top;

architecture rtl of fx_top is
{shell}
  constant ID : std_logic_vector(31 downto 0) := x"47524159";   -- "GRAY"
  signal rst : std_logic;
  signal win_addr : std_logic_vector(6 downto 0);
  signal win_wr, win_rd : std_logic;
  signal win_wdata, win_rdata : std_logic_vector(31 downto 0);
begin
  rst <= not CPU_RESETN;
  win_rdata <= (others => '0');
  LED <= (others => '0');
  u_shell : fpga_shell
    generic map (DESIGN_ID => {id}, BUILD_STAMP => {stamp})
    port map (clk => CLK100MHZ, rst => rst, uart_rx => UART_TXD_IN, uart_tx => UART_RXD_OUT, win_addr => win_addr, win_wr => win_wr,
              win_rd => win_rd, win_wdata => win_wdata, win_rdata => win_rdata);
{extra}
end architecture rtl;
"""


def vhdl_top(id_expr: str = 'x"47524159"', stamp: str = "BUILD_STAMP", extra: str = "") -> str:
    return TOP_VHDL.format(shell=vhdl.SHELL_COMPONENT, id=id_expr, stamp=stamp, extra=extra)


def make_design(tmp: Path, files: dict[str, str], spec: str | None = SPEC, build: dict | None = None, top: str = "fx_top") -> Path:
    """A design directory under ``tmp`` (which acts as the repo root: build.yaml's globs are relative to it)."""
    d = tmp / "d"
    (d / "rtl").mkdir(parents=True)
    for n, t in files.items():
        (d / "rtl" / n).write_text(t)
    if spec is not None:
        (d / "spec.md").write_text(spec)
    exts = {Path(n).suffix for n in files}
    cfg = {"top": top, "sources": [f"d/rtl/*{e}" for e in sorted(exts)], "constraints": []}
    cfg.update(build or {})
    (d / "build.yaml").write_text(yaml.safe_dump(cfg))
    return d


# ---- flow/sources.py ----------------------------------------------------------------------------------------------------
def test_language_by_suffix() -> None:
    assert [S.language(x) for x in ("a.sv", "a.V", "a.svh", "a.vh", "a.vhd", "a.VHDL", "a.py", "a.xdc")] == \
        ["sv", "sv", "header", "header", "vhdl", "vhdl", None, None]


def test_by_language_keeps_order_and_drops_other_files() -> None:
    g = S.by_language(["b.vhd", "a.sv", "x.tcl", "c.vhdl", "h.svh"])
    assert g == {"sv": [Path("a.sv")], "header": [Path("h.svh")], "vhdl": [Path("b.vhd"), Path("c.vhdl")]}


def test_no_reader_names_the_files_and_the_reader() -> None:
    t = S.no_reader([Path("a.sv"), Path("x.vhd"), Path("y.vhd")], {"sv"}, "the thing")
    assert t == "no reader for .vhd (2 file(s): x.vhd, y.vhd): the thing reads SystemVerilog only"
    assert S.no_reader([Path("a.sv"), Path("h.svh")], {"sv"}, "x") is None            # headers are SystemVerilog
    assert S.no_reader([Path("x.vhd")], {"sv", "vhdl"}, "x") is None
    assert "(+2 more)" in S.no_reader([Path(f"f{i}.vhd") for i in range(5)], {"sv"}, "x")
    assert S.no_reader([], {"sv"}, "x") is None


def test_strip_comments_per_language() -> None:
    assert S.strip_comments("a -- b\nc", "vhdl") == "a     \nc"
    assert S.strip_comments("a // b\nc /* d\ne */ f", "sv") == "a     \nc     \n     f"
    assert "--" not in S.strip_comments("x -- y /* z */ w", "vhdl")


@pytest.mark.parametrize("expr,val", [('x"47524159"', 0x47524159), ('X"4752_4159"', 0x47524159), ('32x"47524159"', 0x47524159), ('b"0101"', 5),
                                      ('o"17"', 15), ("16#47524159#", 0x47524159), ("5", 5), ("1_000", 1000), ('"GRAY"', 0x47524159),
                                      ('x"4U"', None), ("some_name", None), ("to_unsigned(5, 8)", None)])
def test_vhdl_literals(expr: str, val: int | None) -> None:
    assert S.parse_vhdl_literal(expr) == val


def test_build_sources_without_build_yaml_includes_vhdl(tmp_path: Path) -> None:
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    for n in ("a.sv", "b.vhd", "c.v", "notes.txt"):
        (d / "rtl" / n).write_text("x")
    assert [p.name for p in S.build_sources(d, tmp_path)] == ["a.sv", "b.vhd", "c.v"]
    assert [p.name for p in S.design_rtl(d)] == ["a.sv", "b.vhd", "c.v"]
    assert C.build_sources(d, tmp_path) == S.build_sources(d, tmp_path)               # the checks' name is the shared one


def test_the_reader_table_matches_the_probe() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import vhdl_parity_probe as P
    assert {r for r, _, _ in S.COVERAGE if r != "--"} == {r["id"] for r in P.READERS}


def test_the_command_prints_the_table(capsys) -> None:
    assert S.main([]) == 0
    out = capsys.readouterr().out
    assert "no reader" in out and "R05" in out


# ---- R05: the derived-constants check ------------------------------------------------------------------------------------
def test_wrong_design_id_in_vhdl_is_caught(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top(id_expr='x"47524158"')})
    r = DC.derive(d, tmp_path)
    assert [f["code"] for f in r["findings"] if f["blocking"]] == ["CONST-ID-01"]
    assert "0x47524158" in r["findings"][0]["message"] and "0x47524159" in r["findings"][0]["message"]
    assert r["findings"][0]["where"].endswith("fx_top.vhd")


def test_right_design_id_in_vhdl_is_clean_in_every_literal_form(tmp_path: Path) -> None:
    for form in ('x"47524159"', 'X"4752_4159"', "16#47524159#", '"GRAY"', "ID"):
        d = make_design(tmp_path / form.replace('"', "q").replace("#", "h")[:6], {"fx_top.vhd": vhdl_top(id_expr=form)})
        r = DC.derive(d, tmp_path / form.replace('"', "q").replace("#", "h")[:6])
        assert r["findings"] == [] and r["not_read"] == [], (form, r)
        assert r["design_id_bindings"][0]["value"] == 0x47524159


def test_vhdl_design_id_through_a_generic_default(tmp_path: Path) -> None:
    top = vhdl_top(id_expr="MY_ID").replace("generic (BUILD_STAMP", 'generic (MY_ID : std_logic_vector(31 downto 0) := x"47524158"; BUILD_STAMP')
    r = DC.derive(make_design(tmp_path, {"fx_top.vhd": top}), tmp_path)
    assert [f["code"] for f in r["findings"] if f["blocking"]] == ["CONST-ID-01"], r


def test_vhdl_design_id_that_is_not_a_literal_makes_the_check_partial(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top(id_expr="to_stdlogicvector(ID)")})
    r = C.run_one("constants", d, "rtl", root=tmp_path)
    assert r["status"] == "pass" and r["incomplete"] == ["design_id"], r                  # not a clean pass: PARTIAL
    assert "not a literal" in r["parts"]["design_id"]


def test_quoted_id_but_no_shell_instance_in_vhdl_is_partial(tmp_path: Path) -> None:
    top = vhdl_top().replace("u_shell : fpga_shell", "u_other : other_thing")
    r = C.run_one("constants", make_design(tmp_path, {"fx_top.vhd": top}), "rtl", root=tmp_path)
    assert r["incomplete"] == ["design_id"] and "fpga_shell" in r["parts"]["design_id"], r


def test_sv_constants_unchanged_and_not_partial(tmp_path: Path) -> None:
    sv = "module top; fpga_shell #(.DESIGN_ID(32'h47524158), .BUILD_STAMP(0)) u_shell (.clk(c)); endmodule\n"
    r = C.run_one("constants", make_design(tmp_path, {"top.sv": sv}, top="top"), "rtl", root=tmp_path)
    assert r["status"] == "fail" and [f["code"] for f in r["findings"]] == ["CONST-ID-01"] and r["incomplete"] == []
    sv2 = "module top; endmodule\n"                                         # no shell: the old note, still not a failure or a partial
    r = C.run_one("constants", make_design(tmp_path / "b", {"top.sv": sv2}, top="top"), "rtl", root=tmp_path / "b")
    assert r["status"] == "pass" and r["incomplete"] == []


def test_the_planted_constant_in_the_brief_55_translation_is_caught(tmp_path: Path) -> None:
    """The brief 55 VHDL path: the arm B translation of t1_gray_stepper, its shell binding changed by one character."""
    src = ROOT / "results" / "55_vhdl" / "translations" / "B" / "t1_gray_stepper" / "rtl"
    spec = (ROOT / "benchmark" / "tasks" / "t1_gray_stepper" / "spec.md").read_text()
    good = {f.name: f.read_text() for f in src.glob("*.vhd")}
    assert 'x"47524159"' in good["t1_gray_stepper_top.vhd"]
    r = DC.derive(make_design(tmp_path / "ok", good, spec, top="t1_gray_stepper_top"), tmp_path / "ok")
    assert r["findings"] == [] and r["design_id_bindings"][0]["value"] == 0x47524159
    bad = dict(good, **{"t1_gray_stepper_top.vhd": good["t1_gray_stepper_top.vhd"].replace('x"47524159"', 'x"47524158"')})
    r = DC.derive(make_design(tmp_path / "bad", bad, spec, top="t1_gray_stepper_top"), tmp_path / "bad")
    assert [f["code"] for f in r["findings"]] == ["CONST-ID-01"]


def test_vhdl_named_literal_is_found(tmp_path: Path) -> None:
    spec = 'The design ID is "GRAY". The identification word 0x47524159 is register 0.\n'
    r = DC.derive(make_design(tmp_path, {"fx_top.vhd": vhdl_top()}, spec), tmp_path)
    assert r["findings"] == []
    r = DC.derive(make_design(tmp_path / "b", {"fx_top.vhd": vhdl_top(id_expr="ID").replace('x"47524159"', 'x"11111111"')},
                              spec.replace("47524159", "12345678")), tmp_path / "b")
    assert "CONST-LIT-01" in [f["code"] for f in r["findings"]]


# ---- R04: xpm_sim -------------------------------------------------------------------------------------------------------
XPM_NO = "  u_x : xpm_cdc_single port map (src_clk => '0', src_in => CPU_RESETN, dest_clk => CLK100MHZ, dest_out => open);\n"
XPM_OK = ("  u_x : xpm_cdc_single generic map (DEST_SYNC_FF => 4, SIM_ASSERT_CHK => 1) port map (src_clk => '0', src_in => CPU_RESETN,\n"
          "    dest_clk => CLK100MHZ, dest_out => open);\n")


@pytest.mark.parametrize("inst,n", [(XPM_NO, 1), (XPM_OK, 0), (XPM_NO.replace(": xpm_cdc_single", ": entity xpm.xpm_cdc_single"), 1),
                                    (XPM_OK.replace("SIM_ASSERT_CHK => 1", "SIM_ASSERT_CHK => 0"), 1),
                                    (XPM_OK.replace(": xpm_cdc_single", ": component xpm_cdc_single"), 0),
                                    ("  -- u_x : xpm_cdc_single port map (a => b);\n", 0),
                                    ("  component xpm_cdc_single is port (a : in std_logic); end component;\n", 0),
                                    (XPM_NO.replace("xpm_cdc_single", "xpm_cdc_async_rst"), 0)])        # async_rst has no SIM_ASSERT_CHK
def test_xpm_sim_reads_vhdl(tmp_path: Path, inst: str, n: int) -> None:
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top(extra=inst)})
    r = C.run_one("xpm_sim", d, "rtl", root=tmp_path)
    assert r["status"] == "pass" and [f["code"] for f in r["findings"]] == ["XPM-SIM-01"] * n, r["findings"]
    if n:
        assert r["findings"][0]["where"].endswith(".vhd:" + r["findings"][0]["where"].rsplit(":", 1)[1])


def test_xpm_sim_with_no_source_is_not_run(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"readme.txt": "x"}, build={"sources": []})
    assert C.run_one("xpm_sim", d, "rtl", root=tmp_path)["status"] == "not_run"


# ---- R01: lint ----------------------------------------------------------------------------------------------------------
@needs_ghdl
def test_vhdl_top_is_linted_by_ghdl(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top()})
    r = C.run_one("lint", d, "rtl", root=tmp_path)
    assert r["status"] == "pass" and r["findings"] == [], r
    latch = "  p_latch : process (CLK100MHZ, CPU_RESETN) begin\n    if CPU_RESETN = '1' then LED2 <= CLK100MHZ; end if;\n  end process;\n"
    top = vhdl_top(extra=latch).replace("signal rst : std_logic;", "signal rst : std_logic;\n  signal LED2 : std_logic;")
    r = C.run_one("lint", make_design(tmp_path / "b", {"fx_top.vhd": top}), "rtl", root=tmp_path / "b")
    assert r["status"] == "fail" and r["findings"][0]["code"] == "GHDL" and "latch" in r["findings"][0]["message"].lower(), r
    assert r["findings"][0]["rule"] == "HDL-LINT-00" and r["findings"][0]["where"].endswith("fx_top.vhd")


def test_systemverilog_top_over_vhdl_entities_is_not_run(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"top.sv": "module top; sub u(); endmodule\n", "sub.vhd": "entity sub is end entity;\n"}, top="top",
                    build={"sources": ["d/rtl/*.sv", "d/rtl/*.vhd"]})
    r = C.run_one("lint", d, "rtl", root=tmp_path)
    assert r["status"] == "not_run" and "no reader" in r["why"] and "sub.vhd" in r["why"], r


def test_lint_is_not_clean_when_verilator_itself_failed(tmp_path: Path, monkeypatch) -> None:
    from flow import lint_ruleset as L
    monkeypatch.setattr(L, "verilator_findings", lambda design: ([], "verilator exited 1: bad VERILATOR_ROOT"))
    d = make_design(tmp_path, {"top.sv": "module top; endmodule\n"}, top="top")
    r = C.run_one("lint", d, "rtl", root=tmp_path)
    assert r["status"] == "not_run" and "exited 1" in r["why"]


# ---- R07: axi_profile ---------------------------------------------------------------------------------------------------
def test_axi_profile_says_it_does_not_read_vhdl_register_logic(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top()})
    (d / "spec.yaml").write_text(yaml.safe_dump({"interfaces": {"axi_lite_profile": "house", "blocks": {}}}))
    r = C.run_one("axi_profile", d, "rtl", root=tmp_path)
    assert r["incomplete"] == ["vhdl_register_logic"] and "no reader for .vhd" in r["parts"]["vhdl_register_logic"], r
    d2 = make_design(tmp_path / "b", {"top.sv": "module top; endmodule\n"}, top="top")
    (d2 / "spec.yaml").write_text(yaml.safe_dump({"interfaces": {"axi_lite_profile": "house", "blocks": {}}}))
    assert C.run_one("axi_profile", d2, "rtl", root=tmp_path / "b")["incomplete"] == []


# ---- R08: fsm coverage --------------------------------------------------------------------------------------------------
def test_fsm_coverage_names_the_unread_vhdl_file(tmp_path: Path) -> None:
    from flow import fsm_coverage as F
    f = tmp_path / "m.vhd"
    f.write_text("architecture r of m is type st_t is (S_A, S_B); begin end;\n")
    with pytest.raises(ValueError, match=r"no reader for \.vhd"):
        F.read_states(f, "st_t")
    g = tmp_path / "m.sv"
    g.write_text("typedef enum logic [1:0] {S_A, S_B = 3} st_t;\n")
    assert F.read_states(g, "st_t") == {"S_A": 0, "S_B": 3}


# ---- R09, R10: CDC ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("body,crosses", [
    ('  signal sy : std_logic_vector(1 downto 0);\n  attribute ASYNC_REG : string;\n  attribute ASYNC_REG of sy : signal is "TRUE";\n', True),
    ("  u_x : xpm_cdc_single port map (a => b);\n", True),
    ("  u_x : entity xpm.xpm_cdc_gray port map (a => b);\n", True),
    ("  u_f : xpm_fifo_async port map (a => b);\n", True),
    ("  -- attribute ASYNC_REG of sy : signal is \"TRUE\";\n  -- u_x : xpm_cdc_single\n", False),
    ("  component xpm_cdc_single is port (a : in std_logic); end component;\n", False),
    ("", False)])
def test_cdc_crossing_detected_in_vhdl(tmp_path: Path, body: str, crosses: bool) -> None:
    from flow import cdc_inject
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "t.vhd").write_text("architecture r of t is\n" + body + "begin\nend architecture;\n")
    assert cdc_inject.design_crosses(d) is crosses


def test_cdc_injection_run_fails_closed_on_a_vhdl_crossing(tmp_path: Path) -> None:
    from flow import cdc_inject_run as R
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "t.vhd").write_text('architecture r of t is\n  attribute ASYNC_REG of sy : signal is "TRUE";\nbegin\nend architecture;\n')
    rep = R.evaluate(d, seeds=1, timeout_s=5)
    assert rep["applicable"] is True and rep["pass"] is False and "no reader for .vhd" in rep["why"], rep
    (d / "rtl" / "u.sv").write_text("module u; endmodule\n")                 # and no crossing in the design: still not applicable, passes
    (d / "rtl" / "t.vhd").write_text("architecture r of t is begin end architecture;\n")
    rep = R.evaluate(d, seeds=1, timeout_s=5)
    assert rep["applicable"] is False and rep["pass"] is True


def test_the_v3_cdc_check_sees_a_vhdl_crossing(tmp_path: Path) -> None:
    from flow import verif_gates as VG
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "t.vhd").write_text('architecture r of t is\n  attribute ASYNC_REG of sy : signal is "TRUE";\nbegin\nend architecture;\n')
    got = VG.cdc_checks(d, None, None)
    assert "cdc_structure_clean" in got and "cdc_injection_clean" in got        # before brief 153 a VHDL crossing returned {}


# ---- R11, R12: the spec-test role ---------------------------------------------------------------------------------------
@needs_ghdl
def test_spectest_simulates_the_ghdl_netlist_of_vhdl(tmp_path: Path) -> None:
    from agent.graph import spectest as ST
    assert "vhdl.own_sources(DESIGN_DIR" in ST.ENTRY_TEMPLATE and 'glob("*.sv")' not in ST.ENTRY_TEMPLATE
    compile(ST.ENTRY_TEMPLATE.split("import spec_bench")[0], "entry", "exec")
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top()})
    own = vhdl.own_sources(d, {})
    assert len(own) == 1 and own[0].suffix == ".v" and "module fx_top" in own[0].read_text()
    (d / "rtl" / "extra.sv").write_text("module extra; endmodule\n")
    own = vhdl.own_sources(d, {})
    assert [p.name for p in own][0] == "extra.sv" and own[-1].suffix == ".v"      # SystemVerilog as it is, the VHDL as its netlist


def test_spectest_sources_of_a_systemverilog_design_are_unchanged(tmp_path: Path) -> None:
    d = make_design(tmp_path, {"b.sv": "module b; endmodule\n", "a.sv": "module a; endmodule\n"}, top="a")
    assert [p.name for p in vhdl.own_sources(d, {})] == ["a.sv", "b.sv"]


def test_spectest_evidence_key_changes_with_a_vhdl_edit(tmp_path: Path) -> None:
    from agent.graph import spectest as ST
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top()})
    h0 = ST.rtl_hash(d)
    (d / "rtl" / "fx_top.vhd").write_text(vhdl_top() + "\n-- edit\n")
    assert ST.rtl_hash(d) != h0
    other = make_design(tmp_path / "o", {"a.sv": "module a; endmodule\n"}, top="a")
    h1 = ST.rtl_hash(other)
    (other / "rtl" / "a.sv").write_text("module a; wire x; endmodule\n")
    assert ST.rtl_hash(other) != h1


# ---- R13: trace matrix --------------------------------------------------------------------------------------------------
def test_trace_v1_lists_vhdl_files_per_legacy_item(tmp_path: Path) -> None:
    from flow import trace_v1 as T
    d = ROOT / "runs" / "t153" / "d"
    shutil.rmtree(d.parent, ignore_errors=True)
    (d / "rtl").mkdir(parents=True)
    try:
        (d / "rtl" / "a.vhd").write_text("entity a is end;\n")
        (d / "rtl" / "b.sv").write_text("module b; endmodule\n")
        items = T.legacy_items(d, {"evidence_record": "x.json", "requirements": [{"id": "R1", "tests": ["t"]}]})
        assert [p.rsplit("/", 1)[1] for p in items[0]["checks"]] == ["a.vhd", "b.sv"]
    finally:
        shutil.rmtree(d.parent, ignore_errors=True)


def test_trace_elements_and_waivers_read_vhdl_comments(tmp_path: Path) -> None:
    from flow import traceability as TR
    f = tmp_path / "t.vhd"
    f.write_text("-- req: R-1\nentity gray_core is end entity;\n-- std-waive: STD-RST-01 async by design owner: me; date: 2026-11-21\n"
                 "entity other is end entity; -- req: R-2\n")
    by_req, _ = TR.rtl_elements([f], tmp_path, {"R-1", "R-2"})
    assert by_req == {"R-1": {"gray_core"}, "R-2": {"other"}}, by_req
    w = TR.inline_waivers([f])
    assert len(w) == 1 and w[0]["rule"] == "STD-RST-01" and w[0]["owner"] == "me" and w[0]["date"] == "2026-11-21"
    g = tmp_path / "t.sv"                                                                   # SystemVerilog is as before
    g.write_text("// req: R-1\nmodule m; endmodule\n// std-waive: STD-RST-01 why owner: x; date: 2026-11-21\n")
    assert TR.rtl_elements([g], tmp_path, {"R-1"})[0] == {"R-1": {"m"}} and len(TR.inline_waivers([g])) == 1


# ---- R14: the build stamp -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("stamp,bad", [('x"00000000"', True), ('X"0000_0000"', True), ("(others => '0')", True), ("BUILD_STAMP", False),
                                       ('x"00000001"', False)])
def test_constant_zero_build_stamp_in_vhdl(tmp_path: Path, stamp: str, bad: bool) -> None:
    from flow import hw_dry_check as H
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top(stamp=stamp)})
    probs = [p for p in H.check_design(d)["problems"] if "BUILD_STAMP" in p]
    assert bool(probs) is bad, probs
    if bad:
        assert probs[0].startswith("rtl/fx_top.vhd:")


def test_constant_zero_build_stamp_in_a_comment_is_ignored(tmp_path: Path) -> None:
    from flow import hw_dry_check as H
    d = make_design(tmp_path, {"fx_top.vhd": vhdl_top(extra="  -- BUILD_STAMP => x\"00000000\"\n")})
    assert not [p for p in H.check_design(d)["problems"] if "BUILD_STAMP" in p]


# ---- R15: managed RTL import --------------------------------------------------------------------------------------------
def _project(tmp: Path, files: dict[str, str]):
    from agent.core import managed as M
    d = make_design(tmp, files)
    comp = M.Component(name="c", ownership="third_party", level="rtl", paths=["rtl/**"], module="fx_top",
                       build_sources=[f"designs/d/rtl/{n}" for n in files], interface={"ports": [{"name": "x"}]})
    return M.Project(name="p", top="fx_top", components=[comp], design=d), comp


def test_managed_import_does_not_drop_a_vhdl_component_silently(tmp_path: Path) -> None:
    from flow import managed_rtl_import as MI
    proj, comp = _project(tmp_path, {"fx_top.vhd": vhdl_top()})
    assert MI.contract_problems(proj, comp)[0].startswith("no reader for .vhd")
    with pytest.raises(ValueError, match="no reader for .vhd"):
        MI.build_files(proj, comp)
    proj, comp = _project(tmp_path / "b", {"top.sv": "module top; endmodule\n"})
    assert [p.name for p in MI.build_files(proj, comp)] == ["top.sv"]


# ---- R16, R17: review and inspect ---------------------------------------------------------------------------------------
def test_review_finds_the_top_of_vhdl_rtl(tmp_path: Path) -> None:
    from flow.review import prepare as P
    f1, f2 = tmp_path / "top.vhd", tmp_path / "leaf.vhd"
    f1.write_text("entity top is end entity;\narchitecture r of top is begin\n  u : entity work.leaf port map (a => b);\nend architecture;\n")
    f2.write_text("entity leaf is end entity;\n")
    assert P.infer_top([f1, f2]) == "top"
    f2.write_text("entity leaf is end entity;\n")
    f1.write_text("entity top is end entity;\n")
    assert P.infer_top([f1, f2]) is None                                                # two roots: no unique answer, no guess
    g = tmp_path / "m.sv"
    g.write_text("module m; endmodule\n")
    assert P.infer_top([g]) == "m"


def test_review_prepare_lists_vhdl_in_the_generated_build_yaml(tmp_path: Path) -> None:
    from flow.review import prepare as P
    d = tmp_path / "usr"
    d.mkdir()
    (d / "top.vhd").write_text("entity top is end entity;\n")
    r = P.prepare(d, name="t153")
    try:
        cfg = yaml.safe_load((r["src"] / "build.yaml").read_text())
        assert r["top"] == "top" and any(s.endswith("/*.vhd") for s in cfg["sources"]), cfg
    finally:
        shutil.rmtree(r["work"], ignore_errors=True)


def test_inspect_schematic_sources_name_the_unread_vhdl() -> None:
    from flow import inspect_views as IV
    files, note = IV.schematic_sources([Path("a.sv"), Path("b.vhd")])
    assert files == [Path("a.sv")] and note.startswith("no reader for .vhd (1 file(s): b.vhd)")
    assert IV.schematic_sources([Path("a.sv"), Path("h.svh")]) == ([Path("a.sv")], None)


# ---- the whole labelled set ---------------------------------------------------------------------------------------------
def _tools_present() -> bool:
    return bool(HAVE_GHDL and shutil.which("yosys") or (Path.home() / ".local/opt/oss-cad-suite/bin/yosys").is_file()) and bool(
        shutil.which("verilator") or (Path.home() / ".local/opt/oss-cad-suite/bin/verilator").is_file()) and bool(shutil.which("iverilog"))


@pytest.mark.skipif(not _tools_present(), reason="needs GHDL, Yosys (OSS CAD Suite), Verilator and Icarus")
def test_no_reader_of_the_labelled_set_is_silent_on_vhdl() -> None:
    """The measurement of results/153_vhdl_parity: every reader is `caught` or `no_reader` on the VHDL design, and the SystemVerilog
    controls still catch their plants (a port changed no SystemVerilog result)."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import vhdl_parity_probe as P
    rep = P.run_readers()
    bad = [(r["id"], r["vhdl"]) for r in rep["readers"] if r["vhdl"]["outcome"] not in ("caught", "no_reader")]
    assert not bad, bad
    assert [r["id"] for r in rep["readers"] if r["sv"]["outcome"] not in ("caught", "control")] == []
    assert rep["vhdl_summary"]["silent"] == 0 and rep["vhdl_summary"]["wrong"] == 0


def test_the_pre_registration_names_every_reader() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import vhdl_parity_probe as P
    assert len(P.READERS) == 17 and len({r["id"] for r in P.READERS}) == 17
    assert re.search(r"17 readers", (ROOT / "results" / "153_vhdl_parity" / "prereg.md").read_text())


# ---- the agent's own RTL lists --------------------------------------------------------------------------------------------
def test_stage_2_plan_sees_a_vhdl_design_as_having_rtl(tmp_path: Path) -> None:
    """Before brief 153 the plan looked for rtl/*.sv, so a VHDL design's RTL never "existed": every stage-2 visit rewrote it from scratch
    instead of repairing it."""
    import types
    from agent.graph import run as gr
    d = tmp_path / "d"
    for sub in ("tests", "rtl"):
        (d / sub).mkdir(parents=True)
    (d / "model.py").write_text("class Model: pass\n")
    (d / "tests" / "test_x_rtl.py").write_text("# t\n")
    (d / "rtl" / "top.vhd").write_text("entity top is end entity;\n")
    rt = types.SimpleNamespace(design=d)
    assert gr.stage2_plan(rt, {"owners": {"rtl": ["fails"]}}) == {"rtl": ["fails"]}                 # repaired, not rewritten
    (d / "rtl" / "top.vhd").unlink()
    assert gr.stage2_plan(rt, {"owners": {"rtl": ["fails"]}}) == {"rtl": None}                      # nothing there: write it


def test_closure_snapshot_covers_vhdl(tmp_path: Path) -> None:
    from agent.graph import closure as cl
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "a.vhd").write_text("entity a is end entity;\n")
    (tmp_path / "rtl" / "b.sv").write_text("module b; endmodule\n")
    ws = cl.Workspace(tmp_path)
    snap = ws.read()
    assert sorted(snap) == ["rtl/a.vhd", "rtl/b.sv"]
    (tmp_path / "rtl" / "a.vhd").write_text("entity broken is\n")
    (tmp_path / "rtl" / "c.vhd").write_text("entity c is end entity;\n")
    ws.restore(snap)
    assert (tmp_path / "rtl" / "a.vhd").read_text() == "entity a is end entity;\n" and not (tmp_path / "rtl" / "c.vhd").exists()


def test_flow_scripts_still_work_with_only_flow_on_the_path(tmp_path: Path) -> None:
    """``python flow/verif_gates.py`` imports ``cdc_inject`` as a top-level module, with no repo root on sys.path: the new
    ``flow.sources`` import must fall back to the sibling module (the first version of brief 153 broke this)."""
    import subprocess
    import sys
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "t.vhd").write_text('architecture r of t is\n  attribute ASYNC_REG of sy : signal is "TRUE";\nbegin\nend architecture;\n')
    code = ("import sys; sys.path[:] = [p for p in sys.path if p not in ('', %r)] ; sys.path.insert(0, %r)\n"
            "import cdc_inject, trace_v1, hw_dry_check, fsm_coverage, constraint_gates, traceability\n"
            "from pathlib import Path\n"
            "assert cdc_inject.design_crosses(Path(%r))\n"
            "assert hw_dry_check.check_design(Path(%r))['problems']\n"
            "assert constraint_gates.xpm_sim_findings_vhdl('u : xpm_cdc_single port map (a => b);')\n"
            "try:\n    fsm_coverage.read_states(Path('x.vhd'), 'st')\nexcept ValueError as e:\n    assert 'no reader' in str(e)\n"
            "print('ok')\n") % (str(ROOT), str(ROOT / "flow"), str(d), str(d))
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr[-800:]
