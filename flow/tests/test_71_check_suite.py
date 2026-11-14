"""Brief 71: the check suite (flow/checks) - registry against the rule set, the reset check on its seeded faults (the
committed Vivado 2026.1 records), the source part, the digest, the gates' use of the registry and the agent tool."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from flow import checks as C
from flow import lint_ruleset as LR
from flow.checks import resets as R

from flow.checks import elab as _elab

needs_elab = pytest.mark.skipif(_elab.find_tool() is None, reason="yosys (OSS CAD Suite 20261112) not installed; the reset-elab CI job runs these")
ROOT = Path(__file__).resolve().parents[2]
SEEDED = ROOT / "results" / "71_check_suite" / "seeded"
KB = ROOT.parent / "FPGA_Design_Agent_Knowledge"


# ---- the registry against flow/hdl_rules.yaml --------------------------------------------------------------------------
def test_every_code_a_check_can_raise_maps_to_a_rule() -> None:
    rs = LR.load_rules()
    bad = [f"{n}: {tool}:{code}" for n, c in C.CHECKS.items() for tool, codes in c.codes.items() for code in codes
           if LR.rule_for(rs, tool, code) == "HDL-UNMAPPED"]
    assert not bad, f"codes with no rule in hdl_rules.yaml: {bad}"


def test_every_rule_is_covered_by_a_check_or_marked_manual() -> None:
    rs = LR.load_rules()
    covered: set[str] = set()
    for c in C.CHECKS.values():
        for tool, codes in c.codes.items():
            for code in codes:
                if code == "*":           # a pass-through check: every rule that names this tool
                    covered |= {r["id"] for r in rs["rules"] if (r.get("checks") or {}).get(tool)}
                else:
                    covered.add(LR.rule_for(rs, tool, code))
    for tool, codes in C.MONITORS.items():
        covered |= {LR.rule_for(rs, tool, code) for code in codes}
    missing = [r["id"] for r in rs["rules"] if r["id"] not in covered and not r.get("manual")]
    assert not missing, f"rules no check covers (add a check or mark manual: true): {missing}"


def test_rule_set_shape_fix_and_skill() -> None:
    rs = LR.load_rules()
    assert not LR.rule_problems(rs)
    assert rs["version"] == "1.3"
    for r in rs["rules"]:
        assert str(r.get("fix") or "").strip(), f"{r['id']}: no fix"
        sk = str(r.get("skill") or "")
        assert sk, f"{r['id']}: no skill"
        if "/" in sk:
            assert (ROOT / sk).is_file(), f"{r['id']}: {sk} does not exist"
        elif KB.is_dir():                          # the private bank is not in CI
            assert any(KB.rglob(f"{sk}/SKILL.md")), f"{r['id']}: no KB skill {sk}"


def test_reset_codes_map_to_their_rules() -> None:
    rs = LR.load_rules()
    want = {("resets", "RST-ASYNC-01"): "HDL-RST-01", ("resets", "RST-POL-01"): "HDL-RST-02",
            ("resets", "RST-DSPRAM-01"): "HDL-RST-03", ("resets", "RST-CDC-01"): "HDL-RST-04",
            ("resets", "RST-LUT-01"): "HDL-RST-05", ("vivado", "LUTAR-1"): "HDL-RST-05", ("vivado", "DPIR-1"): "HDL-RST-03",
            ("vivado", "CDC-7"): "HDL-RST-04", ("vivado", "CDC-1"): "HDL-CDC-01", ("vivado", "ROAS-1"): "HDL-RST-01"}
    assert {k: LR.rule_for(rs, *k) for k in want} == want
    assert all(R.CODE_RULE[c] == LR.rule_for(rs, "resets", c) for c in R.CODE_RULE)


def test_amd_reset_ids_exist_in_vivado_2026_1() -> None:
    """The AMD rule ids the reset check reads are in the 2026.1 catalogue (get_methodology_checks / get_drc_checks), or are
    report_cdc rows the seeded designs produced (report_cdc has no catalogue command)."""
    cat = (ROOT / "results" / "71_check_suite" / "rule_catalogue_2026_1.tsv").read_text().splitlines()
    have = {(ln.split("\t")[0], ln.split("\t")[1]) for ln in cat if ln.count("\t") >= 3}
    for rid in R.AMD_METHODOLOGY:
        assert ("methodology", rid) in have, rid
    for rid in R.AMD_DRC:
        assert ("drc", rid) in have, rid
    seen_cdc = {r["rule"] for d in SEEDED.iterdir() if (d / "cdc.rpt").is_file()
                for r in C._parse_cdc(d / "cdc.rpt")["rules"]}
    assert "CDC-7" in seen_cdc


# ---- the reset check on the seeded faults (Vivado 2026.1 records) ------------------------------------------------------
#: each seeded design and the reset rules it must raise (the clean design: none); a design whose synthesis failed is not
#: "caught" (it has no scan)
EXPECT = {"rst_clean": set(), "rst_f1_async": {"HDL-RST-01"}, "rst_f2_polarity": {"HDL-RST-02"},
          "rst_f3_dsp_async": {"HDL-RST-01", "HDL-RST-03"}, "rst_f3b_bram_async": {"HDL-RST-01", "HDL-RST-03"},
          "rst_f4_cdc_sync": {"HDL-RST-04"}, "rst_f4b_cdc_async": {"HDL-RST-01", "HDL-RST-04"},
          "rst_f5_lut_async": {"HDL-RST-05"}}


def _seeded_rules(case: str) -> set[str]:
    d = SEEDED / case
    assert (d / "reset_scan.tsv").is_file() and not (d / "synth_failed.txt").exists(), f"{case}: no scan (did not compile)"
    assert not (d / "reset_scan.not_run.txt").exists()
    cfg = {"synchronisers": set(R.RECOGNISED), "async_inputs": set()}
    fs = R.netlist_findings(R.read_scan(d / "reset_scan.tsv"), cfg)
    fs += [f for f in R.amd_findings(C._parse_rules(d / "methodology.rpt"), C._parse_rules(d / "drc.rpt"),
                                     C._parse_cdc(d / "cdc.rpt"), "post_synth")
           if f["severity"].lower() not in ("advisory", "info")]
    rs = LR.load_rules()
    return {f.get("rule") or LR.rule_for(rs, f["tool"], f["code"]) for f in fs}


@pytest.mark.parametrize("case", sorted(EXPECT))
def test_seeded_reset_faults(case: str) -> None:
    got = _seeded_rules(case)
    assert got == EXPECT[case], f"{case}: raised {sorted(got)}, expected {sorted(EXPECT[case])}"


def test_declared_external_async_input_is_allowed() -> None:
    """F4b's asynchronous reset comes from a register, so declaring a port changes nothing; a register reset straight from a
    declared external asynchronous input passes rule 1, and the same input undeclared fails it."""
    row = {"cell": "q_reg", "ref": "FDCE", "pin": "CLR", "pin_inverted": "0", "clock": "clk", "hier": "", "root_kind": "port",
           "root": "ext_rst", "root_ref": "", "root_inverted": "0", "path": "IBUF", "root_clock": "", "root_async_reg": "",
           "root_hier": "", "d_ref": "LUT2", "q_refs": "LUT3"}
    base = {"synchronisers": set(R.RECOGNISED)}
    assert {f["code"] for f in R.netlist_findings([row], {**base, "async_inputs": set()})} == {"RST-ASYNC-01"}
    assert R.netlist_findings([row], {**base, "async_inputs": {"ext_rst"}}) == []


def test_vendor_ip_cells_are_left_out_but_a_lut_outside_is_not() -> None:
    row = {"cell": "u_gt/x_reg", "ref": "FDCE", "pin": "CLR", "pin_inverted": "0", "clock": "c",
           "hier": "gth_wiz_gtwizard_top/gth_wiz", "root_kind": "cell", "root": "u_or", "root_ref": "LUT2", "root_inverted": "0",
           "path": "", "root_clock": "", "root_async_reg": "", "root_hier": "", "d_ref": "", "q_refs": ""}
    cfg = {"synchronisers": set(R.RECOGNISED), "async_inputs": set()}
    assert {f["code"] for f in R.netlist_findings([row], cfg, {"gth_wiz"})} == {"RST-LUT-01"}
    assert R.netlist_findings([{**row, "root_hier": "gth_wiz"}], cfg, {"gth_wiz"}) == []


@pytest.mark.parametrize("hier", ["vio_x", "violation_ctl", "ila_ne", "xpm_mine", "my_wiz", "axi_dma_v7_1"])
def test_a_user_module_is_never_vendor_by_its_name(hier: str) -> None:
    """Review fix: only the build's IP cores and the named XPM macros are vendor hierarchy."""
    row = {"cell": "q_reg", "ref": "FDCE", "pin": "CLR", "pin_inverted": "0", "clock": "c", "hier": hier, "root_kind": "cell",
           "root": "r_reg", "root_ref": "FDRE", "root_inverted": "0", "path": "", "root_clock": "c", "root_async_reg": "",
           "root_hier": "", "d_ref": "", "q_refs": ""}
    assert "RST-ASYNC-01" in {f["code"] for f in R.netlist_findings([row], {"synchronisers": set(R.RECOGNISED), "async_inputs": set()})}


def test_latches_and_unknown_clocks() -> None:
    cfg = {"synchronisers": set(R.RECOGNISED), "async_inputs": set()}
    latch = {"cell": "l_reg", "ref": "LDCE", "pin": "CLR", "pin_inverted": "0", "clock": "", "hier": "", "root_kind": "port",
             "root": "rst", "root_ref": "", "root_inverted": "0", "path": "IBUF", "root_clock": "", "root_async_reg": "",
             "root_hier": "", "d_ref": "", "q_refs": ""}
    assert {f["code"] for f in R.netlist_findings([latch], cfg)} == {"RST-ASYNC-01"}
    noclk = {**latch, "ref": "FDRE", "pin": "R", "root_kind": "cell", "root": "r_reg", "root_ref": "FDRE", "root_clock": "",
             "clock": "c", "path": ""}
    fs = R.netlist_findings([noclk], cfg)
    assert [f.get("incomplete") for f in fs] == [True]


# ---- the source part ------------------------------------------------------------------------------------------------
SRC = """
module m (input logic clk, input logic rst, input logic rst_n, input logic d, output logic q, output logic r, output logic s);
    always_ff @(posedge clk or posedge rst) begin
        if (rst) q <= 1'b0;
        else     q <= d;
    end
    always_ff @(posedge clk) begin
        if (rst) r <= 1'b0;
        else     r <= d;
    end
    always_ff @(posedge clk) begin
        if (!rst) s <= 1'b0;
        else      s <= d;
    end
endmodule
module reset_sync (input logic clk, input logic rst_n_async, output logic rst);
    logic [1:0] q;
    always_ff @(posedge clk or negedge rst_n_async) if (!rst_n_async) q <= 2'b11; else q <= {q[0], 1'b0};
    assign rst = q[1];
endmodule
"""


@needs_elab
def test_source_part(tmp_path: Path) -> None:
    f = tmp_path / "m.sv"
    f.write_text(SRC)
    fs = R.source_findings(tmp_path, [f], {"synchronisers": set(R.RECOGNISED), "async_inputs": set()})
    codes = sorted((x["code"], x["line"]) for x in fs)
    # line 16: a user file that defines reset_sync (a recognised synchroniser name) is reported (review fix)
    # line 18: its asynchronous edge too, since an impostor is not exempt (review round 2)
    assert codes == [("RST-ASYNC-01", 3), ("RST-ASYNC-01", 16), ("RST-ASYNC-01", 18), ("RST-POL-02", 11)], codes


def test_source_two_asynchronous_resets_in_one_block_is_rejected_not_passed(tmp_path: Path) -> None:
    """A block with two asynchronous resets is not synthesisable as one flip-flop: the front end rejects it, so the source part
    is PARTIAL with the tool's message (it used to be reported by the text scanner). Brief 71B."""
    from flow.checks import elab
    if elab.find_tool() is None:
        pytest.skip("yosys (OSS CAD Suite) not installed")
    f = tmp_path / "m.sv"
    f.write_text("module m (input logic clk, input logic ext_rst_n, input logic soft_rst_n, input logic d, output logic q);\n"
                 "    always_ff @(posedge clk or negedge ext_rst_n or negedge soft_rst_n) begin\n"
                 "        if (!ext_rst_n) q <= 1'b0;\n        else q <= d;\n    end\nendmodule\n")
    parts: dict[str, str] = {}
    R.source_findings(tmp_path, [f], {"synchronisers": set(R.RECOGNISED), "async_inputs": {"ext_rst_n"}}, top="m", parts=parts)
    assert parts["source"].startswith("not run: ")


# ---- the runner and the digest -------------------------------------------------------------------------------------------
def _mini(tmp_path: Path, case: str = "rst_f1_async") -> Path:
    d = tmp_path / "designs" / "mini"
    b = d / "build" / "base"
    b.mkdir(parents=True)
    for n, to in (("methodology.rpt", "methodology_synth.rpt"), ("drc.rpt", "drc_synth.rpt"), ("cdc.rpt", "cdc_synth.rpt"),
                  ("reset_scan.tsv", "reset_scan_synth.tsv"), ("control_sets.rpt", "control_sets_synth.rpt"),
                  ("utilization.rpt", "utilization_synth.rpt")):
        shutil.copy(SEEDED / case / n, b / to)
    (b / "timing_summary_synth.rpt").write_text("")
    (d / "rtl").mkdir()
    (d / "rtl" / "m.sv").write_text("module m (input logic clk, input logic rst, input logic d, output logic q);\n"
                                    "    always_ff @(posedge clk) begin\n        if (rst) q <= 1'b0;\n        else q <= d;\n"
                                    "    end\nendmodule\n")
    return d


def test_runner_digest_and_full_report(tmp_path: Path) -> None:
    d = _mini(tmp_path)
    rep = C.run(d, ["resets", "methodology", "drc", "cdc", "control_sets"], "synth", "standard")
    st = {c["check"]: c["status"] for c in rep["checks"]}
    assert st["resets"] == "fail" and st["control_sets"] == "pass"
    assert "HDL-RST-01 RST-ASYNC-01" in rep["digest"] and "fix:" in rep["digest"] and "skill: reset-strategy" in rep["digest"]
    full = json.loads((d / "build" / "checks" / "base" / "synth.json").read_text())
    assert full["checks"][0]["findings"] and rep["report_path"] == "build/checks/base/synth.json"
    assert len(C.digest(rep, "summary")) < len(rep["digest"])


def test_a_part_that_did_not_run_is_never_a_full_pass(tmp_path: Path) -> None:
    d = _mini(tmp_path, "rst_clean")
    (d / "build" / "base" / "reset_scan_synth.tsv").unlink()
    rep = C.run(d, ["resets"], "synth", "summary")
    c = rep["checks"][0]
    assert c["status"] == "pass" and "netlist" in c["incomplete"] and not rep["pass"]
    assert c["parts"]["netlist"].startswith("not run: needs Vivado")
    assert "PARTIAL" in rep["digest"]


def test_reset_findings_are_not_waivable_by_lint_waivers(tmp_path: Path) -> None:
    d = _mini(tmp_path)
    (d / "lint").mkdir()
    (d / "lint" / "waivers.yaml").write_text(yaml.safe_dump({"waivers": [
        {"rule": "HDL-RST-01", "match": "*", "reason": "x", "owner": "y", "date": "2026-11-14"}]}))
    assert C.run(d, ["resets"], "synth")["checks"][0]["status"] == "fail"


@needs_elab
def test_vivado_session_is_one_call_for_all_missing_reports(tmp_path: Path) -> None:
    d = _mini(tmp_path, "rst_clean")
    (d / "build" / "base" / "reset_scan_synth.tsv").unlink()
    (d / "build" / "base" / "control_sets_synth.rpt").unlink()
    (d / "build" / "base" / "post_synth.dcp").write_text("dcp")
    calls = []

    def fake(dcp: Path, out: Path, names: list[str]) -> tuple[int, str]:
        calls.append(names)
        shutil.copy(SEEDED / "rst_clean" / "reset_scan.tsv", out / "reset_scan.tsv")
        shutil.copy(SEEDED / "rst_clean" / "control_sets.rpt", out / "control_sets.rpt")
        (out / "cmt.not_run.txt").write_text("cmt not run: test")
        return 0, "ok"
    rep = C.run(d, "all", "synth", vivado=fake)
    assert calls == [["cmt", "control_sets", "reset_scan"]]
    st = {c["check"]: c for c in rep["checks"]}
    assert st["resets"]["status"] == "pass" and not st["resets"]["incomplete"]
    assert st["clocking"]["parts"]["cmt"].startswith("not run: cmt not run")


def test_select_all_skips_checks_that_do_not_apply(tmp_path: Path) -> None:
    chosen, skipped = C.select("all", "rtl", tmp_path)
    assert "lint" in chosen and "cdc" not in chosen
    assert set(skipped) == {"fsm", "gt_plan", "doc", "axi_profile"}
    with pytest.raises(KeyError):
        C.select(["nope"], "rtl", tmp_path)


# ---- sign-off gates use the registry ---------------------------------------------------------------------------------
def test_gates_resets_gate_uses_the_registry(tmp_path: Path) -> None:
    from flow import gates as G
    for case, want in (("rst_clean", True), ("rst_f4_cdc_sync", False)):
        d = _mini(tmp_path / case, case)
        g: dict[str, bool] = {}
        r = G._resets(d / "build" / "base", g)
        assert g["post_synth_resets_clean"] is want, (case, r)
    g = {}
    assert G._resets(tmp_path / "nowhere", g) is None and g == {}       # an older build: no such gate


def test_doc_gate_goes_through_the_registry(tmp_path: Path, monkeypatch) -> None:
    import agent.graph.document as D
    monkeypatch.setattr(D, "doc_gate", lambda design, required: ["p1", "p2 " + ",".join(required)])
    assert D.registry_doc_gate(tmp_path, ["g"]) == ["p1", "p2 g"]


def test_agent_check_tool_is_registered_and_offered_to_the_designer() -> None:
    import agent.core.tools  # noqa: F401
    from agent.core.registry import TOOLS
    from agent.graph import run as RUN
    assert "check" in TOOLS and set(TOOLS["check"].input_schema["properties"]["names"]["items"]["enum"]) == {"all", *C.CHECKS}
    for n in range(1, 10):
        assert "check" in RUN.effective_tools("rtl", n, "V3")
    assert "check" not in RUN.effective_tools("tests", 2, "V3") and "check" not in RUN.effective_tools("model", 2, "V3")
    assert "gt_plan" in RUN.effective_tools("rtl", 2, "V3")
    for old in ("lint", "gates", "check_constraints", "report_digest"):      # thin aliases kept: recorded runs call them
        assert old in TOOLS


# review rounds 2 and 3: the regression designs are in flow/tests/test_71b_reset_elab.py (brief 71B)
REG = Path(__file__).parent / "data" / "b71_resets"


def test_source_list_is_the_builds_own_expansion() -> None:
    """The check reads exactly the files flow/prepare.py builds (``**`` recurses there and here)."""
    from flow import prepare
    for d in (ROOT / "designs").iterdir():
        if not (d / "build.yaml").is_file():
            continue
        pats = (yaml.safe_load((d / "build.yaml").read_text()) or {}).get("sources") or []
        try:
            want = list(dict.fromkeys(prepare.expand(pats)))
        except SystemExit:
            continue
        assert C.build_sources(d) == want, d.name
    g = REG / "d_glob"
    assert {p.name for p in C.build_sources(g, root=g)} == {"x.sv", "y.sv"}


def test_stale_session_report_without_a_checkpoint(tmp_path: Path) -> None:
    import os
    d = _mini(tmp_path, "rst_clean")
    out = d / "build" / "checks" / "base" / "synth"
    out.mkdir(parents=True)
    (out / "cmt.rpt").write_text("CMT u MMCM VCO 1 PFD 1 VIOLATION old\n")
    os.utime(out / "cmt.rpt", (1, 1))                          # older than the build's reports
    assert C.Ctx(d, "synth").report("cmt") is None
