"""Brief 82P4: the derived-constants check at the stage exit gate (stages 2 and 3), and the unresolved spec-test verdict as a
stop that is not clean. Planted cases only: no model call, no Vivado."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.graph import repair, run as gr, spectest
from agent.graph.stages import MACHINE, classify, constants_stage, exit_check, route_failure
from flow import derived_constants as DC
from tools import run_record as rr

TOP = "module top; fpga_shell #(.DESIGN_ID({id}), .BUILD_STAMP(0)) u_shell (.clk(c)); endmodule\n"
SPEC_TXT = 'Register 0 is the identification word 0x55445031. The design ID is "UEP1".\n'
S2, S3 = MACHINE[2], MACHINE[3]
#: the stage-2 evidence of a design whose other gates are all clean, so the constants gate is the only thing that decides
BASE = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "arch_approval": {"ok": True},
        "standards": {"rules": []}, "verif": {"reached": "V3", "stages": {}}, "verif_level": "V1"}


def design(tmp: Path, rtl: str, spec: str = SPEC_TXT) -> Path:
    d = tmp / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "top.sv").write_text(rtl)
    (d / "spec.md").write_text(spec)
    return d


def only_constants_fail(ev: dict) -> list[str]:
    ok, fails = exit_check(S2, ev)
    return [f for f in fails if f.startswith("constants ")]


def test_stage_two_and_three_have_the_gate():
    assert "constants" in S2.gates and "constants" in S3.gates


def test_a_wrong_bound_design_id_cannot_pass_stage_two(tmp_path):
    d = design(tmp_path, TOP.format(id="32'h55445031"))            # 82P3's four failures: the register-0 word, not "UEP1"
    ev = {**BASE, "constants": {"findings": DC.derive(d, tmp_path)["findings"]}}
    ok, fails = exit_check(S2, ev)
    assert not ok and any("constants CONST-ID-01" in f and "0x55455031" in f for f in fails)


def test_the_right_design_id_passes(tmp_path):
    d = design(tmp_path, TOP.format(id="32'h55455031"))
    assert only_constants_fail({**BASE, "constants": {"findings": DC.derive(d, tmp_path)["findings"]}}) == []


def test_advice_never_blocks(tmp_path):
    d = design(tmp_path, TOP.format(id="not_a_known_name"))          # CONST-ID-02, CONST-LIT-01: advice
    fs = DC.derive(d, tmp_path)["findings"]
    assert fs and not any(f["blocking"] for f in fs)
    assert constants_stage({"findings": fs}) == (True, [])
    assert only_constants_fail({**BASE, "constants": {"findings": fs}}) == []


def test_a_check_that_did_not_run_does_not_fail_a_design():
    assert constants_stage(None) == (True, []) and constants_stage({"findings": [], "error": "boom"}) == (True, [])


def test_a_wrong_clock_period_blocks_stage_three_and_goes_to_constraints():
    f = {"code": "CONST-CLK-01", "severity": "error", "blocking": True, "where": "x.xdc", "message": "create_clock -period 8 ns"}
    ok, fails = constants_stage({"findings": [f]})
    assert not ok and classify(S3, fails) == "constraints" and route_failure(S3, "constraints") == 3


def test_an_id_failure_routes_to_the_rtl_even_when_the_text_says_spec(tmp_path):
    d = design(tmp_path, TOP.format(id="32'h55445031"))
    ok, fails = constants_stage({"findings": DC.derive(d, tmp_path)["findings"]})
    assert classify(S2, fails) == "rtl" and route_failure(S2, "rtl") == 2


def test_the_rtl_role_is_given_the_finding(tmp_path):
    d = design(tmp_path, TOP.format(id="32'h55445031"))
    owners, sig = repair.stage2_owners({**BASE, "constants": {"findings": DC.derive(d, tmp_path)["findings"]}})
    assert list(owners) == ["rtl"] and "CONST-ID-01" in owners["rtl"][0] and "constants" in sig


def test_blocks_helper_and_gate_wrapper(tmp_path):
    d = design(tmp_path, TOP.format(id="32'h55445031"))
    rt = SimpleNamespace(design=d, session=SimpleNamespace(root=tmp_path))
    ev = {"constants": gr.constants_gate(rt)}
    assert gr.constants_blocks(ev) and (d / "build" / "derived_constants.json").is_file()
    assert not gr.constants_blocks({"constants": {"findings": []}}) and not gr.constants_blocks({})


# ---- an unresolved spec-test verdict is not a clean stop -------------------------------------------------------------------
@pytest.mark.parametrize("outcome,expect", [("unresolved", gr.UNRESOLVED_STOP), ("pass", "done"), ("design_wrong", "done"), ("error", "done")])
def test_stop_status(tmp_path, outcome, expect):
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    spectest.save_state(d, {**spectest.load_state(d), "fired": True, "outcome": outcome})
    rt = SimpleNamespace(design=d, cfg=SimpleNamespace(spec_tests=True))
    assert gr.stop_status(rt) == expect
    assert gr.stop_status(SimpleNamespace(design=d, cfg=SimpleNamespace(spec_tests=False))) == "done"   # the gate was off


def test_unresolved_is_not_a_clean_stop_in_the_summary_fields():
    assert gr.UNRESOLVED_STOP != "done" and gr.UNRESOLVED_STOP.startswith("unresolved")


def test_run_record_reports_unresolved_not_pass_and_not_escape(tmp_path):
    run = tmp_path / "run" / "d" / "build" / "spectest"
    run.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"fired": True, "passed": False, "outcome": "unresolved", "design_wrong": 2}))
    base = {"task": "t", "run_id": "r", "split": "development", "stop": {}, "gates": {"V2": "pass"},
            "stage_visits": {"rtl-design-creation": 2}}
    for hidden in (True, False):
        f = rr.derive({**base, "score": {"pass": hidden, "tests_passed": 9, "tests_total": 10}}, tmp_path / "run")
        assert f["outcome"] == "unresolved" and f["hidden_pass"] is hidden and f["escape_level"] is None
    clean = rr.derive({**base, "score": {"pass": False, "tests_passed": 9, "tests_total": 10}}, tmp_path / "none")
    assert clean["outcome"] == "escape"                                  # without the unresolved verdict it is still an escape


# ---- back-test through the exit gate on the 82P3 scored RTL (public RTL and the task's public spec) --------------------------
ROOT = Path(__file__).resolve().parents[2]
B82P3 = ROOT / "benchmark" / "v2" / "runs" / "b82p3"
SPEC = ROOT / "benchmark" / "v2" / "tasks" / "v2_e_udp_endpoint" / "spec.md"
#: run id -> whether its RTL binds the spec's design ID (from the 82P3 records)
RUNS = {"20261117-122336-fa53": False, "20261117-135502-145d": True, "20261117-150856-afed": True,
        "20261117-200835-e7a9": False, "20261117-231304-1e26": False, "20261118-021720-e777": False}


@pytest.mark.parametrize("run,right", sorted(RUNS.items()))
def test_82p3_runs_at_the_exit_gate(run, right, tmp_path):
    import shutil
    d = tmp_path / run
    shutil.copytree(B82P3 / "artifacts" / run / "rtl", d / "rtl")
    shutil.copy(SPEC, d / "spec.md")
    ev = {**BASE, "constants": {"findings": DC.derive(d, tmp_path)["findings"]}}
    assert (only_constants_fail(ev) == []) is right, run
