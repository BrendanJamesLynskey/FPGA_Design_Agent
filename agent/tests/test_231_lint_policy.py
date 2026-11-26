"""Brief 231 item 1b/1c (agent side): the lint tool switches PROCASSINIT off (initial values are checked by STD-INIT-01 / STD-INIT-02) and
explains DECLFILENAME in one line (rule HDL-STY-01)."""

from __future__ import annotations

from agent.core import dispatch
from agent.core.runner import RunResult
from agent.core.tools import LINT_HINTS, LINT_OFF, lint_hints
from agent.tests.conftest import FakeRunner

DECL = ("%Warning-DECLFILENAME: designs/x/rtl/p5_core.sv:2:8: Filename 'p5_core' does not match MODULE name: 'fifo_core'\n"
        "                       2 | module fifo_core #(\n"
        "%Error: Exiting due to 1 warning(s)\n")


def test_procassinit_is_off_and_nothing_else_is() -> None:
    assert LINT_OFF == ["-Wno-PROCASSINIT"]


def test_the_lint_tool_passes_the_switch_to_verilator(session) -> None:
    session.runner = FakeRunner({"lint": RunResult(0, "", "", 0.1)})
    dispatch(session, "lint", {})
    argv = next(c for c in getattr(session.runner, "calls", []) if "--lint-only" in str(c))
    assert "-Wno-PROCASSINIT" in str(argv) and "-Wall" in str(argv)


def test_declfilename_gets_a_repair_note_and_still_fails(session) -> None:
    session.runner = FakeRunner({"lint": RunResult(1, "", DECL, 0.1)})
    r = dispatch(session, "lint", {})
    assert r["ok"] is False
    assert "Rename the file to <module>.sv" in r["output"] and "HDL-STY-01" in r["output"]


def test_hints_only_for_the_codes_present() -> None:
    assert lint_hints("%Warning-UNUSEDSIGNAL: x") == ""
    assert lint_hints(DECL).strip() == LINT_HINTS["DECLFILENAME"]


def test_a_spec_with_no_reset_input_is_asked_the_reset_model() -> None:
    from agent.graph.interview import ensure_reset_model_question, has_reset_input
    spec = {"reset": {"port": "none", "kind": "none"}, "open_questions": []}
    out, added = ensure_reset_model_question(spec)
    assert added and "reprogram" in out["open_questions"][0]["default"] and "STD-INIT-02" in out["open_questions"][0]["reason"]
    assert spec["open_questions"] == []                                    # the input is not changed
    again, added2 = ensure_reset_model_question(out)
    assert not added2 and again is out                                     # asked once
    assert ensure_reset_model_question({"reset": "none"})[1] is True


def test_a_spec_with_a_reset_or_a_stated_model_is_not_asked() -> None:
    from agent.graph.interview import ensure_reset_model_question, has_reset_input
    assert has_reset_input({"reset": {"port": "rst_n"}}) and not has_reset_input({"reset": {"port": "none"}})
    assert ensure_reset_model_question({"reset": {"port": "rst_n", "polarity": "active_low"}})[1] is False
    assert ensure_reset_model_question({"reset": {"port": "none", "model": "reprogram"}})[1] is False
    assert ensure_reset_model_question({"reset": {"port": "none"}, "resolved_questions": [{"question": "Is the reset model reprogram?"}]})[1] is False


def test_the_spec_schema_refuses_an_unknown_reset_model() -> None:
    from agent.graph.spec_schema import shape_errors
    assert not [e for e in shape_errors({"reset": {"port": "none", "model": "reprogram"}}) if "reset.model" in e]
    assert any("reset.model" in e for e in shape_errors({"reset": {"port": "none", "model": "sometimes"}}))


def test_no_assertion_bench_is_flagged_and_a_checking_one_is_not(tmp_path) -> None:
    from agent.core.cocotb_lint import bench_hygiene_text, no_assertion_bench
    base = "import cocotb\nfrom model import Model\n\n@cocotb.test()\nasync def t(dut):\n    m = Model()\n    {body}\n"
    f = tmp_path / "a.py"
    f.write_text(base.format(body="await cocotb.triggers.Timer(1, 'ns')"))
    v = no_assertion_bench(f)
    assert v and v["tests"] == ["t"] and "no assert" in bench_hygiene_text([v], tmp_path)
    for body in ("assert int(dut.q.value) == 0", "raise AssertionError('x')", "cocotb.log.info('x'); dut._log.info('x'); raise SystemExit"):
        f.write_text(base.format(body=body))
        assert no_assertion_bench(f) is None
    f.write_text("import cocotb\nfrom arith.tools import bench\n\n@cocotb.test()\nasync def t(dut):\n    await bench.run(dut)\n")
    assert no_assertion_bench(f) is None                    # a helper of its own may assert
    f.write_text("def helper():\n    pass\n")
    assert no_assertion_bench(f) is None                    # no tests at all


def test_a_passing_simulation_with_a_vacuous_bench_carries_the_advisory(session) -> None:
    (session.design / "tests").mkdir(exist_ok=True)
    (session.design / "tests" / "test_x_rtl.py").write_text("import cocotb\n\n@cocotb.test()\nasync def t(dut):\n    pass\n")
    session.runner = FakeRunner({"simulate": RunResult(0, "1 passed", "", 0.1)})
    r = dispatch(session, "simulate", {})
    assert r["ok"] is True and r["bench_hygiene"][0]["tests"] == ["t"] and "[bench hygiene, advisory]" in r["output"]
