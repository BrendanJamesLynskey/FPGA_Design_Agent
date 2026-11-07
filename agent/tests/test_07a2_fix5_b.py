"""Brief 07a2 fix 5: batch-1 fixes (group B: oracle quote check is YAML-aware)."""

from __future__ import annotations

from pathlib import Path

from agent.graph.interview import Question, SpecOracle

# the c10_dds_sine line that batch 1 run 2 quoted: a single-quoted YAML scalar, so the file holds two''s
C10_LINE = ("each read of DATA returns two samples, 12-bit two's complement: sample 2m in [11:0] and sample 2m+1 in "
            "[27:16] (the other bits 0), m = 0..599")


def test_oracle_accepts_a_quote_that_is_the_parsed_yaml_value(tmp_path: Path) -> None:
    f = tmp_path / "spec.yaml"
    f.write_text("requirements:\n  - 'each read of DATA returns two samples, 12-bit two''s complement: sample 2m in "
                 "[11:0] and sample 2m+1 in [27:16] (the other bits 0), m = 0..599'\n")
    assert C10_LINE not in f.read_text()                      # the raw text does not hold the parsed form
    o = SpecOracle(f, lambda s, u: {"answer": "sample 2m in [11:0]", "quote": C10_LINE})
    ans, quote = o.answer(Question("q1", "How is DATA packed?", "[15:0]", "layout"))
    assert ans == "sample 2m in [11:0]" and quote == C10_LINE


def test_oracle_still_refuses_an_invented_quote(tmp_path: Path) -> None:
    f = tmp_path / "spec.yaml"
    f.write_text("requirements:\n  - 'it''s fine'\n")
    o = SpecOracle(f, lambda s, u: {"answer": "x", "quote": "never written anywhere"})
    ans, quote = o.answer(Question("q1", "What colour?", "red", "r"))
    assert ans == "not specified" and quote is None
