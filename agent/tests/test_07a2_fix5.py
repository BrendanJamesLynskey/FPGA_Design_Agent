"""Brief 07a2 fix 5, group C: an answered register map overrides the clarify role's proposed default."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent.graph.interview import Interview, Question, SpecOracle, apply_register_answer, register_map_errors

HIDDEN = Path(__file__).resolve().parents[2] / "benchmark/course/tasks/c10_dds_sine/hidden/spec.yaml"
REQUEST = "Expose the oscillator over the test shell registers. LED0 shows done."


def role_spec() -> dict:
    """What batch 1 run 2's clarify role wrote: right offsets, its own DATA packing ([15:0] sign-extended)."""
    return {"registers": {"map": [
        {"offset": 0, "name": "FW", "access": "RW", "reset": 0, "bits": "[23:0] frequency word"},
        {"offset": 4, "name": "DATA", "access": "RO", "reset": 0, "bits": "[15:0] sample 2m sign-extended to 16 bits"}]},
        "open_questions": [{"question": "What is the register map (offsets, widths, reset values, access)?",
                            "default": "FW 0, DATA 4", "reason": "no offsets given"}]}


def test_answered_register_map_overrides_the_role_default() -> None:
    oracle = SpecOracle(HIDDEN, lambda s, u: {"answer": "not specified", "quote": None})
    iv = Interview()
    spec = role_spec()
    iv.ask(Question("q1", spec["open_questions"][0]["question"], "FW 0, DATA 4", "no offsets"), oracle)
    spec = apply_register_answer(iv.resolve_into(spec))
    data = next(e for e in spec["registers"]["map"] if e["name"] == "DATA")
    assert data["bits"].startswith("[11:0] sample 2m, [27:16] sample 2m+1") and "sign-extended" not in data["bits"]
    assert data["offset"] == 4 and data["access"] == "RO"
    assert {e["name"] for e in spec["registers"]["map"]} >= {"FW", "GO", "STATUS", "PTR", "DATA"}   # missing ones added
    assert register_map_errors(REQUEST, spec) == []
    yaml.safe_dump(spec)                                                       # still valid YAML


def test_a_free_form_human_answer_changes_nothing() -> None:
    spec = role_spec()
    spec["resolved_questions"] = [{"question": "Which offset is DATA?", "answer": "four", "status": "answered"}]
    assert apply_register_answer(spec)["registers"] == spec["registers"]
