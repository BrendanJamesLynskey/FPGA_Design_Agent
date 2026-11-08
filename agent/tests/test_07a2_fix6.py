"""Brief 07a2 fix 6: the clarify register-map rule on c15_softmax_unit run 2 (the map was asked and answered in range-line
form, but neither the copy into registers.map nor the gate understood "X0..X3: offset 0x00-0x03")."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent.graph.interview import (REQUEST_OFFSETS, answer_register_rows, apply_register_answer, register_map_errors,
                                   request_needs_register_map)

ROOT = Path(__file__).resolve().parents[2]
SPEC_MD = (ROOT / "benchmark/course/tasks/c15_softmax_unit/spec.md").read_text()
RUN2 = yaml.safe_load((Path(__file__).parent / "fixtures/softmax_run2_clarify.yaml").read_text())


def run2_spec() -> dict:
    return {"registers": RUN2["registers"], "resolved_questions": RUN2["resolved_questions"], "open_questions": []}


def test_the_softmax_spec_triggers_the_rule() -> None:
    assert request_needs_register_map(SPEC_MD)


def test_range_lines_expand_to_one_register_per_offset() -> None:
    rows = answer_register_rows(RUN2["resolved_questions"][0]["answer"])
    assert [(r["name"], r["offset"]) for r in rows] == [
        ("X0", 0), ("X1", 1), ("X2", 2), ("X3", 3), ("GO", 16), ("STATUS", 17),
        ("OUT0", 32), ("OUT1", 33), ("OUT2", 34), ("OUT3", 35)]


def test_run2_gate_fails_on_the_invented_map() -> None:
    errs = register_map_errors(SPEC_MD, run2_spec())
    assert errs, "run 2 passed the gate with ID/CTRL/SCORE1..7 beside the real map"
    text = " ".join(errs)
    assert "no register at offset 0x01" in text.replace(", ", " ") or "0x01" in text
    assert "does not list" in text and "0x04" in text            # the role's CTRL at 4 is invented


def test_applying_the_answer_replaces_the_invented_map() -> None:
    spec = apply_register_answer(run2_spec())
    offs = sorted(e["offset"] for e in spec["registers"]["map"])
    assert offs == [0, 1, 2, 3, 16, 17, 32, 33, 34, 35]
    assert register_map_errors(SPEC_MD, spec) == []
    assert next(e for e in spec["registers"]["map"] if e["offset"] == 1)["name"] == "X1"
    yaml.safe_dump(spec)


def test_a_human_answer_keeps_the_role_entries() -> None:
    spec = run2_spec()
    spec["resolved_questions"][0] = {**spec["resolved_questions"][0], "by": "human"}
    kept = apply_register_answer(spec)["registers"]["map"]
    assert {e["offset"] for e in kept} >= {4, 8, 20}               # only the oracle's answer is the whole map


def test_trigger_wording() -> None:
    for t in ("Read the result back over the USB-UART.", "I will write the value and read back the result.",
              "A host interface lets me write to start.", "Everything goes through the shell."):
        assert request_needs_register_map(t), t
    assert not request_needs_register_map("The shell registers are at offsets 0x00 to 0x0F.")
    assert not request_needs_register_map("A blinking LED on the board.")
    assert not REQUEST_OFFSETS.search("starting at 0xB400, the I2C address is 0x4B")


def test_hex_constants_are_not_offsets() -> None:
    req = "Over the test shell I can read the state. The feedback taps are a register, starting at 0xB400."
    assert request_needs_register_map(req)
