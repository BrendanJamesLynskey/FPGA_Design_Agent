"""Brief 174: the spec interview reads board_facts.yaml and does not ask what a sourced fact already answers."""

import yaml

from agent.graph.interview import Interview, Question
from agent.graph.package_facts import fact_for, load_facts


def _facts(tmp_path, rows):
    (tmp_path / "board_facts.yaml").write_text(yaml.safe_dump({"facts": rows}))
    return load_facts(tmp_path)


def _row(key, value, conf="high", loc="BOM row 60"):
    return {"key": key, "value": value, "confidence": conf, "source": {"file": "board/bom.csv", "locator": loc, "sha256": "ab" * 32}}


class _Counting:
    name = "human"
    asked = 0

    def answer(self, q):
        _Counting.asked += 1
        return "not specified", None


def test_sourced_fact_is_not_asked_again(tmp_path):
    facts = _facts(tmp_path, [_row("chip.phy.DP83867", {"mpn": "DP83867CSRGZT"}), _row("pin.led0", {"pin": "H17", "iostandard": "LVCMOS33"}),
                              _row("part", "xc7a100tcsg324-1", "user-declared", "manifest")])
    iv = Interview(facts=facts)
    who = _Counting()
    a = iv.ask(Question("q1", "Which Ethernet PHY is on the board?", "unknown", "the PHY sets the RGMII delay mode"), who)
    b = iv.ask(Question("q2", "Which pin does led0 use?", "H17", "pin"), who)
    c = iv.ask(Question("q3", "What is the reset polarity?", "active low", "reset"), who)      # no fact: asked as before
    assert (a.status, a.by, a.fact, a.answer) == ("answered", "package", "chip.phy.DP83867", "DP83867CSRGZT")
    assert "board/bom.csv, BOM row 60" in a.evidence and "sha256" in a.evidence
    assert b.by == "package" and b.fact == "pin.led0"
    assert c.status == "defaulted" and _Counting.asked == 1
    assert iv.summary()["answered"] == 2


def test_unsourced_low_confidence_or_ambiguous_facts_are_not_used(tmp_path):
    facts = _facts(tmp_path, [_row("chip.phy.DP83867", {"mpn": "A"}, "low"), _row("pin.led1", {"pin": "A1"}),
                              _row("pin.led1", {"pin": "B2"})])
    assert fact_for("Which PHY?", facts) is None                     # low confidence
    assert fact_for("Which pin does led1 use?", facts) is None       # two different values: ask
    bad = _row("part", "x")
    bad["source"] = {}
    assert load_facts(tmp_path) == [f for f in load_facts(tmp_path)]
    (tmp_path / "board_facts.yaml").write_text(yaml.safe_dump({"facts": [bad]}))
    assert load_facts(tmp_path) == []                                # no source, not a fact


def test_no_package_changes_nothing(tmp_path):
    assert load_facts(tmp_path) == []
    iv = Interview()
    q = iv.ask(Question("q1", "Which Ethernet PHY is on the board?", "x", "y"), None)
    assert q.by == "default"
