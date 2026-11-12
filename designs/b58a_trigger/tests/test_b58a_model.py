"""The trading path, no simulator: the reference model, the rule validator and schema, the recorded natural-language rule
fixtures, and the mock venue's book against the model's."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from designs.b58a_trigger.host import nl_rule, strategy
from designs.b58a_trigger.host.mock_venue import Venue
from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import Config, Model, residue_check

DESIGN = Path(__file__).resolve().parents[1]


def test_fcs_residue_and_frames():
    residue_check()
    seq, msgs = Venue(seed=3).packet_msgs(91)
    f = bf.with_fcs(bf.feed_frame(seq, msgs))
    assert len(f) == 1510
    o = bf.Order(bf.NEW_ORDER, bf.BUY, 7, 10125, 10, 42, 9)
    assert bf.parse_order(bf.order_frame(o)) == o
    # the board's response template checksum: IPv4 with DF, TTL 64, length 52
    hdr = bf.order_frame(o)[14:34]
    assert bf.ip_checksum(hdr) == 0


def test_venue_book_matches_model():
    """Good frames only: the board's book (as the model computes it) equals the venue's own view."""
    v = Venue(seed=5, ninst=6)
    m = Model(cfg=Config())
    for _ in range(300):
        m.frame(bf.with_fcs(v.frame(random.Random(len(m.book)).randint(1, 5))))
    for inst, e in v.book.items():
        assert m.book.get(inst, [0, 0, 0, 0, 0])[:4] == e
    assert m.cnt["book_mismatch"] == 0 and m.cnt["seq_gaps"] == 0


def test_bad_frame_is_a_gap():
    v = Venue(seed=1)
    m = Model(cfg=Config(halt_on_gap=True))
    m.frame(bf.with_fcs(v.frame(2)))
    m.frame(bf.with_fcs(v.frame(2), bad=True))
    m.frame(bf.with_fcs(v.frame(2)))
    assert m.cnt["seq_gaps"] == 1 and m.halted


@pytest.mark.parametrize("bad,why", [
    ({"match": {"types": []}, "action": {"log": True}}, "types"),
    ({"match": {"types": ["ADD"]}, "action": {}}, "does nothing"),
    ({"match": {"types": ["ADD"], "price": {"op": "<", "value": "1.005"}}, "action": {"log": True}}, "two decimals"),
    ({"match": {"types": ["ADD"]}, "action": {"order": {"side": "buy", "qty": 101, "price": {"mode": "message"}}}},
     "maximum order size"),
    ({"match": {"types": ["ADD"]}, "action": {"order": {"side": "buy", "qty": 1,
                                                        "price": {"mode": "offset", "value": 6}}}}, "price band"),
    ({"match": {"types": ["ADD"], "colour": "red"}, "action": {"log": True}}, "unknown field"),
])
def test_validator_refuses(bad, why):
    with pytest.raises(rl.RuleError, match=why):
        rl.validate(bad)


def test_words_layout():
    n = rl.validate({"match": {"types": ["ADD", "TRADE"], "side": "ask", "instrument": 7,
                               "price": {"op": "<", "value": "101.25"}, "book": "crosses"},
                     "action": {"order": {"side": "sell", "qty": 10, "price": {"mode": "offset", "value": -0.5}},
                                "pin": 1, "log": True}, "holdoff_cycles": 99})
    w = rl.words(n)
    assert w == [1 | 1 << 1 | 1 << 4 | 2 << 5 | 1 << 8 | 2 << 11 | 1 << 13 | 1 << 14 | 2 << 15 | 1 << 17 | 1 << 18
                 | 1 << 19, 7, 10125, 10, (-50) & 0xFFFFFFFF, 99]


def test_schema_agrees_with_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((DESIGN / "rules" / "rule_schema.json").read_text())
    for c in nl_rule.CASES:
        fx = json.loads((DESIGN / "rules" / "fixtures" / f"{c['id']}.json").read_text())
        rule = fx["turns"][-1].get("rule")
        if rule is not None:
            jsonschema.validate(rule, schema)


def test_nl_fixtures_mean_what_was_asked():
    """The recorded luna replies (no model call in CI): every rule either means its sentence or is refused for the
    right reason."""
    r = nl_rule.check()
    assert not r["wrong"] and not r["refused_wrong"] and not r["not_refused"], r
    assert len(r["meant"]) + len(r["refused_right"]) == len(nl_rule.CASES)


def test_strategy_rule_is_valid():
    s = strategy.MidTracker(inst=3, edge=25, qty=5)
    rule = s.update(9900, 10, 10100, 10)
    writes = strategy.rule_writes(0, rule)
    assert len(writes) == 7 and writes[-1] == (strategy.REG_CTRL2, strategy.COMMIT)
    assert s.update(9900, 10, 10100, 10) is None          # no change, nothing to write
