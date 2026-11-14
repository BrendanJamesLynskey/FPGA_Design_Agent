"""Brief 71B: the reset check's source part is elaboration (Yosys + slang for SystemVerilog, the ghdl plugin for VHDL), not a text
scanner. The regression sets are the 23 designs of review round 2 (flow/tests/data/b71_resets) and the 212 of review round 3
(flow/tests/data/b71b_cases, expectations in expected.yaml): each has an expected outcome, and a design that cannot be read is
PARTIAL, never a pass. The tests skip, with a reason, where the OSS CAD Suite is not installed; CI installs the pinned release
(OSS CAD Suite 20261112) in the ``reset-elab`` job. Locally: ``FDA_OSS_CAD=<suite dir> python -m pytest flow/tests/test_71b_reset_elab.py``."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from flow import checks as C
from flow.checks import elab
from flow.checks import resets as R

DATA = Path(__file__).parent / "data"
TOOL = elab.find_tool()
needs_tool = pytest.mark.skipif(TOOL is None, reason="yosys (OSS CAD Suite 20261112) not installed: set FDA_OSS_CAD or install it "
                                                      "under ~/.local/opt/oss-cad-suite; the reset-elab CI job runs these")

#: review round 2's 23 designs: the rules the source part raises, or "partial" (the front end rejects the design)
ROUND2 = {
    "d_base": {"HDL-RST-01"}, "d_gen": {"HDL-RST-01"}, "d_glob": {"HDL-RST-01"}, "d_iface": {"HDL-RST-01"},
    "d_iffp": {"HDL-RST-01"},                 # `iff` in the sensitivity list: elaborated, no longer unread
    "d_incl": {"HDL-RST-01"}, "d_latch": {"HDL-RST-01"},
    "d_macro": {"HDL-RST-01"},                # a macro in the sensitivity list: preprocessed, no longer unread
    "d_macromod": {"HDL-RST-01"},
    "d_multi": "partial", "d_multi2": "partial",   # two asynchronous resets in one block: the front end rejects it
    "d_name_declared": {"HDL-RST-01"},        # the declared input is a top port; here the reset is a&b computed in the top
    "d_pol_alias": set(),                     # rst_p = ~rst_n: both blocks reset on rst_n low, one polarity (correct pass)
    "d_pol_eq0": {"HDL-RST-02"}, "d_pol_eqeq": {"HDL-RST-02"}, "d_pol_name": {"HDL-RST-02"}, "d_pol_plain": {"HDL-RST-02"},
    "d_pol_second": {"HDL-RST-02"}, "d_pol_struct": {"HDL-RST-02"}, "d_prim": {"HDL-RST-01"},
    "d_reset_sync": {"HDL-RST-01"}, "d_vhdl_mixed": {"HDL-RST-01"}, "d_xpmname": {"HDL-RST-01"},
}


def _copy(src: Path, tmp: Path) -> Path:
    d = tmp / src.name
    shutil.copytree(src, d, symlinks=True)
    if src.name == "dir_as_sv":                    # a directory named x.sv (git keeps it with a placeholder file inside)
        for f in (d / "rtl" / "x.sv").glob("*"):
            f.unlink()
    return d


def _outcome(d: Path) -> tuple[str, set[str], dict]:
    r = C.run_one("resets", d, "rtl", root=d)
    rules = {f["rule"] for f in r.get("findings", []) if f.get("blocking")}
    src = r.get("parts", {}).get("source", "not run: " + str(r.get("why", "")))
    if r.get("status") == "not_run" or src != "ran":
        return "partial", rules, r
    return ("clean" if not rules else "bad"), rules, r


@needs_tool
@pytest.mark.parametrize("name", sorted(ROUND2))
def test_review_round_2_regressions(name: str, tmp_path: Path) -> None:
    kind, rules, r = _outcome(_copy(DATA / "b71_resets" / name, tmp_path))
    want = ROUND2[name]
    if want == "partial":
        assert kind == "partial" and "source" in r["incomplete"] and r["status"] != "pass", r
    else:
        assert kind != "partial", r["parts"]
        assert rules == want, (name, r["findings"])
    assert r["status"] != "pass" or r.get("incomplete"), "at scope rtl the netlist parts are never run: never a full pass"


EXPECTED = yaml.safe_load((DATA / "b71b_cases" / "expected.yaml").read_text())


def test_every_third_round_case_has_an_expectation() -> None:
    dirs = {p.name for p in (DATA / "b71b_cases").iterdir() if p.is_dir()}
    assert dirs == set(EXPECTED) and len(dirs) == 212


@needs_tool
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_review_round_3_regressions(name: str, tmp_path: Path) -> None:
    kind, rules, r = _outcome(_copy(DATA / "b71b_cases" / name, tmp_path))
    want = EXPECTED[name]
    if want == "partial":
        assert kind == "partial", (name, r["findings"], r["parts"])
        assert r["status"] != "pass" or r.get("incomplete"), "a partial source part must not read as a clean pass"
    elif want == "clean":
        assert kind == "clean", (name, r["findings"], r["parts"])
    else:
        assert kind == "bad" and rules == set(str(want).split(",")), (name, rules, r["parts"])


@needs_tool
def test_the_pinned_tool_is_installed() -> None:
    v = elab.version()
    assert v.startswith(elab.PIN_YOSYS), f"expected {elab.PIN_YOSYS} (OSS CAD Suite {elab.PIN_SUITE}), found {v!r}"


# ---- fail closed --------------------------------------------------------------------------------------------------------
def _design(tmp: Path, files: dict[str, str], build: str = "top: x\nsources: [rtl/*.sv]\n") -> Path:
    d = tmp / "d"
    for fn, t in files.items():
        p = d / fn
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t)
    (d / "build.yaml").write_text(build)
    return d


ASYNC = "module x(input clk, input rst_n, input d, output logic q);\nalways_ff @(posedge clk or negedge rst_n) if (!rst_n) q<=0; else q<=d;\nendmodule\n"


def test_missing_tool_is_partial_never_a_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(elab, "find_tool", lambda: None)
    d = _design(tmp_path, {"rtl/x.sv": "module x(input clk, input d, output logic q);\nalways_ff @(posedge clk) q<=d;\nendmodule\n"})
    r = C.run_one("resets", d, "rtl", root=d)
    assert r["parts"]["source"].startswith("not run: yosys") and "source" in r["incomplete"]
    assert r["status"] != "fail" and r["incomplete"], "the source part could not run: PARTIAL or not run, never a clean pass"
    assert not C.run(d, ["resets"], "rtl")["pass"]


def test_unmatched_source_entry_is_partial(tmp_path: Path) -> None:
    d = _design(tmp_path, {"rtl/x.sv": ASYNC}, build="top: x\nsources: [rtl/x.sv, rtl/missing.sv]\n")
    r = C.run_one("resets", d, "rtl", root=d)
    assert r["parts"]["source"].startswith("not run: no file matches") and "source" in r["incomplete"]


def test_file_of_another_kind_is_partial(tmp_path: Path) -> None:
    d = _design(tmp_path, {"rtl/x.sv": ASYNC, "rtl/p.svp": "protected\n"}, build="top: x\nsources: [rtl/x.sv, rtl/p.svp]\n")
    r = C.run_one("resets", d, "rtl", root=d)
    assert "svp" in r["parts"]["source"] and "source" in r["incomplete"]


@needs_tool
def test_elaboration_error_is_partial_with_the_tools_message(tmp_path: Path) -> None:
    d = _design(tmp_path, {"rtl/x.sv": "module x(input clk, output q);\nassign q = undeclared_signal;\nendmodule\n"})
    r = C.run_one("resets", d, "rtl", root=d)
    assert "undeclared_signal" in r["parts"]["source"] and "source" in r["incomplete"]


@needs_tool
def test_other_hdl_extensions_are_read_not_dropped(tmp_path: Path) -> None:
    for ext in (".v", ".SV", ".vlg", ".sverilog"):
        d = _design(tmp_path / ext.strip("."), {f"rtl/x{ext}": ASYNC}, build=f"top: x\nsources: [rtl/x{ext}]\n")
        r = C.run_one("resets", d, "rtl", root=d)
        assert {f["rule"] for f in r["findings"] if f["blocking"]} == {"HDL-RST-01"}, ext


@needs_tool
def test_an_async_flop_in_a_vhdl_entity_is_found(tmp_path: Path) -> None:
    vhd = ("library ieee; use ieee.std_logic_1164.all;\nentity x is port(clk, rst_n, d : in std_logic; q : out std_logic); end entity;\n"
           "architecture a of x is begin process(clk, rst_n) begin\n if rst_n = '0' then q <= '0'; elsif rising_edge(clk) then "
           "q <= d; end if; end process; end architecture;\n")
    d = _design(tmp_path, {"rtl/x.vhd": vhd}, build="top: x\nsources: [rtl/x.vhd]\n")
    r = C.run_one("resets", d, "rtl", root=d)
    assert r["parts"]["source"] == "ran" and {f["rule"] for f in r["findings"] if f["blocking"]} == {"HDL-RST-01"}


@needs_tool
def test_declared_input_exempts_only_the_nets_it_drives(tmp_path: Path) -> None:
    arch = "reset:\n  async_inputs: [rst_n]\n"
    d = _design(tmp_path, {"rtl/x.sv": ASYNC, "architecture.yaml": arch})
    assert not [f for f in C.run_one("resets", d, "rtl", root=d)["findings"] if f["blocking"]]
    d2 = _design(tmp_path / "b", {"rtl/x.sv": ASYNC.replace("negedge rst_n) if (!rst_n)", "negedge a) if (!a)").replace(
        "input d,", "input d, input a,"), "architecture.yaml": arch})
    assert {f["rule"] for f in C.run_one("resets", d2, "rtl", root=d2)["findings"] if f["blocking"]} == {"HDL-RST-01"}


# ---- the sign-off netlist gate attacked with real builds (Vivado 2026.1 records, results/71b_netlist_scans) -----------------
SCANS = Path(__file__).resolve().parents[2] / "results" / "71b_netlist_scans"
#: each attack design (flow/checks/seeded/adv) and the reset rules the netlist part plus AMD's rows must raise ({} = clean)
NETLIST = {
    **{c: {"HDL-RST-01"} for c in (
        "adv_a01_async_plain", "adv_a02_prim_fdce", "adv_a03_prim_fdpe_inv_clk", "adv_a04_prim_fdcpe", "adv_a05_prim_ldce",
        "adv_a06_latch_with_reset", "adv_a07_macro_flop", "adv_a08_async_set", "adv_a10_instance_named_reset_sync",
        "adv_a11_user_module_named_reset_sync", "adv_a12_array", "adv_a13_dont_touch", "adv_a14_gated_buf",
        "adv_e01_iddr_async", "adv_e02_oddr_async", "adv_e03_srl_style_shift_async")},
    "adv_b01_polarity": {"HDL-RST-02"}, "adv_b02_polarity_via_inverter": {"HDL-RST-02"},
    "adv_c01_lut_drives_async": {"HDL-RST-01", "HDL-RST-05"}, "adv_c02_cdc_sync_reset": {"HDL-RST-04"},
    "adv_c03_cdc_async_reg": {"HDL-RST-01", "HDL-RST-04"},
    "adv_d01_dsp_async": {"HDL-RST-01", "HDL-RST-03"}, "adv_d02_bram_async": {"HDL-RST-01", "HDL-RST-03"},
    "adv_z01_clean_sync": set(), "adv_z02_clean_shell_sync": set(), "adv_z03_clean_two_domains": set(),
}


@pytest.mark.parametrize("case", sorted(NETLIST))
def test_netlist_gate_attack_designs(case: str) -> None:
    from flow import lint_ruleset as LR
    d = SCANS / case
    assert (d / "reset_scan.tsv").is_file() and not (d / "synth_failed.txt").exists(), f"{case}: no scan"
    cfg = {"synchronisers": set(R.RECOGNISED), "async_inputs": set()}
    fs = R.netlist_findings(R.read_scan(d / "reset_scan.tsv"), cfg)
    fs += [f for f in R.amd_findings(C._parse_rules(d / "methodology.rpt"), C._parse_rules(d / "drc.rpt"),
                                     C._parse_cdc(d / "cdc.rpt"), "post_synth") if f["severity"].lower() not in ("advisory", "info")]
    rs = LR.load_rules()
    got = {f.get("rule") or LR.rule_for(rs, f["tool"], f["code"]) for f in fs if not f.get("incomplete")}
    assert got == NETLIST[case], (case, got)


# ---- the independent re-review's defeats (brief 71B), each now caught or PARTIAL ------------------------------------------
def _src_only(tmp: Path, files: dict[str, str]) -> tuple[str, set[str]]:
    pats = ", ".join(f"rtl/*.{e}" for e in ("sv", "vhd") if any(f.endswith("." + e) for f in files))
    d = _design(tmp, files, build=f"top: x\nsources: [{pats}]\n")
    r = C.run_one("resets", d, "rtl", root=d)
    return ("ran" if r["parts"].get("source") == "ran" else "partial"), {f["rule"] for f in r["findings"] if f["blocking"]}


SUB = "module sub(input clk, rst, d, output logic q); always_ff @(posedge clk or posedge rst) if (rst) q<=0; else q<=d; endmodule\n"
TOPX = "module x(input clk, rst, d, output q); sub u(.clk(clk), .rst(rst), .d(d), .q(q)); endmodule\n"
REVIEW = {
    "blackbox_attribute_hides_body": ({"rtl/x.sv": "(* blackbox *) " + SUB + TOPX}, "partial"),
    "missing_module_is_not_stubbed_silently": ({"rtl/x.sv": TOPX}, "partial"),
    "latch_with_unnamed_reset": ({"rtl/x.sv": "module x(input clk, por, en, d, output logic q); always_latch if (por) q = 1'b0; else if (en) q = d; endmodule\n"}, {"HDL-RST-01"}),
    "ldcpe_primitive": ({"rtl/x.sv": "module x(input g, clr, pre, d, output q); LDCPE u(.G(g), .GE(1'b1), .CLR(clr), .PRE(pre), .D(d), .Q(q)); endmodule\n"}, {"HDL-RST-01"}),
    "fdcp_primitive": ({"rtl/x.sv": "module x(input clk, clr, pre, d, output q); FDCP u(.C(clk), .CLR(clr), .PRE(pre), .D(d), .Q(q)); endmodule\n"}, {"HDL-RST-01"}),
    "iddr_async": ({"rtl/x.sv": "module x(input clk, rst, d, output q1, q2); IDDR #(.SRTYPE(\"ASYNC\")) u(.C(clk), .CE(1'b1), .D(d), .R(rst), .S(1'b0), .Q1(q1), .Q2(q2)); endmodule\n"}, {"HDL-RST-01"}),
    "oddre1_sr": ({"rtl/x.sv": "module x(input clk, rst, d, output q); ODDRE1 u(.C(clk), .D1(d), .D2(d), .SR(rst), .Q(q)); endmodule\n"}, {"HDL-RST-01"}),
    "vhdl_entity_mid_line": ({"rtl/x.sv": "module x(input clk, rst, d, output q); ent u(.clk(clk), .rst(rst), .d(d), .q(q)); endmodule\n",
        "rtl/a.vhd": "library ieee; use ieee.std_logic_1164.all; entity ent is port(clk, rst, d : in std_logic; q : out std_logic); end entity;\n"
        "architecture a of ent is begin process(clk, rst) begin if rst = '1' then q <= '0'; elsif rising_edge(clk) then q <= d; end if; end process; end architecture;\n"}, {"HDL-RST-01"}),
    "vhdl_two_architectures": ({"rtl/x.vhd": "library ieee; use ieee.std_logic_1164.all;\nentity x is port(clk, rst, d : in std_logic; q : out std_logic); end entity;\n"
        "architecture sync of x is begin process(clk) begin if rising_edge(clk) then q <= d; end if; end process; end architecture;\n"
        "architecture asyn of x is begin process(clk, rst) begin if rst = '1' then q <= '0'; elsif rising_edge(clk) then q <= d; end if; end process; end architecture;\n"}, "partial"),
}


@needs_tool
@pytest.mark.parametrize("name", sorted(REVIEW))
def test_review_defeats_are_closed(name: str, tmp_path: Path) -> None:
    files, want = REVIEW[name]
    kind, rules = _src_only(tmp_path, files)
    if want == "partial":
        assert kind == "partial", (name, rules)
    else:
        assert kind == "ran" and rules == want, (name, kind, rules)
