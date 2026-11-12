"""Brief 50A: the plain-English parser, replayed from recorded model replies (no model call in CI)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.graph.llm import Reply, Replay
from debug_core.plan import make_plan
from debug_core.request import SYSTEM, clean, extract_json, parse, signal_menu
from debug_core.rtl_index import RtlIndex

FIX = Path(__file__).parent / "fixtures"
REQ = json.loads((FIX / "requests.json").read_text())

#: what each recorded request must plan to (probes, trigger patterns, window asked, buildable)
EXPECT = {
    "t1_count_write": (["win_wr", "addr", "count"], ["1", "10000000"], (16, 32), True),
    "t1_pwm_period": (["phase", "led"], ["00000000"], (0, 1023), True),
    "t1_sync_byte": (["rx_valid", "rx_data", "uart_rx_pin"], ["R", "10100101"], (900, 100), True),
    "t1_or_flags": (["win_wr", "press_clear", "count", "duty"], ["R", "R"], (8, 64), True),
    "brief_fifo_example": (["rx_data"], [], (200, 50), False),
    "t1_reuse_rise": (["win_wr", "count"], ["R"], (4, 8), True),
}


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_recorded_requests_plan_as_expected(name: str) -> None:
    r = REQ[name]
    intent, meta = parse(r["request"], Path(r["design"]), client=Replay(FIX / "llm" / f"{name}.json"))
    assert meta["attempts"] == 1 and meta["cost"] is not None and meta["cost"] < 0.01
    plan = make_plan(r["design"], intent, r["request"])
    probes, patterns, (pre, post), ok = EXPECT[name]
    assert [p["label"] for p in plan["probes"]] == probes
    assert [c["pattern"] for c in plan["trigger"]["conditions"]] == patterns
    assert (plan["window"]["requested"]["pre"], plan["window"]["requested"]["post"]) == (pre, post)
    assert (not plan["errors"]) == ok


def test_a_single_condition_is_always_and() -> None:
    r = REQ["t1_reuse_rise"]                      # the model wrote combine OR for one condition
    intent, _ = parse(r["request"], Path(r["design"]), client=Replay(FIX / "llm" / "t1_reuse_rise.json"))
    assert intent["trigger"]["combine"] == "OR"
    assert make_plan(r["design"], intent)["trigger"]["combine"] == "AND"


def test_the_brief_example_reports_why_it_cannot_be_built() -> None:
    r = REQ["brief_fifo_example"]
    intent, _ = parse(r["request"], Path(r["design"]), client=Replay(FIX / "llm" / "brief_fifo_example.json"))
    assert intent["unclear"]                                  # the parser said it found no FIFO overflow signal
    plan = make_plan(r["design"], intent, r["request"])
    assert any(e["what"] == "trigger" for e in plan["errors"])


def test_setup_stimulus_and_readback_are_parsed() -> None:
    r = REQ["t1_pwm_period"]
    intent, _ = parse(r["request"], Path(r["design"]), client=Replay(FIX / "llm" / "t1_pwm_period.json"))
    plan = make_plan(r["design"], intent)
    assert [(o["register"], o["value"]) for o in plan["setup"]] == [("COUNT", 0x8421), ("DUTY", 0x40)]
    assert [o["register"] for o in plan["readback"]] == ["DUTY", "COUNT"]


def test_a_bad_reply_is_asked_again_once_then_refused() -> None:
    good = json.loads((FIX / "llm" / "t1_count_write.json").read_text())[0]
    bad = {**good, "text": "Sure! Here is what I think the engineer wants."}
    intent, meta = parse(REQ["t1_count_write"]["request"], Path("designs/t1_dimmer_counter"), client=Replay([bad, good]))
    assert meta["attempts"] == 2 and intent["probes"] == ["count"]
    with pytest.raises(ValueError):
        parse("x", Path("designs/t1_dimmer_counter"), client=Replay([bad, bad]))


def test_unreported_cost_is_none_not_zero() -> None:
    good = json.loads((FIX / "llm" / "t1_count_write.json").read_text())[0]
    _, meta = parse("x", Path("designs/t1_dimmer_counter"), client=Replay([{**good, "cost": None}]))
    assert meta["cost"] is None


def test_extract_and_clean() -> None:
    assert extract_json('```json\n{"probes": ["a"]}\n```') == {"probes": ["a"]}
    assert extract_json('text {"probes": []} more') == {"probes": []}
    c = clean({"probes": ["a", ""], "trigger": {"combine": "and", "conditions": [{"signal": "x", "op": "rise", "value": None,
                                                                                    "extra": 1}]}, "foo": 1})
    assert c == {"probes": ["a"], "trigger": {"combine": "AND", "conditions": [{"signal": "x", "op": "rise"}]}}


def test_the_prompt_lists_signals_and_registers() -> None:
    d = Path("designs/t1_dimmer_counter")
    from debug_core.plan import register_map
    menu = signal_menu(RtlIndex.from_design(d), register_map(d))
    assert "u_dut.count (16 bits)" in menu and "COUNT 0x80" in menu and "win_wr (1 bits)" in menu
    assert "Do not invent" in SYSTEM


def test_the_parser_never_routes_to_forbidden_models() -> None:
    from agent.graph.llm import FORBIDDEN
    from debug_core.request import DEFAULT_MODEL
    assert not any(f in DEFAULT_MODEL for f in FORBIDDEN)
