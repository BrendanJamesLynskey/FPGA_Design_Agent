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


# ---- brief 190, item 10: the new-protocol intake ------------------------------------------------------------------------------------------
from agent.graph.interview import PROTOCOL_QUESTIONS, ensure_protocol_questions, request_is_protocol  # noqa: E402

ITCH_REQ = "Build a feed handler that decodes a binary market-data protocol from UDP datagrams and keeps a top of book."
TOPICS = ["session", "delimiting", "encodings", "largest", "sequencing", "gaps"]


def test_the_six_questions_each_have_a_default_and_a_reason() -> None:
    assert [q.topic for q in PROTOCOL_QUESTIONS] == TOPICS
    for q in PROTOCOL_QUESTIONS:
        assert q.text.endswith("?") and len(q.default) > 40 and len(q.reason) > 60
        Question(id="x", text=q.text, default=q.default, reason=q.reason)         # the Interview's own validity rule would accept it
        # a question never asks twice about its own topic: its own text is seen by its own pattern
        import re
        assert re.search(q.seen, q.text), q.topic


def test_a_protocol_request_gets_all_six_and_a_plain_request_none() -> None:
    spec, added = ensure_protocol_questions(ITCH_REQ, {"open_questions": [{"question": "Which board?", "default": "nexys", "reason": "only one"}]})
    assert added == TOPICS
    assert [o["question"] for o in spec["open_questions"]][0] == "Which board?" and len(spec["open_questions"]) == 7
    assert all(o["default"] and o["reason"] for o in spec["open_questions"])
    for plain in ("Blink an LED at 1 Hz.", "A UART echo with a register map.", "Fix the reset bug in the SPI protocol block; UART framing is 8N1.", ""):
        assert not request_is_protocol(plain)
        same, none = ensure_protocol_questions(plain, {"open_questions": []})
        assert none == [] and same == {"open_questions": []}


def test_acronyms_match_in_capitals_only_and_the_named_cases_match() -> None:
    assert request_is_protocol("a FIX engine") and request_is_protocol("an OUCH order sender") and request_is_protocol("decode ITCH")
    assert not request_is_protocol("fix it") and request_is_protocol("check the sequence numbers of each datagram")


def test_topics_the_spec_already_asked_are_not_asked_again() -> None:
    spec = {"open_questions": [{"question": "Is a heartbeat sent, and is there a login?", "default": "no", "reason": "r"}],
            "resolved_questions": [{"question": "What is the maximum message size?", "answer": "64 bytes"},
                                   {"question": "How do sequence numbers behave?", "answer": "per packet"}]}
    out, added = ensure_protocol_questions(ITCH_REQ, spec)
    assert added == ["delimiting", "encodings", "gaps"]
    assert ensure_protocol_questions(ITCH_REQ, out)[1] == []                  # idempotent: a second call adds nothing


def test_the_questions_flow_through_the_interview_with_defaults_and_the_record_says_so() -> None:
    spec, _ = ensure_protocol_questions(ITCH_REQ, {"open_questions": []})
    iv = Interview()
    for i, o in enumerate(spec["open_questions"]):
        iv.ask(Question(f"q{i}", o["question"], o["default"], o["reason"]), None)
    s = iv.summary()
    assert s["asked"] == 6 and s["defaulted"] == 6 and all(q["by"] == "default" for q in s["questions"])
    out = iv.resolve_into(spec)
    assert not out["open_questions"] and len(out["resolved_questions"]) == 6
    assert "big-endian" in next(q for q in out["resolved_questions"] if "byte order" in q["question"])["answer"]


def test_the_oracle_answers_a_protocol_question_only_from_the_hidden_spec(tmp_path) -> None:
    hidden = tmp_path / "full_spec.yaml"
    hidden.write_text("protocol:\n  length: 2-byte big-endian length before every message\n")
    replies = iter([{"answer": "2-byte big-endian length prefix", "quote": "length: 2-byte big-endian length before every message"},
                    {"answer": NOT_SPECIFIED, "quote": None}])
    o = SpecOracle(hidden, lambda sys, user: next(replies))
    iv = Interview()
    d, e = (PROTOCOL_QUESTIONS[1], PROTOCOL_QUESTIONS[2])
    a, b = iv.ask(Question("d", d.text, d.default, d.reason), o), iv.ask(Question("e", e.text, e.default, e.reason), o)
    assert (a.status, a.by) == ("answered", "oracle") and (b.status, b.answer) == ("defaulted", e.default)


def test_the_t1_request_the_goldens_use_is_not_a_protocol_request() -> None:
    """The request-golden tests (test_08f) run the T1 dimmer; it must not gain questions."""
    from pathlib import Path
    t1 = Path(__file__).resolve().parents[2] / "designs" / "t1_dimmer_counter"
    for f in t1.glob("spec.md"):
        assert not request_is_protocol(f.read_text())
