"""Brief 149: goal-aware change requests (area, fmax, power, latency, retarget, language, mapping) and the question for a
request that matches no class. No model call, no Vivado. The labelled set is results/149_goal_kinds/labelled_requests.json."""
import json
from pathlib import Path

import pytest

from agent.graph import pickup as P

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("text,kind,stage", [
    ("use fewer LUTs, same ports and tests", "area", 1),
    ("raise Fmax to 200 MHz", "fmax", 3),
    ("make it run at 125 MHz instead of 100 MHz", "fmax", 3),
    ("close timing at 150 MHz", "timing", 6),                 # a closure word: the number is not a new clock
    ("retarget to the KR260", "retarget", 1),
    ("cut power below 0.2 W", "power", 3),
    ("lower the latency by two clocks", "latency", 1),
    ("port it to VHDL", "language", 2),
    ("use block RAM instead of LUT RAM", "mapping", 2),      # "LUT RAM" is a mapping, not an area request
    ("increase the clock frequency to 150 MHz", "fmax", 3),  # a change verb does not reopen the RTL for a goal class
])
def test_goal_kinds(text, kind, stage) -> None:
    k, s, words = P.classify_change(text)
    assert (k, s) == (kind, stage) and words


@pytest.mark.parametrize("text", ["make it better", "improve it", "it does not feel right", "fix the typo in the README",
                                  "update the documentation for the new clock"])
def test_unmatched_request_is_a_question_not_stage_0(text) -> None:
    assert P.classify_change(text) == (None, None, [])
    e = P.entry_stage({"state": {}}, {"design": "d", "ddir": "d"}, text)
    assert e["stage"] is None and e["question"] and "--kind" in e["question"]
    assert ("documentation-only" in e["question"]) == ("README" in text or "documentation" in text)


def test_kind_and_from_stage_still_override_the_question() -> None:
    e = P.entry_stage({"state": {}}, {"design": "d", "ddir": "d"}, "make it better", kind="docs")
    assert e["stage"] == P.DOC_ONLY and "question" not in e
    e = P.entry_stage({"state": {}}, {"design": "d", "ddir": "d"}, "make it better", from_stage=4)
    assert e["stage"] == 4


def test_no_request_is_not_a_question() -> None:
    e = P.entry_stage({"state": {"stage": "simulated"}}, {"design": "d", "ddir": "d"}, None)
    assert e["stage"] == 3 and "question" not in e


def test_every_goal_kind_has_a_rule_and_a_kind_choice() -> None:
    assert set(P.GOAL_KINDS) <= set(P.STAGE_OF_KIND)


def test_labelled_set_accuracy() -> None:
    rows = json.loads((ROOT / "results/149_goal_kinds/labelled_requests.json").read_text())
    assert len(rows) >= 60
    ok = sum(P.classify_change(r["request"])[1] == r["stage"] for r in rows)
    assert ok / len(rows) >= 0.9                                # measured 0.946 (results/149_goal_kinds/measure_after2.json)
    assert all(P.classify_change(r["request"])[1] is not None for r in rows if r["stage"] is not None)
    assert all(P.classify_change(r["request"])[1] is None for r in rows if r["stage"] is None)  # a question, never stage 0 silently
