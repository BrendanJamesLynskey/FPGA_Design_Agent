"""The spec interview and the spec oracle (05b): one question at a time, a default with a reason, the oracle
answers only with a verbatim quote from the hidden spec."""

import pytest

from agent.graph.interview import NOT_SPECIFIED, Interview, Question, SpecOracle


def _q(i, text="Is the reset active low?"):
    return Question(id=f"q{i}", text=text, default="yes, active low", reason="the board's CPU_RESETN is active low")


def test_oracle_answers_only_with_a_real_quote(tmp_path):
    hidden = tmp_path / "full_spec.yaml"
    hidden.write_text("reset:\n  polarity: active low (CPU_RESETN)\n")
    replies = iter([{"answer": "active low", "quote": "polarity: active low (CPU_RESETN)"},
                    {"answer": "add a UART at 1 Mbaud", "quote": "uart: 1 Mbaud"},          # invented: refused
                    {"answer": NOT_SPECIFIED, "quote": None}])
    o = SpecOracle(hidden, lambda sys, user: next(replies))
    iv = Interview()
    a = iv.ask(_q(1), o)
    b = iv.ask(_q(2, "What baud rate?"), o)
    c = iv.ask(_q(3, "Gamma curve?"), o)
    assert (a.status, a.by) == ("answered", "oracle") and a.evidence
    assert b.status == "defaulted" and b.answer == "yes, active low"
    assert c.status == "defaulted"
    assert iv.summary()["asked"] == 3 and iv.summary()["answered"] == 1
    assert any(e.get("refused") for e in o.log)


def test_interview_off_defaults_everything():
    iv = Interview()
    q = iv.ask(_q(1), None)
    assert (q.status, q.by, q.answer) == ("defaulted", "default", "yes, active low")


def test_a_question_needs_a_default_and_a_reason():
    with pytest.raises(ValueError):
        Interview().ask(Question("q", "Clock?", "", ""), None)


def test_resolve_clears_open_questions():
    spec = {"open_questions": [{"question": "Gamma curve?", "default": "no"}, {"question": "Auto-repeat?"}]}
    iv = Interview()
    iv.ask(_q(1, "Gamma curve?"), None)
    out = iv.resolve_into(spec)
    assert [o["question"] for o in out["open_questions"]] == ["Auto-repeat?"]
    assert out["resolved_questions"][0]["by"] == "default"
