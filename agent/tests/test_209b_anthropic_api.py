"""Brief 209b: the anthropic_api endpoint as a first-class endpoint: cost from usage, prompt caching markers, the per-model
temperature rule and budget scaling. Recorded responses only: no network, no key."""
from __future__ import annotations

import json

import pytest

from agent.graph.llm import BudgetExceeded, Meter, Reply
from agent.models import endpoints as E
from agent.models.config import ConfigError, Layer, Table, build_table, validate_layer

SONNET = {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10}


class Resp:
    def __init__(self, d):
        self.d = d

    def read(self):
        return json.dumps(self.d).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def client(usage, sent=None, **kw):
    def opener(req, timeout):
        if sent is not None:
            sent.append(json.loads(req.data))
        return Resp({"content": [{"type": "text", "text": "ok"}], "usage": usage})
    c = E.AnthropicClient(kw.pop("model", "claude-sonnet-5-5"), key_env="ANTHROPIC_API_KEY", opener=opener, **kw)
    c._key = "k"
    return c


MSGS = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {"name": "t", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "a", "content": "R1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "b", "type": "function", "function": {"name": "t", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "b", "content": "R2"}]
TOOLS = [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}},
         {"type": "function", "function": {"name": "u", "description": "d", "parameters": {"type": "object", "properties": {}}}}]


def test_cost_comes_from_usage_with_all_four_fields() -> None:
    u = {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 20000, "cache_read_input_tokens": 100000}
    # 1000*2 + 500*10 + 20000*2.5 + 100000*0.1 = 2000 + 5000 + 50000 + 10000 = 67000 micro-USD
    assert E.usage_cost(u, SONNET) == pytest.approx(0.067)
    r = client(u, price=SONNET)(MSGS, TOOLS)
    assert r.cost == pytest.approx(0.067) and r.cost_basis == "usage*price"
    assert (r.input_tokens, r.completion_tokens, r.cache_write_tokens, r.cache_read_tokens) == (1000, 500, 20000, 100000)
    assert r.prompt_tokens == 121000                      # all three input fields


def test_a_price_without_cache_prices_derives_them_from_input() -> None:
    u = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000}
    assert E.usage_cost(u, {"input": 0.10, "output": 0.50}) == pytest.approx(0.10 + 0.125 + 0.01)


def test_no_price_keeps_the_ceiling_and_warns_once(capsys) -> None:
    E._WARNED_NO_PRICE.clear()
    c = client({"input_tokens": 10, "output_tokens": 5}, model="claude-unpriced-9")
    r1, r2 = c(MSGS, TOOLS), c(MSGS, TOOLS)
    assert r1.cost is None and r2.cost is None and r1.cost_basis is None
    assert capsys.readouterr().err.count("FDA_NO_PRICE") == 1
    m = Meter({"turns": 9, "seconds": 99, "usd": 3.0})
    m.add(r1)
    assert m.run["usd"] == 0.05 and m.unreported == 1       # today's ceiling


def test_the_meter_charges_the_computed_cost_not_the_ceiling() -> None:
    m = Meter({"turns": 9, "seconds": 99, "usd": 3.0})
    m.add(Reply("t", [], cost=0.0123, input_tokens=4, cache_read_tokens=6, prompt_tokens=10, completion_tokens=2))
    assert m.run["usd"] == 0.0123 and m.unreported == 0
    assert m.split == {"input": 4, "output": 2, "cache_write": 0, "cache_read": 6}


def test_cache_markers_cover_tools_system_and_the_conversation() -> None:
    sent: list = []
    client({"input_tokens": 1, "output_tokens": 1}, sent)(MSGS, TOOLS)
    b = sent[0]
    cc = {"type": "ephemeral"}
    assert b["system"] == [{"type": "text", "text": "SYS", "cache_control": cc}]
    assert "cache_control" not in b["tools"][0] and b["tools"][-1]["cache_control"] == cc
    msgs = b["messages"]
    assert msgs[-1]["content"][-1]["cache_control"] == cc                 # the conversation so far
    assert msgs[-3]["content"][-1]["cache_control"] == cc                 # where the previous call wrote its entry
    assert "cache_control" not in json.dumps(msgs[:-3] + [msgs[-2]])
    assert json.dumps(b).count("cache_control") <= 4                      # the API limit


def test_cache_off_sends_the_plain_shape() -> None:
    sent: list = []
    client({"input_tokens": 1, "output_tokens": 1}, sent, cache=False)(MSGS, TOOLS)
    assert sent[0]["system"] == "SYS" and "cache_control" not in json.dumps(sent[0])


def test_the_markers_leave_the_callers_messages_untouched() -> None:
    before = json.dumps(MSGS)
    client({"input_tokens": 1, "output_tokens": 1})(MSGS, TOOLS)
    assert json.dumps(MSGS) == before


def test_temperature_is_omitted_by_the_model_rule_and_kept_where_accepted() -> None:
    sent: list = []
    client({"input_tokens": 1, "output_tokens": 1}, sent, temperature=0.2, accepts_temperature=False)(MSGS, TOOLS)
    client({"input_tokens": 1, "output_tokens": 1}, sent, model="claude-sonnet-4-6", temperature=0.2, accepts_temperature=True)(MSGS, TOOLS)
    assert "temperature" not in sent[0] and sent[1]["temperature"] == 0.2


def test_the_config_rules_and_the_resolver_wire_them() -> None:
    t = build_table(user_file=None)
    assert t.model_rule("claude-sonnet-5-5") == {"price": SONNET, "temperature": False, "matched": "claude-sonnet-5-5",
                                                 "max_tokens": 16000, "effort": "medium", "timeout_s": 300}
    assert t.model_rule("claude-haiku-5-5")["price"] == {"input": 0.10, "output": 0.50}
    assert t.model_rule("claude-sonnet-4-6")["temperature"] is True and t.model_rule("claude-sonnet-4-6")["price"] is None
    assert t.model_rule("claude-unknown-1")["temperature"] is False and t.model_rule("openai/x")["price"] is None
    cli = {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}
    t2 = build_table(user_file=None, cli={"purposes": {"rtl": cli}})
    assert "temperature" not in t2.entry("rtl").options                 # the soft default is not sent to a model that rejects it
    t3 = build_table(user_file=None, cli={"purposes": {"rtl": {**cli, "model": "claude-sonnet-4-6"}}})
    assert t3.entry("rtl").options["temperature"] == 0.2
    from agent.models.resolver import Resolver
    rs = Resolver(t2)
    import os                                                           # construction needs a key: a fake one, never sent
    os.environ["ANTHROPIC_API_KEY"] = "sk-test-0000000000"
    try:
        c = rs._build(t2.entry("rtl"), None)
        assert (c.max_tokens, c.effort, c.timeout_s) == (16000, "medium", 300)
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    assert c.price == SONNET and c.accepts_temperature is False


def test_models_section_overrides_price_and_is_validated() -> None:
    t = build_table(user_file=None, cli={"models": {"claude-sonnet-5-5": {"price": {"input": 3, "output": 15}}, "claude-new-1": {"price": {"input": 1, "output": 2}}}})
    assert t.model_rule("claude-sonnet-5-5")["price"] == {**SONNET, "input": 3, "output": 15}
    assert t.model_rule("claude-new-1-x")["price"] == {"input": 1, "output": 2}
    for bad in ({"models": {"m": {"price": {"input": 1}}}}, {"models": {"m": {"price": {"input": -1, "output": 1}}}},
                {"models": {"m": {"cost": 1}}}, {"budget_scale": 0}, {"budget_scale": "2"}):
        with pytest.raises(ConfigError):
            validate_layer(bad, "cli", "t")


def test_budget_scale_multiplies_stage_usd_and_the_run_cap() -> None:
    assert build_table(user_file=None).budget_scale == 1.0
    assert build_table(user_file=None, cli={"budget_scale": 4}).budget_scale == 4.0
    m = Meter({"turns": 300, "seconds": 9999, "usd": 12.0}, usd_scale=4.0)
    m.start_stage({"turns": 30, "seconds": 1800, "usd": 0.40})
    assert m.stage_limits == {"turns": 30, "seconds": 1800, "usd": 1.6}
    m.add(Reply("t", [], cost=1.7))
    with pytest.raises(BudgetExceeded, match="stage usd"):
        m.check()
    m1 = Meter({"turns": 300, "seconds": 9999, "usd": 3.0})
    m1.start_stage({"turns": 30, "seconds": 1800, "usd": 0.40})
    assert m1.stage_limits["usd"] == 0.40                               # the default model's budgets are unchanged


def test_the_run_summary_and_config_record_the_scale(tmp_path) -> None:
    from agent.graph.run import Config
    cfg = Config(spec_md=tmp_path / "s.md", name="x", model_config={"budget_scale": 3})
    assert cfg.model_table().budget_scale == 3.0
    assert "budget_scale" in cfg.model_table().record()
    assert "budget_scale" not in build_table(user_file=None).record()


def test_model_calls_rows_hold_all_four_token_fields(tmp_path) -> None:
    from agent.models.resolver import Resolver
    t = build_table(user_file=None, cli={"purposes": {"rtl": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}})
    rs = Resolver(t, run_dir=tmp_path)
    r = Reply("t", [], prompt_tokens=30, completion_tokens=2, cost=0.01, input_tokens=5, cache_write_tokens=10, cache_read_tokens=15, cost_basis="usage*price")
    rs.log_call(t.entry("rtl"), r, 0.5)
    row = json.loads((tmp_path / "model_calls.jsonl").read_text())
    assert (row["input_tokens"], row["completion_tokens"], row["cache_write_tokens"], row["cache_read_tokens"], row["cost_usd"]) == (5, 2, 10, 15, 0.01)


def test_the_run_limit_wins_when_stage_and_run_limits_are_both_exceeded() -> None:
    m = Meter({"turns": 300, "seconds": 9999, "usd": 0.5})
    m.start_stage({"turns": 30, "seconds": 1800, "usd": 0.4})
    m.add(Reply("t", [], cost=0.6))
    with pytest.raises(BudgetExceeded) as e:
        m.check()
    assert str(e.value).startswith("run ")              # node_work re-raises only a "run ..." stop; a "stage ..." one starts the next visit


def test_effort_and_max_tokens_follow_the_model_and_an_explicit_option_wins() -> None:
    cli = {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}
    o = build_table(user_file=None, cli={"purposes": {"rtl": cli}}).entry("rtl").options
    assert (o["max_tokens"], o["effort"], o["timeout_s"]) == (16000, "medium", 300)
    o2 = build_table(user_file=None, cli={"purposes": {"rtl": {**cli, "options": {"max_tokens": 4000, "effort": "high"}}}}).entry("rtl").options
    assert (o2["max_tokens"], o2["effort"]) == (4000, "high")
    o3 = build_table(user_file=None, cli={"models": {"claude-sonnet-5-5": {"max_tokens": 9000, "effort": "low"}}, "purposes": {"rtl": cli}}).entry("rtl").options
    assert (o3["max_tokens"], o3["effort"]) == (9000, "low")
    o4 = build_table(user_file=None, cli={"purposes": {"rtl": {**cli, "model": "claude-haiku-5-5"}}}).entry("rtl").options
    assert o4["max_tokens"] == 8192 and "effort" not in o4            # a model with no rule keeps the kind's defaults
    for bad in ({"models": {"m": {"effort": "huge"}}}, {"models": {"m": {"max_tokens": 0}}}, {"models": {"m": {"timeout_s": -1}}}):
        with pytest.raises(ConfigError):
            validate_layer(bad, "cli", "t")


def test_the_request_carries_output_config_effort_and_no_thinking_budget() -> None:
    sent: list = []
    client({"input_tokens": 1, "output_tokens": 1}, sent, effort="medium", max_tokens=16000)(MSGS, TOOLS)
    assert sent[0]["output_config"] == {"effort": "medium"} and sent[0]["max_tokens"] == 16000 and "thinking" not in sent[0]
    sent.clear()
    client({"input_tokens": 1, "output_tokens": 1}, sent)(MSGS, TOOLS)
    assert "output_config" not in sent[0]


def _truncated(usage, content):
    def opener(req, timeout):
        return Resp({"content": content, "usage": usage, "stop_reason": "max_tokens"})
    c = E.AnthropicClient("claude-sonnet-5-5", key_env="ANTHROPIC_API_KEY", opener=opener, price=SONNET, max_tokens=16000)
    c._key = "k"
    return c


def test_a_reply_cut_off_at_max_tokens_is_recorded_and_hands_the_role_a_note(tmp_path, capsys) -> None:
    c = _truncated({"input_tokens": 3, "output_tokens": 16000},
                   [{"type": "text", "text": "partial"}, {"type": "tool_use", "id": "x", "name": "write_file", "input": {"p": "half"}}])
    r = c(MSGS, TOOLS)
    assert r.stop_reason == "max_tokens" and r.tool_calls == []             # the cut-off call has incomplete arguments: dropped
    assert "cut off at the output limit of 16000 tokens" in r.text and r.text.startswith("partial")
    assert r.cost == pytest.approx((3 * 2 + 16000 * 10) / 1e6)             # the truncated call is still paid for, and charged
    assert "FDA_TRUNCATED" in capsys.readouterr().err
    m = Meter({"turns": 9, "seconds": 99, "usd": 3.0})
    m.add(r)
    assert m.truncated == 1
    from agent.models.resolver import Resolver
    t = build_table(user_file=None, cli={"purposes": {"rtl": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}})
    Resolver(t, run_dir=tmp_path).log_call(t.entry("rtl"), r, 1.0)
    assert json.loads((tmp_path / "model_calls.jsonl").read_text())["stop_reason"] == "max_tokens"


def test_a_normal_reply_keeps_its_tool_calls_and_stop_reason() -> None:
    def opener(req, timeout):
        return Resp({"content": [{"type": "tool_use", "id": "x", "name": "t", "input": {"a": 1}}], "usage": {"input_tokens": 1, "output_tokens": 1}, "stop_reason": "tool_use"})
    c = E.AnthropicClient("claude-sonnet-5-5", key_env="ANTHROPIC_API_KEY", opener=opener, price=SONNET)
    c._key = "k"
    r = c(MSGS, TOOLS)
    assert r.stop_reason == "tool_use" and r.tool_calls == [{"id": "x", "name": "t", "args": {"a": 1}}] and "cut off" not in r.text
