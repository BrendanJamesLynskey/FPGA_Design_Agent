"""Brief 08f: the independent spec-only test role and its gate (agent/graph/spectest.py), tested with stub model calls.

The integration tests run a real cocotb bench on Icarus against a tiny design and skip when iverilog is not installed."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest
import yaml

from agent.core.runner import LocalRunner, RunResult
from agent.core.session import ROOT
from agent.graph import repair, roles, spectest
from agent.graph import run as gr

HAVE_ICARUS = shutil.which("iverilog") is not None

SPEC_MD = "# Adder\nLED shows SW plus one, registered. Top module `add_top`, ports as in the board's master XDC. SW is 4 bits wide here.\n"
RESOLVED = [{"question": "Is LED signed?", "answer": "No, unsigned.", "status": "answered", "by": "oracle"},
            {"question": "Latency?", "answer": "two clocks", "status": "defaulted", "by": "oracle"}]

GOOD_RTL = """module add_top (input logic CLK100MHZ, input logic [3:0] SW, output logic [4:0] LED);
  always_ff @(posedge CLK100MHZ) LED <= {1'b0, SW} + 5'd1;
endmodule
"""
BAD_RTL = GOOD_RTL.replace("5'd1", "5'd2")

BENCH = '''import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import spec_ref
PARAMS = {}

@cocotb.test()
async def test_led_is_sw_plus_one(dut):
    # request: "LED shows SW plus one, registered"
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, "ns").start())
    for sw in range(16):
        dut.SW.value = sw
        await ClockCycles(dut.CLK100MHZ, 3)
        assert int(dut.LED.value) == spec_ref.led(sw), f"SW={sw}: expected LED {spec_ref.led(sw)} (SW plus one), design drove {int(dut.LED.value)}"
'''
REF = "def led(sw):\n    return sw + 1\n"
WRONG_BENCH = BENCH.replace("spec_ref.led(sw)", "spec_ref.led(sw) + 7")


def reply(bench=BENCH, ref=REF):
    return f"=== FILE: spectest/spec_ref.py ===\n{ref}=== END FILE ===\n=== FILE: spectest/spec_bench.py ===\n{bench}=== END FILE ===\n"


@pytest.fixture
def design():
    d = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}" / "add"
    (d / "rtl").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "__init__.py").write_text("")
    (d / ".no_shell").write_text("")
    (d / "spec.md").write_text(SPEC_MD)
    (d / "spec.yaml").write_text(yaml.safe_dump({"top": "add_top", "behaviour": {"x": ["SECRET agent reading"]},
                                                 "resolved_questions": RESOLVED}))
    (d / "build.yaml").write_text("top: add_top\n")
    (d / "rtl" / "add.sv").write_text(GOOD_RTL)
    (d / "tests" / "add_bench.py").write_text("# the agent's own bench\nassert True\n")
    yield d
    shutil.rmtree(d.parent, ignore_errors=True)


class Calls:
    def __init__(self, *replies):
        self.replies, self.log = list(replies), []

    def __call__(self, system, user):
        self.log.append((system, user))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


# --- what the role is given --------------------------------------------------------------------------------------------

def test_the_role_sees_the_request_the_interview_and_the_board_but_nothing_of_the_agents(design):
    (design / "model.py").write_text("AGENT_MODEL_MARKER = 1\n")
    (design / "rtl" / "add.sv").write_text(GOOD_RTL + "// RTL_MARKER\n")
    p = spectest.role_prompt(design, "nexys_a7_100t")
    assert "LED shows SW plus one" in p and "No, unsigned." in p and "CLK100MHZ" in p
    assert "NOT CONFIRMED" in p and "ANSWERED by the requester" in p      # a defaulted answer is labelled as a guess
    for secret in ("AGENT_MODEL_MARKER", "RTL_MARKER", "SECRET agent reading", "the agent's own bench"):
        assert secret not in p
    assert "uart_bfm" not in p                                              # a no-shell design gets no shell material
    (design / ".no_shell").unlink()
    assert "UartBfm" in spectest.role_prompt(design, "nexys_a7_100t")


def test_the_spec_test_role_has_no_jail_entry_and_the_four_roles_are_untouched():
    assert set(roles.ROLES) == {"clarify", "model", "tests", "rtl"}        # the new role is a plain text call, never a tool session


def test_reply_parsing_drops_paths_outside_spectest_and_fences():
    files = spectest.parse_files("=== FILE: ../model.py ===\nx\n=== END FILE ===\n=== FILE: spectest/spec_ref.py ===\n```python\nA=1\n```\n=== END FILE ===\n"
                                 "=== FILE: spectest/../rtl/x.sv ===\ny\n=== END FILE ===")
    assert files == {"spectest/spec_ref.py": "A=1\n"}


def test_static_problems_catch_missing_syntax_and_the_agents_model(design):
    assert len(spectest.static_problems(design)) == 2
    spectest.write_files(design, {"spectest/spec_ref.py": "def f(:\n", "spectest/spec_bench.py": "import model\n"})
    p = " ".join(spectest.static_problems(design))
    assert "does not compile" in p and "imports `model`" in p and "no @cocotb.test" in p and "PARAMS" in p


def test_verdict_parsing_never_fails_a_design_on_an_unreadable_reply():
    assert spectest.parse_verdict('{"verdict": "design_wrong", "reason": "r"}')["verdict"] == "design_wrong"
    assert spectest.parse_verdict('```json\n{"verdict": "bench_wrong", "reason": "r"}\n```')["verdict"] == "bench_wrong"
    assert spectest.parse_verdict("I think the design is wrong")["verdict"] == "bench_wrong"


def test_triage_sees_both_benches_and_the_spec_but_no_rtl(design):
    spectest.write_files(design, {"spectest/spec_bench.py": BENCH, "spectest/spec_ref.py": REF})
    t = spectest.triage_prompt(design, "- test_led: expected 3")
    assert "the agent's own bench" in t and "test_led_is_sw_plus_one" in t and "LED shows SW plus one" in t
    assert "always_ff" not in t


# --- the gate, with a fake runner -----------------------------------------------------------------------------------------

class FakeSim:
    """A runner that writes the results.xml of a bench that passes or fails, without a simulator."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def run(self, kind, argv, cwd, env=None, timeout=600):
        d = (ROOT / argv[-1]).parents[1]
        ok = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        x = d / "build" / "spectest" / "sim" / "spectest"
        x.mkdir(parents=True, exist_ok=True)
        (x / "results.xml").write_text('<testsuites><testsuite><testcase name="test_a"/>' + (
            "" if ok else '<testcase name="test_b"><failure message="AssertionError: expected 3, got 4"/></testcase>') + "</testsuite></testsuites>")
        return RunResult(0 if ok else 1, "out", "", 0.2)


def test_gate_pass_is_recorded_and_cached_until_the_rtl_changes(design):
    role, tri = Calls(reply()), Calls('{"verdict":"design_wrong","reason":"x"}')
    r = spectest.gate(design, "nexys_a7_100t", FakeSim([True]), role, tri)
    assert r == {"verdict": "pass", "blocks": False, "evidence": "", "sig": "pass"} and not tri.log
    rec = spectest.record(design)
    assert rec["fired"] and rec["passed"] is True and rec["caught_bug"] is False and rec["bench_repaired"] is False
    sim = FakeSim([False])
    assert spectest.gate(design, "nexys_a7_100t", sim, role, tri)["cached"] and sim.calls == 0
    (design / "rtl" / "add.sv").write_text(GOOD_RTL + "// edit\n")
    assert spectest.gate(design, "nexys_a7_100t", FakeSim([True]), role, tri)["verdict"] == "pass"
    assert len(role.log) == 1                                                  # the bench is written once and reused


def test_design_wrong_blocks_and_goes_to_the_rtl_role_then_a_pass_counts_as_a_caught_bug(design):
    role, tri = Calls(reply()), Calls('{"verdict":"design_wrong","reason":"the request says plus one"}')
    r = spectest.gate(design, "nexys_a7_100t", FakeSim([False]), role, tri)
    assert r["verdict"] == "design_wrong" and r["blocks"] and "plus one" in r["evidence"] and "test_b" in r["evidence"]
    owners, sig = repair.stage2_owners({"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True},
                                        "verif": {"reached": "V3"}, "verif_level": "V3", "spec_test": r})
    assert list(owners) == ["rtl"] and "[spec test]" in owners["rtl"][0] and "spectest" in sig
    r2 = spectest.gate(design, "nexys_a7_100t", FakeSim([True]), role, tri)
    rec = spectest.record(design)
    assert r2["verdict"] == "pass" and rec["caught_bug"] and rec["design_wrong_verdicts"] == 1 and rec["passed"] is True


def test_bench_wrong_repairs_the_bench_once_then_runs_it_again(design):
    role = Calls(reply(), reply(bench=BENCH + "# repaired\n"))
    tri = Calls('{"verdict":"bench_wrong","reason":"the request never says that"}')
    r = spectest.gate(design, "nexys_a7_100t", FakeSim([False, True]), role, tri)
    rec = spectest.record(design)
    assert r["verdict"] == "pass" and rec["bench_repaired"] and rec["bench_wrong_verdicts"] == 1 and rec["bench_writes"] == 2
    assert "YOUR EARLIER BENCH" in role.log[1][1] and "never says that" in role.log[1][1]


def test_bench_wrong_twice_is_unresolved_and_does_not_block(design):
    role, tri = Calls(reply()), Calls('{"verdict":"bench_wrong","reason":"x"}')
    r = spectest.gate(design, "nexys_a7_100t", FakeSim([False]), role, tri)
    assert r["verdict"] == "unresolved" and not r["blocks"] and spectest.record(design)["outcome"] == "unresolved"


def test_the_loop_limit_stops_design_wrong_round_trips(design):
    role, tri = Calls(reply()), Calls('{"verdict":"design_wrong","reason":"x"}')
    sim = FakeSim([False])
    assert spectest.gate(design, "n", sim, role, tri, max_loops=1)["blocks"]
    (design / "rtl" / "add.sv").write_text(GOOD_RTL + "// edit\n")
    r = spectest.gate(design, "n", sim, role, tri, max_loops=1)
    assert r["verdict"] == "unresolved" and not r["blocks"] and len(tri.log) == 1


def test_a_bench_that_never_compiles_is_an_error_not_a_failed_design(design):
    role = Calls("no files here")
    r = spectest.gate(design, "n", FakeSim([True]), role, Calls("{}"))
    assert r["verdict"] == "error" and not r["blocks"] and len(role.log) == 2     # one static repair call


def test_a_model_call_that_raises_never_stops_the_run(design):
    def boom(system, user):
        raise RuntimeError("network down")
    r = spectest.gate(design, "n", FakeSim([True]), boom, boom)
    assert r["verdict"] == "error" and not r["blocks"] and "network down" in r["evidence"]


# --- integration: a real cocotb bench on Icarus ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAVE_ICARUS, reason="needs iverilog")
@pytest.mark.parametrize("rtl,verdict", [(GOOD_RTL, "pass"), (BAD_RTL, "design_wrong")])
def test_real_bench_against_a_correct_and_a_wrong_design(design, rtl, verdict):
    (design / "rtl" / "add.sv").write_text(rtl)
    role, tri = Calls(reply()), Calls('{"verdict":"design_wrong","reason":"the request says plus one"}')
    r = spectest.gate(design, "nexys_a7_100t", LocalRunner(), role, tri, timeout=300)
    assert r["verdict"] == verdict, r
    if verdict == "design_wrong":
        assert "SW=" in r["evidence"] and "expected LED" in r["evidence"]


# --- config, records, resume ------------------------------------------------------------------------------------------------

def test_config_and_resume_round_trip():
    from agent.__main__ import config_from_json
    cfg = gr.Config(spec_md=Path("s.md"), name="n", spec_tests=True, spectest_max_loops=3)
    c = {k: str(v) for k, v in cfg.__dict__.items()}
    c.update(run_limits=cfg.run_limits, profile="single", roles={})
    back = config_from_json(c)
    assert back.spec_tests is True and back.spectest_max_loops == 3 and back.spectest_model == "claude-sonnet-5-5"
    assert gr.Config(spec_md=Path("s.md"), name="n").spec_tests is False


def test_run_record_reads_the_gate_state(design, tmp_path):
    from tools import run_record as rr
    run = design.parent
    assert rr.spec_test_of(run) is None
    spectest.save_state(design, {**spectest.load_state(design), "fired": True, "passed": True, "outcome": "pass", "caught_bug": True,
                                 "design_wrong": 1, "bench_repaired": False, "runs": 2, "bench_writes": 1})
    got = rr.spec_test_of(run)
    assert got["fired"] and got["passed"] and got["caught_bug"] and got["design_wrong_verdicts"] == 1 and got["bench_runs"] == 2
    f = rr.derive({"task": "c", "run_id": "r1", "stop": {"stage": 9, "name": "configuration-and-debug"}}, run)
    assert f["spec_test"]["fired"] is True
    assert "spec_test" not in rr.derive({"task": "c", "run_id": "r1"}, None)
    (run / "config.json").write_text(json.dumps({"spec_tests": "True"}))
    shutil.rmtree(design / "build")
    assert rr.spec_test_of(run) == {"fired": False}
