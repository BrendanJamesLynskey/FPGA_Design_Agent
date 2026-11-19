"""Brief 106: the derived-constants check and the stale-data check, each on planted cases, plus the back-test over the
82P3 run records (public RTL and the task spec: no hidden material)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from flow import checks as C
from flow import derived_constants as DC
from flow import stale_check as SC

ROOT = Path(__file__).resolve().parents[2]
B82P3 = ROOT / "benchmark" / "v2" / "runs" / "b82p3"
SPEC = ROOT / "benchmark" / "v2" / "tasks" / "v2_e_udp_endpoint" / "spec.md"
#: run id -> whether its RTL binds the shell DESIGN_ID to the spec's derived value (read from the run records, see the results README)
RUNS_82P3 = {"20261117-122336-fa53": False, "20261117-135502-145d": True, "20261117-150856-afed": True,
             "20261117-200835-e7a9": False, "20261117-231304-1e26": False, "20261118-021720-e777": False}


def _design(tmp: Path, rtl: dict[str, str], spec: str | None = None) -> Path:
    d = tmp / "d"
    (d / "rtl").mkdir(parents=True)
    for n, t in rtl.items():
        (d / "rtl" / n).write_text(t)
    if spec is not None:
        (d / "spec.md").write_text(spec)
    return d


# ---- derivation ---------------------------------------------------------------------------------------------------------
def test_design_id_is_the_ascii_of_the_quoted_string() -> None:
    t = DC.spec_table('The design ID is "UEP1". The identification word 0x55445031 is register 0.')
    assert t["design_id"]["value"] == 0x55455031 and t["design_id"]["string"] == "UEP1"
    assert [l["value"] for l in t["named_literals"]] == [0x55445031]


def test_a_polynomial_is_not_an_identity_word() -> None:
    t = DC.spec_table("the Ethernet CRC-32: reflected 0xEDB88320, initial value 0xFFFFFFFF")
    assert t["named_literals"] == [] and t["design_id"] is None


@pytest.mark.parametrize("expr,val", [("32'h5545_5031", 0x55455031), ("32'd5", 5), ('"UEP1"', 0x55455031), ("foo", None)])
def test_literals(expr: str, val: int | None) -> None:
    assert DC.parse_literal(expr) == val


# ---- planted cases ------------------------------------------------------------------------------------------------------
TOP = "module top; fpga_shell #(.DESIGN_ID({id}), .BUILD_STAMP(0)) u_shell (.clk(c)); endmodule\n"
SPEC_TXT = 'Register 0 is the identification word 0x55445031. The design ID is "UEP1".\n'


def test_wrong_design_id_is_caught(tmp_path: Path) -> None:
    d = _design(tmp_path, {"top.sv": TOP.format(id="32'h55445031")}, SPEC_TXT)
    r = DC.derive(d, tmp_path)
    assert [f["code"] for f in r["findings"] if f["blocking"]] == ["CONST-ID-01"]
    assert "different constant" in r["findings"][0]["message"]


def test_right_design_id_passes_in_every_spelling(tmp_path: Path) -> None:
    for expr in ("32'h55455031", "32'h5545_5031", '"UEP1"'):
        d = _design(tmp_path / expr.replace("'", "").replace('"', "q"), {"top.sv": TOP.format(id=expr) + "localparam X = 32'h55445031;\n"}, SPEC_TXT)
        assert not DC.derive(d, tmp_path)["findings"], expr


def test_a_name_that_resolves_to_the_wrong_literal_is_caught(tmp_path: Path) -> None:
    rtl = "module top; localparam logic [31:0] ID_WORD = 32'h55445031;\n" + TOP.format(id="ID_WORD")
    d = _design(tmp_path, {"top.sv": rtl}, SPEC_TXT)
    assert [f["code"] for f in DC.derive(d, tmp_path)["findings"]] == ["CONST-ID-01"]


def test_an_unresolvable_binding_is_advice_not_a_pass(tmp_path: Path) -> None:
    d = _design(tmp_path, {"top.sv": TOP.format(id="f(x)") + "localparam X = 32'h55445031;\n"}, SPEC_TXT)
    fs = DC.derive(d, tmp_path)["findings"]
    assert [(f["code"], f["blocking"]) for f in fs] == [("CONST-ID-02", False)]


def test_commented_out_binding_is_not_read(tmp_path: Path) -> None:
    rtl = "// fpga_shell #(.DESIGN_ID(32'h55445031)) u (.clk(c));\n" + TOP.format(id="32'h55455031") + "localparam X = 32'h55445031;\n"
    d = _design(tmp_path, {"top.sv": rtl}, SPEC_TXT)
    assert not DC.derive(d, tmp_path)["findings"]


def test_missing_spec_literal_is_advice(tmp_path: Path) -> None:
    d = _design(tmp_path, {"top.sv": TOP.format(id="32'h55455031")}, SPEC_TXT)
    fs = DC.derive(d, tmp_path)["findings"]
    assert [(f["code"], f["blocking"]) for f in fs] == [("CONST-LIT-01", False)]


def test_no_spec_and_no_shell_are_said_not_silently_passed(tmp_path: Path) -> None:
    d = _design(tmp_path, {"top.sv": "module m; endmodule\n"})
    t = DC.derive(d, tmp_path)
    assert not t["findings"] and any("no spec.md" in n for n in t["notes"])
    d2 = _design(tmp_path / "b", {"top.sv": "module m; endmodule\n"}, SPEC_TXT)
    assert any("no fpga_shell instance" in n for n in DC.derive(d2, tmp_path / "b")["notes"])


def test_clock_period_against_the_board_file() -> None:
    assert DC.xdc_clock_periods("create_clock -add -name c -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];", "CLK100MHZ") == [10.0]
    assert DC.xdc_clock_periods("#create_clock -period 8 [get_ports CLK100MHZ]", "CLK100MHZ") == []
    assert DC.xdc_clock_periods("create_clock -period 8 [get_ports { CLK100MHZ }]", "OTHER") == []


def test_wrong_clock_period_is_caught(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "boards" / "b1").mkdir(parents=True)
    (root / "boards" / "b1" / "board.yaml").write_text("name: b1\npart: p\nclock: {port: CLK, freq_mhz: 100}\n")
    d = root / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "t.sv").write_text("module t; endmodule\n")
    (d / "x.xdc").write_text("create_clock -period 8.00 [get_ports { CLK }];\n")
    (d / "build.yaml").write_text("top: t\npart: p\nboard: b1\nsources: [designs/x/rtl/*.sv]\nconstraints: [designs/x/x.xdc]\n")
    fs = DC.derive(d, root)["findings"]
    assert [(f["code"], f["blocking"]) for f in fs] == [("CONST-CLK-01", True)]
    (d / "x.xdc").write_text("create_clock -period 10.00 [get_ports { CLK }];\n")
    assert not DC.derive(d, root)["findings"]


# ---- back-test on the 82P3 run records ----------------------------------------------------------------------------------
@pytest.mark.parametrize("run,right", sorted(RUNS_82P3.items()))
def test_82p3_back_test(run: str, right: bool, tmp_path: Path) -> None:
    src = B82P3 / "artifacts" / run / "rtl"
    d = tmp_path / run
    shutil.copytree(src, d / "rtl")
    shutil.copy(SPEC, d / "spec.md")
    codes = [f["code"] for f in DC.derive(d, tmp_path)["findings"] if f["blocking"]]
    assert codes == ([] if right else ["CONST-ID-01"]), run


def test_82p3_hidden_scores_match_the_back_test() -> None:
    """The one run the gate passes cleanly and that passed the hidden bench is the only pass; the gate flags 4 of the 5 failures."""
    passed = {r for r in RUNS_82P3 if json.loads((B82P3 / "artifacts" / r / "hidden_score.json").read_text()).get("passed") is True}
    assert passed <= {r for r, right in RUNS_82P3.items() if right}, "a run the gate flags passed the hidden bench"


# ---- the check suite registration ---------------------------------------------------------------------------------------
def test_checks_are_registered_and_run_through_the_suite(tmp_path: Path) -> None:
    assert "constants" in C.CHECKS and "stale" in C.CHECKS
    d = _design(tmp_path, {"top.sv": TOP.format(id="32'h55445031")}, SPEC_TXT)
    r = C.run_one("constants", d, "rtl", root=tmp_path)
    assert r["status"] == "fail" and r["findings"][0]["rule"] == "HDL-ORC-01"
    assert (d / "build" / "derived_constants.json").is_file()


# ---- the stale-data check -----------------------------------------------------------------------------------------------
def _built(tmp: Path) -> tuple[Path, Path]:
    """A design with a recorded build: the manifest lists the inputs' hashes as flow/manifest.py does."""
    root = tmp / "repo"
    d = root / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "a.sv").write_text("module a; endmodule\n")
    (d / "x.xdc").write_text("create_clock -period 10 [get_ports c];\n")
    (d / "spec.md").write_text("spec v1\n")
    (d / "build.yaml").write_text("top: a\npart: p\nsources: [designs/x/rtl/*.sv]\nconstraints: [designs/x/x.xdc]\n")
    (root / "boards" / "b1").mkdir(parents=True)
    (root / "boards" / "b1" / "board.yaml").write_text("name: b1\npart: p\nclock: {port: c, freq_mhz: 100}\n")
    ins = {f: SC.sha(root / f) for f in ("designs/x/rtl/a.sv", "designs/x/x.xdc", "designs/x/build.yaml")}
    (d / "build" / "base").mkdir(parents=True)
    (d / "build" / "base" / "manifest.json").write_text(json.dumps({"build_id": "0badc0de", "inputs": ins}))
    return root, d


def test_fresh_build_is_fresh_and_each_changed_input_makes_it_stale(tmp_path: Path) -> None:
    root, d = _built(tmp_path)
    SC.stamp(d, "build:base", root)
    assert SC.check(d, "build:base", root)["status"] == "fresh"
    for rel, new in (("designs/x/rtl/a.sv", "module a; wire w; endmodule\n"), ("designs/x/x.xdc", "create_clock -period 8 [get_ports c];\n"),
                     ("designs/x/spec.md", "spec v2\n"), ("boards/b1/board.yaml", "name: b1\npart: p\nclock: {port: c, freq_mhz: 125}\n")):
        p = root / rel
        old = p.read_text()
        p.write_text(new)
        r = SC.check(d, "build:base", root)
        assert r["status"] == "stale" and rel in r["changed"], rel
        p.write_text(old)
        assert SC.check(d, "build:base", root)["status"] == "fresh", rel


def test_board_file_is_a_hole_in_the_manifest_but_not_in_the_stamp(tmp_path: Path) -> None:
    """The build manifest does not hash the board file. With only the manifest a board-file change goes unseen; with the stamp it is seen.
    (build.yaml names no board here, so the board is the one whose part matches: b1.)"""
    root, d = _built(tmp_path)
    (root / "boards" / "b1" / "board.yaml").write_text("name: b1\npart: p\nclock: {port: c, freq_mhz: 125}\n")
    assert SC.check(d, "build:base", root)["status"] == "fresh"          # no stamp: only the manifest is compared
    (root / "boards" / "b1" / "board.yaml").write_text("name: b1\npart: p\nclock: {port: c, freq_mhz: 100}\n")
    SC.stamp(d, "build:base", root)
    (root / "boards" / "b1" / "board.yaml").write_text("name: b1\npart: p\nclock: {port: c, freq_mhz: 125}\n")
    assert SC.check(d, "build:base", root)["status"] == "stale"


def test_new_and_removed_source_files(tmp_path: Path) -> None:
    root, d = _built(tmp_path)
    (d / "rtl" / "b.sv").write_text("module b; endmodule\n")
    r = SC.check(d, "build:base", root)
    assert r["status"] == "stale" and r["added"] == ["designs/x/rtl/b.sv"]
    (d / "rtl" / "b.sv").unlink()
    (d / "rtl" / "a.sv").unlink()
    r = SC.check(d, "build:base", root)
    assert r["status"] == "stale" and "designs/x/rtl/a.sv" in r["removed"]


def test_no_record_is_never_fresh(tmp_path: Path) -> None:
    root, d = _built(tmp_path)
    shutil.rmtree(d / "build")
    assert SC.check(d, "build:base", root)["status"] == "no_record"
    assert SC.check(d, "sim", root)["status"] == "no_record"


def test_sim_evidence_goes_stale_when_a_test_or_the_rtl_changes(tmp_path: Path) -> None:
    root, d = _built(tmp_path)
    (d / "tests").mkdir()
    (d / "tests" / "test_a_rtl.py").write_text("def test(): pass\n")
    SC.stamp(d, "sim", root)
    assert SC.check(d, "sim", root)["status"] == "fresh"
    (d / "tests" / "test_a_rtl.py").write_text("def test(): assert 1\n")
    assert SC.check(d, "sim", root)["changed"] == ["designs/x/tests/test_a_rtl.py"]


def test_report_claims_must_cite_a_fresh_build(tmp_path: Path) -> None:
    root, d = _built(tmp_path)
    (d / "README.md").write_text("Timing met on build 0badc0de (WNS 0.4 ns).\n")
    assert SC.claim_findings(d, root) == []
    (d / "README.md").write_text("Timing met on build deadbeef.\n")
    assert [f["code"] for f in SC.claim_findings(d, root)] == ["STALE-CLAIM-01"]
    (d / "README.md").write_text("Timing met on build 0badc0de.\n")
    (d / "rtl" / "a.sv").write_text("module a; wire w; endmodule\n")
    assert [f["code"] for f in SC.claim_findings(d, root)] == ["STALE-CLAIM-01"]


def test_stale_check_in_the_suite_cannot_be_waived(tmp_path: Path) -> None:
    root, d = _built(tmp_path)
    (d / "rtl" / "a.sv").write_text("module a; wire w; endmodule\n")
    r = C.run_one("stale", d, "route", root=root)
    assert r["status"] == "fail" and r["findings"][0]["rule"] == "HDL-ORC-02" and not C.CHECKS["stale"].waivable


def test_every_recorded_build_manifest_is_judged() -> None:
    """The comparison runs on every committed manifest; history is stale by construction (the flow moved on), which the
    results README reports as a count, not a failure."""
    ms = [p for p in (ROOT / "results").rglob("manifest.json") if "inputs" in json.loads(p.read_text())]
    assert ms
    for p in ms:
        r = SC.check_manifest(json.loads(p.read_text()), ROOT)
        assert r["status"] in ("fresh", "stale") and r["inputs"] > 0


# ---- plan repeatability -------------------------------------------------------------------------------------------------
def test_plan_is_the_collapsed_stage_order_not_the_rtl() -> None:
    from flow import plan_repeat as PR
    assert PR.collapse([0, 0, 1, 1, 2, 2, 2]) == (0, 1, 2)
    g = {"t": [{"stages_visited": [0, 0, 1, 1, 2], "params": 5}, {"stages_visited": [0, 1, 1, 2, 2, 2], "params": 5},
               {"stages_visited": None, "params": 7}, {"stages_visited": [0, 1, 2, 1, 2], "params": 5}]}
    s = PR.score(g, {"t": 5})
    r = s["groups"]["t"]
    assert r["no_plan"] == 1 and r["plan"] == {"equal_pairs": 1, "pairs": 3}      # 0>1>2 twice; 0>1>2>1>2 differs
    assert r["visits"]["equal_pairs"] == 0
    assert r["params"] == {"equal_pairs": 3, "pairs": 6} and r["correct"] == {"equal_pairs": 3, "pairs": 4}


def test_a_run_with_no_stage_record_is_never_a_match() -> None:
    from flow import plan_repeat as PR
    s = PR.score({"t": [{"stages_visited": None}, {"stages_visited": None}]})
    assert s["groups"]["t"]["plan"]["pairs"] == 0 and s["total"]["plan"]["rate"] is None


def test_results_are_the_committed_analysis() -> None:
    """results/106_orchestrator/results.json is what analyse.py computes now from the committed records."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("analyse106", ROOT / "results" / "106_orchestrator" / "analyse.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = json.loads((ROOT / "results" / "106_orchestrator" / "results.json").read_text())
    assert mod.backtest_82p3() == committed["backtest_82p3"]
    assert mod.repeatability() == committed["repeatability"]
