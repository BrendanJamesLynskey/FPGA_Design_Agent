"""Brief 224: long replies on the anthropic_api endpoint: streaming, the larger output limit of the writing roles, the Designer writing file by file
and the stop reason of a stalled role. Recorded responses and fixtures only: no network, no key, no model."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.graph import run as gr
from agent.graph.llm import Meter
from agent.models import endpoints as E
from agent.models.config import ConfigError, build_table, validate_layer
from agent.tests.sse_fake import StreamResp

SONNET = {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10}
MSGS = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
TOOLS = [{"type": "function", "function": {"name": "write_file", "description": "w", "parameters": {"type": "object", "properties": {}}}}]
USAGE = {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 5000, "output_tokens": 700}


def make(responses, sent=None, **kw):
    """A client whose successive opens return ``responses`` (a StreamResp, or an exception to raise)."""
    it = iter(responses)

    def opener(req, timeout):
        if sent is not None:
            sent.append((json.loads(req.data), timeout))
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    c = E.AnthropicClient("claude-sonnet-5-5", key_env="ANTHROPIC_API_KEY", opener=opener, price=SONNET, **kw)
    c._key = "k"
    return c


def body(content, stop="end_turn", usage=None):
    return {"content": content, "usage": dict(usage or USAGE), "stop_reason": stop}


def test_the_request_is_streamed_and_the_reply_is_assembled_from_events() -> None:
    sent: list = []
    content = [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Writing the first file now."},
               {"type": "tool_use", "id": "t1", "name": "write_file", "input": {"path": "rtl/a.sv", "content": "module a; endmodule\n" * 40}},
               {"type": "tool_use", "id": "t2", "name": "write_file", "input": {"path": "rtl/b.sv", "content": "x"}}]
    r = make([StreamResp(body(content, "tool_use"))], sent, timeout_s=300)(MSGS, TOOLS)
    assert sent[0][0]["stream"] is True and sent[0][1] == 300
    assert r.text == "Writing the first file now." and r.stop_reason == "tool_use"
    assert [c["id"] for c in r.tool_calls] == ["t1", "t2"]
    assert r.tool_calls[0]["args"] == {"path": "rtl/a.sv", "content": "module a; endmodule\n" * 40}
    assert r.stream_retries == 0


def test_usage_and_cost_come_from_the_stream() -> None:
    r = make([StreamResp(body([{"type": "text", "text": "ok"}]))])(MSGS, TOOLS)
    assert (r.input_tokens, r.cache_write_tokens, r.cache_read_tokens, r.completion_tokens) == (10, 1000, 5000, 700)
    assert r.prompt_tokens == 6010
    assert r.cost == pytest.approx((10 * 2.0 + 700 * 10.0 + 1000 * 2.5 + 5000 * 0.1) / 1e6)
    m = Meter({"turns": 9, "seconds": 99, "usd": 3.0})
    m.add(r)
    assert m.run["usd"] == pytest.approx(r.cost) and m.split["output"] == 700 and m.split["cache_read"] == 5000


def test_a_dropped_stream_is_asked_for_again_once(capsys) -> None:
    good = body([{"type": "text", "text": "after the retry"}])
    c = make([StreamResp(good, drop_after=4), StreamResp(good)])
    r = c(MSGS, TOOLS)
    assert r.text == "after the retry" and r.stream_retries == 1 and c.stream_drops == 1
    assert "FDA_STREAM_DROPPED" in capsys.readouterr().err


def test_a_stream_that_drops_twice_is_an_error_never_a_reply() -> None:
    good = body([{"type": "text", "text": "partial"}])
    c = make([StreamResp(good, drop_after=3), StreamResp(good, drop_after=5)])
    with pytest.raises(RuntimeError, match="stream dropped"):
        c(MSGS, TOOLS)
    assert c.stream_drops == 2


def test_a_connection_error_mid_read_is_retried_then_an_error() -> None:
    import http.client
    good = body([{"type": "text", "text": "ok"}])
    assert make([http.client.IncompleteRead(b"x"), StreamResp(good)])(MSGS, TOOLS).text == "ok"
    with pytest.raises(RuntimeError, match="unreachable"):
        make([http.client.IncompleteRead(b"x"), ConnectionResetError()])(MSGS, TOOLS)


def test_an_overloaded_error_event_is_retried_and_another_error_is_not() -> None:
    good = body([{"type": "text", "text": "ok"}])
    over = {"type": "overloaded_error", "message": "busy"}
    assert make([StreamResp(good, error=over), StreamResp(good)])(MSGS, TOOLS).text == "ok"
    bad = {"type": "invalid_request_error", "message": "no"}
    c = make([StreamResp(good, error=bad), StreamResp(good)])
    with pytest.raises(RuntimeError, match="invalid_request_error"):
        c(MSGS, TOOLS)
    assert c.stream_drops == 1                                  # not asked for again


def test_a_call_cut_off_at_max_tokens_is_dropped_with_its_cost_and_a_note() -> None:
    cut = {"type": "tool_use", "id": "x", "name": "write_file", "raw_json": '{"path": "rtl/a.sv", "content": "module a; wire'}
    r = make([StreamResp(body([{"type": "text", "text": "partial"}, cut], "max_tokens", {"input_tokens": 3, "output_tokens": 32000}))],
             max_tokens=32000)(MSGS, TOOLS)
    assert r.stop_reason == "max_tokens" and r.tool_calls == [] and "output limit of 32000 tokens" in r.text and "one file per tool call" in r.text
    assert r.cost == pytest.approx((3 * 2 + 32000 * 10) / 1e6)


def test_a_complete_call_with_arguments_that_are_not_json_is_a_dropped_stream() -> None:
    broken = {"type": "tool_use", "id": "x", "name": "write_file", "raw_json": '{"path": '}
    with pytest.raises(RuntimeError, match="not complete JSON"):
        make([StreamResp(body([broken], "tool_use")), StreamResp(body([broken], "tool_use"))])(MSGS, TOOLS)


def test_the_writing_roles_get_the_larger_limit_and_an_explicit_option_wins() -> None:
    cli = {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}
    t = build_table(user_file=None, cli={"purposes": {p: cli for p in ("rtl", "tests", "interpret", "model")}})
    assert [t.entry(p).options["max_tokens"] for p in ("rtl", "tests", "interpret", "model")] == [32000, 32000, 16000, 16000]
    assert t.entry("rtl", "constraints").options["max_tokens"] == 32000
    o = build_table(user_file=None, cli={"purposes": {"rtl": {**cli, "options": {"max_tokens": 48000}}}}).entry("rtl").options
    assert o["max_tokens"] == 48000
    o = build_table(user_file=None, cli={"models": {"claude-sonnet-5-5": {"writing_max_tokens": 60000}}, "purposes": {"rtl": cli}}).entry("rtl").options
    assert o["max_tokens"] == 60000
    o = build_table(user_file=None, cli={"models": {"claude-sonnet-5-5": {"max_tokens": 9000}}, "purposes": {"rtl": cli}}).entry("rtl").options
    assert o["max_tokens"] == 9000                                # a layer that sets max_tokens alone means it for every purpose
    with pytest.raises(ConfigError):
        validate_layer({"models": {"m": {"writing_max_tokens": 0}}}, "cli", "t")


def test_the_client_built_for_the_designer_carries_the_limit(monkeypatch) -> None:
    from agent.models.resolver import Resolver
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-0000000000")                   # construction needs a key: a fake one, never sent
    t = build_table(user_file=None, cli={"purposes": {"rtl": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}})
    assert Resolver(t)._build(t.entry("rtl"), None).max_tokens == 32000


# --- the Designer writes file by file ---------------------------------------------------------------------------------

ARCH = """blocks:
  - name: top
  - name: core
  - name: fifo
  - name: jtag_bus
"""


def fake_rt(tmp_path: Path):
    d = tmp_path / "design"
    (d / "rtl").mkdir(parents=True)
    (d / "data").mkdir()
    (d / "data" / "jtag_bus.sv").write_text("module jtag_bus; endmodule\n")
    (d / "architecture.yaml").write_text(ARCH)
    return SimpleNamespace(design=d, meter=Meter({"turns": 99, "seconds": 999, "usd": 99.0}), cut_streak={}, budget_notes=[])


def scripted(monkeypatch, rt, script):
    """Replace run_role by a script: each call is (files to write, whether the reply was cut off); the prompts are kept."""
    calls: list[str] = []

    def fake(rt_, role, prompt, allowed=(), repair=False):
        calls.append(prompt)
        files, cut = script[len(calls) - 1]
        for name, text in files.items():
            (rt.design / "rtl" / name).write_text(text)
        rt.meter.truncated += 1 if cut else 0
    monkeypatch.setattr(gr, "run_role", fake)
    return calls


def test_after_a_cut_off_the_files_on_disk_stay_and_the_note_says_what_is_missing(monkeypatch, tmp_path) -> None:
    rt = fake_rt(tmp_path)
    calls = scripted(monkeypatch, rt, [({"fifo.sv": "module fifo; endmodule\n"}, True),
                                       ({"core.sv": "module core; endmodule\n"}, True),
                                       ({"top.sv": "module top; endmodule\n"}, False)])
    gr.run_writing_role(rt, "rtl", "P", (), False)
    assert len(calls) == 3
    assert "fifo.sv" in calls[1] and "Blocks of architecture.yaml with no module written yet: top, core" in calls[1]
    assert "Files in rtl/ now: core.sv, fifo.sv" in calls[2] and "no module written yet: top." in calls[2]
    assert sorted(p.name for p in (rt.design / "rtl").iterdir()) == ["core.sv", "fifo.sv", "top.sv"]
    assert rt.cut_streak["rtl"] == 0 and gr.files_status(rt.design)[1] == []


def test_the_continuation_stops_when_every_block_has_a_module(monkeypatch, tmp_path) -> None:
    rt = fake_rt(tmp_path)
    calls = scripted(monkeypatch, rt, [({"a.sv": "module top; endmodule\nmodule core; endmodule\nmodule fifo; endmodule\n"}, True), ({}, False)])
    gr.run_writing_role(rt, "rtl", "P", (), False)
    assert len(calls) == 1


def test_two_cut_replies_with_no_file_written_raise_the_stall(monkeypatch, tmp_path) -> None:
    rt = fake_rt(tmp_path)
    calls = scripted(monkeypatch, rt, [({}, True), ({}, True), ({"a.sv": "module top;"}, False)])
    with pytest.raises(gr.ReplyTooLong, match="rtl"):
        gr.run_writing_role(rt, "rtl", "P", (), False)
    assert len(calls) == 2 and rt.cut_streak["rtl"] == 2
    assert "cut off at the output limit" in calls[1] and "Files in rtl/ now: none" in calls[1]


def test_the_streak_counts_across_visits_and_a_written_file_resets_it(monkeypatch, tmp_path) -> None:
    rt = fake_rt(tmp_path)
    scripted(monkeypatch, rt, [({}, True)] * 4)
    gr.RTL_CONTINUATIONS = 0
    try:
        gr.run_writing_role(rt, "rtl", "P", (), False)                           # visit 1: one cut, nothing written
        assert rt.cut_streak["rtl"] == 1
        with pytest.raises(gr.ReplyTooLong):
            gr.run_writing_role(rt, "rtl", "P", (), False)                       # visit 2: the second in a row
    finally:
        gr.RTL_CONTINUATIONS = 3
    rt2 = fake_rt(tmp_path / "b")
    scripted(monkeypatch, rt2, [({}, True), ({"a.sv": "module top;"}, True), ({}, True)])
    gr.RTL_CONTINUATIONS = 0
    try:
        for _ in range(3):
            gr.run_writing_role(rt2, "rtl", "P", (), False)
    finally:
        gr.RTL_CONTINUATIONS = 3
    assert rt2.cut_streak["rtl"] == 1                                            # cut, write (reset), cut: never two in a row without a file


def test_a_role_that_is_not_the_designer_gets_one_call_and_the_same_stall_rule(monkeypatch, tmp_path) -> None:
    rt = fake_rt(tmp_path)
    calls = scripted(monkeypatch, rt, [({}, True)])
    gr.run_writing_role(rt, "tests", "P", (), False)
    assert len(calls) == 1 and rt.cut_streak["tests"] == 1


def test_the_designers_request_names_one_file_per_call() -> None:
    assert "one file per write_file call" in gr.FILE_BY_FILE_NOTE and gr.MAX_REPLY_CUTS == 2
