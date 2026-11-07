"""Brief 07a2 fix 3: run 3 (c14_int8_dot_requant, 20261106-211457-2e65) stopped at stage 2 because the tests role's bench
raised cocotb_coverage "CoverPoint must have a parent" at import. The simulate tool showed only cocotb's follow-on
AttributeError (the root cause was in sim.log); the run summary said questions.asked = 0 with 5 answered."""

from __future__ import annotations

import shutil
from pathlib import Path

from agent.core import dispatch
from agent.core.runner import LocalRunner
from agent.core.session import Session
from flow.cocotb_run import failure_excerpt

FIX = Path(__file__).parent / "fixtures"


def test_failure_excerpt_keeps_the_root_cause_of_an_import_error() -> None:
    text = failure_excerpt(FIX / "run3_c14_sim.log")
    assert "Exception: CoverPoint must have a parent" in text
    assert text.index("CoverPoint must have a parent") < text.index("_running_test")      # the root cause comes first
    assert "c14_bench.py\", line 24" in text and "@CoverPoint(\"cov_result_class\"" in text      # the user's own frame
    assert text.startswith("[root cause")


def test_root_cause_is_empty_for_a_log_with_no_exception() -> None:
    from flow.cocotb_run import root_cause
    assert root_cause(["0.00ns INFO cocotb  Running on Icarus", "FAIL  test_x"]) == []


def test_simulate_import_check_returns_the_import_error_as_its_own_kind(session: Session) -> None:
    d = session.design
    shutil.rmtree(d / "tests", ignore_errors=True)
    (d / "tests").mkdir()
    shutil.copy(FIX / "run3_c14_bench.py", d / "tests" / "c14_bench.py")
    (d / "tests" / "test_t1_dimmer_counter_rtl.py").write_text("def test_x():\n    pass\n")
    session.runner = LocalRunner()
    r = dispatch(session, "simulate", {"sim": "icarus"})
    assert not r["ok"] and r["kind"] == "import_error"
    assert r["import_errors"][0]["file"].endswith("tests/c14_bench.py")
    assert "CoverPoint must have a parent" in r["import_errors"][0]["error"]
    assert "CoverPoint must have a parent" in r["output"] and "fails on import" in r["output"]
    assert r["first_failure"]["message"][0].startswith("Exception: CoverPoint must have a parent")


def test_simulate_import_check_passes_a_clean_tests_dir(session: Session) -> None:
    from agent.core.tools import _import_check_tests
    d = session.design
    shutil.rmtree(d / "tests", ignore_errors=True)
    (d / "tests").mkdir()
    (d / "tests" / "helper.py").write_text("X = 1\n")
    session.runner = LocalRunner()
    assert _import_check_tests(session) is None


def test_the_second_clarify_visit_does_not_erase_the_first_visits_questions() -> None:
    from agent.graph.interview import merge_summaries
    q = lambda t, s: {"text": t, "status": s}          # noqa: E731
    first = {"asked": 3, "answered": 2, "defaulted": 1, "questions": [q("a", "answered"), q("b", "answered"), q("c", "defaulted")]}
    second = {"asked": 0, "answered": 0, "defaulted": 0, "questions": []}                       # run 3's second visit
    m = merge_summaries(first, second)
    assert (m["asked"], m["answered"], m["defaulted"]) == (3, 2, 1)
    m = merge_summaries(first, {"questions": [q("c", "defaulted"), q("d", "answered")]})
    assert (m["asked"], m["answered"]) == (4, 3) and [x["text"] for x in m["questions"]] == ["a", "b", "c", "d"]
    assert merge_summaries(None, second)["asked"] == 0


def test_interview_node_merges_into_the_summary_the_state_already_holds(session: Session, tmp_path: Path) -> None:
    import agent.graph.run as gr
    from types import SimpleNamespace
    rt = SimpleNamespace(cfg=SimpleNamespace(interview="off", hidden_spec=None), design=session.design, oracle_llm=None)
    spec = {"name": "x", "open_questions": [], "requirements": []}
    prev = {"asked": 5, "answered": 5, "defaulted": 0, "questions": [{"text": f"q{i}", "status": "answered"} for i in range(5)]}
    try:
        _, summary = gr._interview(rt, spec, {"interview": prev})
    except Exception as e:           # a spec the schema code will not take is not what this test is about
        raise AssertionError(f"_interview raised {e!r}") from e
    assert summary["asked"] == 5 and summary["answered"] == 5
