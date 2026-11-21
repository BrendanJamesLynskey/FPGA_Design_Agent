"""Brief 108: one model configuration for every model call. Offline: no model, no network, no key."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import yaml

from agent.core.session import ROOT
from agent.models import PURPOSES, Resolver, build_table, claude_cli, legacy_layer
from agent.models import inventory as inv
from agent.models.config import ConfigError, Layer, Table, load_file

# ---- the gate: no model client and no claude argv outside agent/models ------------------------------------------------------

CLIENTS = {"OpenRouterClient", "AnthropicClient", "ClaudeCodeChat", "OpenAI", "Anthropic"}
CLAUDE_FLAGS = {"--system-prompt", "--output-format", "--setting-sources", "--permission-mode", "--no-session-persistence",
                "--disable-slash-commands"}
SDKS = {"openai", "anthropic"}


def scan_source(text: str, path: str) -> list[str]:
    """What in this source would be a model call that does not go through the resolver."""
    out = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name in CLIENTS:
                out.append(f"{path}:{n.lineno} constructs {name}")
            if name == "which" and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "claude":
                out.append(f"{path}:{n.lineno} looks up the claude binary")
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in SDKS:
                    out.append(f"{path}:{n.lineno} imports {a.name}")
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] in SDKS:
                out.append(f"{path}:{n.lineno} imports from {n.module}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in CLAUDE_FLAGS:
            out.append(f"{path}:{n.lineno} spells the claude flag {n.value}")
        elif isinstance(n, (ast.List, ast.Tuple)) and n.elts and isinstance(n.elts[0], ast.Constant) and n.elts[0].value == "claude" \
                and any(isinstance(e, ast.Constant) and e.value == "-p" for e in n.elts):
            out.append(f"{path}:{n.lineno} builds a claude -p argv")
    return out


def tracked_python() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "*.py"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("not a git checkout")
    return r.stdout.split()


def is_test(p: str) -> bool:
    return "/tests/" in p or Path(p).name.startswith("test_") or p.startswith("tests/") or Path(p).name == "conftest.py"


def test_gate_no_model_client_or_claude_argv_outside_the_resolver() -> None:
    bad = []
    for p in tracked_python():
        if p.startswith(inv.RESOLVER_FILES) or is_test(p):
            continue
        if not (ROOT / p).is_file():
            continue
        bad += scan_source((ROOT / p).read_text(errors="replace"), p)
    assert not bad, "model calls outside agent/models (route them through the resolver):\n" + "\n".join(bad)


def test_the_gate_catches_each_kind_of_bypass() -> None:
    src = ("import openai\nfrom anthropic import Anthropic\nimport subprocess, shutil\n"
           "c = OpenRouterClient('m')\nd = openai.OpenAI(api_key='x')\nshutil.which('claude')\n"
           "subprocess.run(['claude', '-p', 'hi', '--output-format', 'json'])\n")
    found = scan_source(src, "x.py")
    for what in ("imports openai", "imports from anthropic", "constructs OpenRouterClient", "constructs OpenAI", "looks up the claude binary",
                 "builds a claude -p argv", "spells the claude flag --output-format"):
        assert any(what in f for f in found), (what, found)
    assert scan_source("x = OpenRouterClient.__new__(OpenRouterClient)\n", "t.py") == []       # the tests' bare instance is not a call


def test_the_inventory_names_real_files_and_purposes() -> None:
    covered = set()
    for s in inv.SITES:
        f = ROOT / str(s["file"])
        assert f.is_file(), s
        text = f.read_text()
        ps = [p for p in s["purposes"] if p != "*"]
        assert not ps or s["needs"] == "agent" or any(p in text for p in ps), s
        covered |= set(ps)
    assert covered | set(inv.RESERVED) >= set(PURPOSES), set(PURPOSES) - covered - set(inv.RESERVED)
    assert set(inv.RESERVED) <= set(PURPOSES)


# ---- layers, options, guardrails ------------------------------------------------------------------------------------------

USER = {"endpoints": {"vllm": {"kind": "openai_compatible", "base_url": "http://localhost:8000/v1", "note": "vLLM, greedy, batch-invariant"}},
        "purposes": {"rtl": {"endpoint": "vllm", "model": "fine-tune-1", "options": {"temperature": 0, "seed": 7}}}}


def layer(name: str, data: dict) -> Layer:
    from agent.models.config import validate_layer
    return Layer(name, validate_layer(data, name, name), name)


def table(*layers: Layer, **kw) -> Table:
    return Table([Layer("builtin", {"endpoints": {}, "purposes": __import__("copy").deepcopy(
        __import__("agent.models.config", fromlist=["x"]).BUILTIN_PURPOSES)}), *layers], **kw)


def test_built_in_table_is_todays_behaviour() -> None:
    t = build_table(user_file=Path("/nonexistent"))
    for p in ("interpret", "model", "tests", "rtl", "oracle", "closure", "latency"):
        e = t.entry(p)
        assert (e.kind, e.model, e.options) == ("openrouter", "openai/gpt-6-luna", {"temperature": 0.2, "timeout_s": 180, "retries": 1})
    assert t.entry("spectest").kind == "claude_code" and t.entry("spectest").model == "claude-sonnet-5-5"
    assert t.entry("review").options == {"effort": "medium", "timeout_s": 900}
    assert t.entry("route").model is None and t.entry("constraints").model == t.entry("rtl").model       # inherits
    assert t.entry("doc").model == t.entry("rtl").model


def test_layers_stage_keys_and_inherit() -> None:
    u = layer("user", USER)
    p = layer("project", {"purposes": {"rtl": {"model": "fine-tune-2"}, "rtl@timing-closure": {"endpoint": "claude_code", "model": "claude-sonnet-5-5"}}})
    c = layer("cli", {"purposes": {"tests": {"model": "openai/other"}}})
    t = table(u, p, c)
    assert t.entry("rtl").model == "fine-tune-2" and t.entry("rtl").endpoint == "vllm"          # project over user; endpoint kept
    assert t.entry("rtl").options["seed"] == 7 and t.entry("rtl").note == "vLLM, greedy, batch-invariant"
    assert t.entry("rtl", "timing-closure").kind == "claude_code" and "seed" not in t.entry("rtl", "timing-closure").options
    assert t.entry("rtl", "synthesis").endpoint == "vllm"
    assert t.entry("constraints").model == "fine-tune-2"                                        # inherits rtl until set
    assert t.entry("tests").model == "openai/other" and t.entry("interpret").model == "openai/gpt-6-luna"
    assert t.entry("rtl").sources["model"] == "project" and t.entry("rtl").sources["endpoint"] == "user"


def test_default_applies_to_every_non_opt_in_purpose_and_all_on_the_subscription_is_valid() -> None:
    t = table(layer("cli", {"default": {"endpoint": "claude_code", "model": "claude-haiku-5-5"}}))
    for p, spec in PURPOSES.items():
        e = t.entry(p)
        if p in ("options", "proof"):     # briefs 104 and 125: opt-in, but each has its own built-in entry on the subscription (Sonnet), which a default does not move
            assert (e.kind, e.model) == ("claude_code", "claude-sonnet-5-5")
        elif spec.get("opt_in"):
            assert e.model is None
        elif p == "latency":              # its call sites need tool calls through a chat endpoint: the default skips it, so the table stays valid
            assert e.kind == "openrouter"
        else:
            assert (e.kind, e.model) == ("claude_code", "claude-haiku-5-5"), p
    with pytest.raises(ConfigError, match="tool calls"):                          # naming it explicitly is an error at load
        table(layer("cli", {"purposes": {"latency": {"endpoint": "claude_code", "model": "claude-haiku-5-5"}}}))


def test_an_unsupported_option_is_an_error_at_load_not_silently_ignored() -> None:
    with pytest.raises(ConfigError, match="not supported by endpoint kind 'claude_code'"):
        table(layer("user", {"purposes": {"rtl": {"endpoint": "claude_code", "model": "claude-haiku-5-5", "options": {"temperature": 0}}}}))
    with pytest.raises(ConfigError, match="not supported"):
        table(layer("user", {"purposes": {"rtl": {"endpoint": "anthropic_api", "model": "claude-haiku-5-5", "options": {"seed": 1}}}}))
    with pytest.raises(ConfigError, match="unknown option"):
        layer("user", {"purposes": {"rtl": {"options": {"top_p": 1}}}})
    # a built-in soft default (temperature 0.2) is dropped when the kind cannot take it, so switching kind is a one-line change
    t = table(layer("user", {"purposes": {"rtl": {"endpoint": "claude_code", "model": "claude-haiku-5-5"}}}))
    assert t.entry("rtl").options == {"effort": "medium"}


@pytest.mark.parametrize("data,msg", [
    ({"purposes": {"rtl": {"endpoint": "openrouter", "model": "anthropic/claude-opus-5-5"}}}, "OpenRouter"),
    ({"purposes": {"rtl": {"endpoint": "openrouter", "model": "some/fable-model"}}}, "OpenRouter"),
    ({"endpoints": {"or2": {"kind": "openai_compatible", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"}},
      "purposes": {"rtl": {"endpoint": "or2", "model": "x/opus-9"}}}, "OpenRouter"),
    ({"purposes": {"rtl": {"endpoint": "anthropic_api", "model": "claude-opus-5-5"}}}, "Opus"),
    ({"purposes": {"rtl": {"endpoint": "anthropic_api", "model": "claude-fable-5-1"}}}, "Fable"),
    ({"purposes": {"rtl": {"endpoint": "claude_code", "model": "claude-fable-5-1"}}}, "--allow-fable"),
    ({"purposes": {"rtl": {"endpoint": "claude_code", "model": "openai/gpt-6-luna"}}}, "Anthropic models only"),
])
def test_guardrails_hold_for_every_endpoint_kind(data: dict, msg: str) -> None:
    with pytest.raises(ConfigError, match=msg):
        table(layer("cli", data))


def test_fable_is_allowed_only_with_the_owners_flag_on_claude_code() -> None:
    data = {"purposes": {"rtl": {"endpoint": "claude_code", "model": "claude-fable-5-1"}}}
    assert table(layer("cli", data), allow_fable=True).entry("rtl").model == "claude-fable-5-1"
    with pytest.raises(ConfigError, match="allow_fable is not a file setting"):
        layer("project", {"allow_fable": True})
    with pytest.raises(ConfigError, match="--allow-fable"):
        table(layer("project", data))                                           # a project file cannot grant it


def test_keys_are_named_never_inlined() -> None:
    for bad in ({"api_key": "x"}, {"token": "x"}, {"key": "x"}, {"secret": "x"}):
        with pytest.raises(ConfigError, match="secret"):
            layer("user", {"endpoints": {"e": {"kind": "openai_compatible", "base_url": "http://x", **bad}}})
    with pytest.raises(ConfigError, match="environment variable NAME"):
        layer("user", {"endpoints": {"e": {"kind": "openai_compatible", "base_url": "http://x", "key_env": "sk-abcdefghijklmnop12345"}}})
    with pytest.raises(ConfigError, match="looks like a key"):
        layer("user", {"purposes": {"rtl": {"note": "sk-abcdefghijklmnopqrstu"}}})
    with pytest.raises(ConfigError, match="one line"):
        layer("user", {"purposes": {"rtl": {"note": "line one\nline two"}}})


def test_work_hardware_endpoints_are_refused_for_live_runs_and_a_project_file_cannot_lift_it() -> None:
    user = layer("user", {"endpoints": {"spark": {"kind": "openai_compatible", "base_url": "http://spark.work.lan:8000/v1", "key_env": "SPARK_KEY",
                                                 "host_class": "work_hardware"}},
                         "work_hardware_hosts": ["other.work.lan"]})
    use = layer("cli", {"purposes": {"closure": {"endpoint": "spark", "model": "local-1"}}})
    with pytest.raises(ConfigError, match="work hardware"):
        table(user, use)
    assert table(user, use, replay=True).entry("closure").model == "local-1"        # batch replay only: the call is served from a fixture
    # a project file cannot mark, unmark, or sidestep: host_class and work_hardware_hosts are user-file settings
    with pytest.raises(ConfigError, match="only be set in the user file"):
        layer("project", {"endpoints": {"spark": {"host_class": "lab"}}})
    with pytest.raises(ConfigError, match="only be set in the user file"):
        layer("project", {"work_hardware_hosts": []})
    proj = layer("project", {"endpoints": {"spark": {"base_url": "http://elsewhere/v1"}}})        # re-pointing is refused outright
    with pytest.raises(ConfigError, match="cannot redefine"):
        table(user, proj, use)
    same = layer("project", {"endpoints": {"spark2": {"kind": "openai_compatible", "base_url": "http://spark.work.lan.:8000/v1", "key_env": "SPARK_KEY"}},
                             "purposes": {"closure": {"endpoint": "spark2", "model": "local-1"}}})
    with pytest.raises(ConfigError, match="work hardware"):                           # the mark follows the host, trailing dot included
        table(user, same)
    alias = layer("project", {"endpoints": {"sneaky": {"kind": "openai_compatible", "base_url": "http://other.work.lan:9/v1", "key_env": "SPARK_KEY"}},
                              "purposes": {"closure": {"endpoint": "sneaky", "model": "local-1"}}})
    with pytest.raises(ConfigError, match="work hardware"):                           # a new name on a marked host is still refused
        table(user, alias)


def test_a_project_file_cannot_make_a_guardrail_weaker_by_any_route() -> None:
    """The guardrails run on the final table, whichever layer a value came from, so no layer order or key can skip them."""
    for name in ("user", "project", "cli"):
        with pytest.raises(ConfigError):
            table(layer(name, {"purposes": {"rtl": {"endpoint": "openrouter", "model": "anthropic/claude-opus-5-5"}}}))
    with pytest.raises(ConfigError, match="unknown top-level keys"):
        layer("project", {"guardrails": "off"})


def test_the_record_holds_no_key_and_no_prompt_and_has_a_stable_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-FAKEFAKEFAKEFAKE0123456789")
    t = table(layer("user", USER))
    rec = t.record()
    text = json.dumps(rec)
    assert "FAKEFAKE" not in text and "sk-" not in text
    assert rec["purposes"]["rtl"]["deployment_note"] == "vLLM, greedy, batch-invariant" and rec["purposes"]["rtl"]["endpoint"] == "vllm"
    assert t.hash == table(layer("user", USER)).hash != table().hash
    monkeypatch.setenv("ANTHROPIC_API_KEY", "abcd-1234-efgh-5678")
    bad = table(layer("user", {"purposes": {"rtl": {"note": "abcd-1234-efgh-5678"}}}))
    with pytest.raises(ConfigError, match="value of ANTHROPIC_API_KEY"):
        bad.record()


def test_user_and_project_files_load_from_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    uf, pf = tmp_path / "user.yaml", tmp_path / "models.yaml"
    uf.write_text(yaml.safe_dump(USER))
    pf.write_text(yaml.safe_dump({"purposes": {"tests": {"model": "openai/proj"}}}))
    t = build_table(user_file=uf, project_file=pf, cli={"purposes": {"model": {"model": "openai/cli"}}})
    assert t.entry("rtl").endpoint == "vllm" and t.entry("tests").model == "openai/proj" and t.entry("model").model == "openai/cli"
    rec = t.record()
    assert [x["layer"] for x in rec["layers"]] == ["user", "project", "cli"] and all(x["sha256"] for x in rec["layers"][:2])
    assert load_file(pf, "project").sha256 == rec["layers"][1]["sha256"]
    monkeypatch.setenv("FDA_MODELS_FILE", str(uf))
    assert build_table().entry("rtl").model == "fine-tune-1"


def test_legacy_flags_are_aliases_into_the_same_table() -> None:
    t = table(layer("cli", legacy_layer(harness="claude_code", cc_model="claude-sonnet-5-5", cc_effort="low", model="openai/x",
                                         spectest_model="claude-haiku-5-5", router_model="openai/r", oracle="claude_code")))
    for p in ("interpret", "model", "tests", "rtl"):
        assert (t.entry(p).kind, t.entry(p).model, t.entry(p).options) == ("claude_code", "claude-sonnet-5-5", {"effort": "low"})
    assert t.entry("closure").model == "openai/x" and t.entry("spectest").model == "claude-haiku-5-5"
    assert t.entry("route").model == "openai/r" and t.entry("oracle").kind == "claude_code"
    p = table(layer("cli", legacy_layer(profile="cvdp")))
    assert (p.entry("rtl").model, p.entry("rtl").options) == ("claude-opus-5-5", {}) and p.entry("model").model == "claude-sonnet-5-5"
    s = table(layer("cli", legacy_layer(roles={"rtl@timing-closure": {"harness": "claude_code", "model": "claude-fable-5-1"}})), allow_fable=True)
    assert s.entry("rtl", "timing-closure").model == "claude-fable-5-1" and s.entry("rtl").kind == "openrouter"


def test_rtl_in_the_constraints_stage_is_the_constraints_purpose() -> None:
    t = table(layer("cli", {"purposes": {"constraints": {"endpoint": "claude_code", "model": "claude-haiku-5-5"}}}))
    e = t.entry("rtl", "constraints")
    assert (e.purpose, e.kind, e.model) == ("constraints", "claude_code", "claude-haiku-5-5") and t.entry("rtl", "synthesis").kind == "openrouter"


# ---- the resolver ---------------------------------------------------------------------------------------------------------

def reply(text="ok", calls=None):
    from agent.graph.llm import Reply
    return Reply(text, calls or [], prompt_tokens=3, completion_tokens=2, cost=0.001)


def test_the_resolver_builds_the_client_of_the_endpoint_kind_and_logs_every_call_without_prompts(tmp_path: Path) -> None:
    made = []
    t = table(layer("user", USER))
    rs = Resolver(t, run_dir=tmp_path, factory=lambda e: made.append((e.purpose, e.kind, e.model)) or (lambda m, tools=None: reply("SECRET PROMPT ANSWER")))
    assert rs.chat("rtl")([{"role": "user", "content": "SECRET PROMPT"}]).text == "SECRET PROMPT ANSWER"
    rs.chat("interpret")([{"role": "user", "content": "hi"}])
    assert made == [("rtl", "openai_compatible", "fine-tune-1"), ("interpret", "openrouter", "openai/gpt-6-luna")]
    rows = [json.loads(x) for x in (tmp_path / "model_calls.jsonl").read_text().splitlines()]
    assert [r["purpose"] for r in rows] == ["rtl", "interpret"] and rows[0]["table_hash"] == t.hash and rows[0]["entry_hash"] == t.entry("rtl").hash
    assert rows[0]["endpoint"] == "vllm" and rows[0]["kind"] == "openai_compatible" and rows[0]["cost_usd"] == 0.001
    assert "SECRET" not in (tmp_path / "model_calls.jsonl").read_text()
    with pytest.raises(ConfigError, match="no model configured"):
        rs.chat("route")


def test_injected_replay_and_call_options(tmp_path: Path) -> None:
    fx = tmp_path / "fx.json"
    fx.write_text(json.dumps([reply("one").__dict__, reply("two").__dict__]))
    rs = Resolver(build_table(user_file=Path("/nonexistent")), replay=fx)
    a, b = rs.chat("interpret"), rs.chat("oracle")
    assert [a([]).text, b([]).text] == ["one", "two"]                       # one fixture, shared in order, as a replayed run needs
    assert Resolver(build_table(user_file=Path("/nonexistent")), injected=lambda m, tools=None: reply("inj")).chat("closure")([]).text == "inj"
    e = rs.entry("spectest", overrides={"effort": "low"})
    assert e.options["effort"] == "low" and e.hash != rs.entry("spectest").hash
    with pytest.raises(ConfigError, match="not supported"):
        rs.entry("spectest", overrides={"temperature": 1})
    assert Resolver(table(layer("cli", {"endpoints": {"r": {"kind": "replay", "path": str(fx)}}, "purposes": {"closure": {"endpoint": "r", "model": "recorded"}}}))
                    ).chat("closure")([]).text == "one"


def test_openai_compatible_sends_no_router_fields_and_the_options_it_was_given() -> None:
    from agent.models.endpoints import OpenRouterClient
    seen = {}

    class Chat:
        def create(self, **kw):
            seen.update(kw)
            return NS(usage=NS(prompt_tokens=1, completion_tokens=1, model_extra={}), choices=[NS(message=NS(content="x", tool_calls=[]))],
                      model_extra={}, provider=None)
    c = OpenRouterClient.__new__(OpenRouterClient)
    c.model, c._c, c.temperature, c.router, c.params = "m", NS(chat=NS(completions=Chat())), 0, False, {"seed": 7, "max_tokens": 64, "stop": ["\n"]}
    c([{"role": "user", "content": "hi"}], None)
    assert seen["temperature"] == 0 and seen["seed"] == 7 and seen["max_tokens"] == 64 and seen["stop"] == ["\n"] and "extra_body" not in seen
    c2 = OpenRouterClient.__new__(OpenRouterClient)
    c2.model, c2._c = "m", NS(chat=NS(completions=Chat()))          # the OpenRouter default: today's request, byte for byte
    seen.clear()
    c2([{"role": "user", "content": "hi"}], None)
    assert seen == {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0.2,
                    "extra_body": {"usage": {"include": True}, "provider": {"data_collection": "deny"}}}


def test_the_anthropic_client_translates_messages_tools_and_replies() -> None:
    from agent.models.endpoints import AnthropicClient
    sent = {}

    class Resp:
        def __init__(self, d): self.d = d
        def read(self): return json.dumps(self.d).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout):
        sent["body"], sent["headers"], sent["url"] = json.loads(req.data), dict(req.header_items()), req.full_url
        return Resp({"content": [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "t1", "name": "write_file", "input": {"p": 1}}],
                     "usage": {"input_tokens": 5, "output_tokens": 3}})
    c = AnthropicClient("claude-haiku-5-5", key_env="ANTHROPIC_API_KEY", opener=opener, temperature=0, max_tokens=100, stop=["END"])
    c._key = "k"
    tools = [{"type": "function", "function": {"name": "write_file", "description": "w", "parameters": {"type": "object", "properties": {"p": {}}}}}]
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t0", "type": "function", "function": {"name": "write_file", "arguments": "{\"p\": 0}"}}]},
            {"role": "tool", "tool_call_id": "t0", "content": "done"}]
    r = c(msgs, tools)
    b = sent["body"]
    assert sent["url"].endswith("/v1/messages") and b["system"] == "S" and b["stop_sequences"] == ["END"] and b["temperature"] == 0
    assert b["tools"][0]["input_schema"]["properties"] == {"p": {}}
    assert b["messages"][1]["content"][0] == {"type": "tool_use", "id": "t0", "name": "write_file", "input": {"p": 0}}
    assert b["messages"][2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "done"}]}
    assert (r.text, r.tool_calls, r.prompt_tokens, r.completion_tokens, r.cost) == ("hi", [{"id": "t1", "name": "write_file", "args": {"p": 1}}], 5, 3, None)


def test_a_claude_code_chat_takes_no_tools() -> None:
    from agent.models.endpoints import ClaudeCodeChat
    with pytest.raises(RuntimeError, match="cannot take tool calls"):
        ClaudeCodeChat("claude-haiku-5-5")([{"role": "user", "content": "x"}], [{"type": "function"}])


def test_agent_spec_is_the_legacy_role_view() -> None:
    rs = Resolver(table(layer("cli", legacy_layer(profile="cvdp"))))
    assert rs.agent_spec("rtl") == {"harness": "claude_code", "model": "claude-opus-5-5", "effort": None}
    assert rs.agent_spec("clarify")["model"] == "claude-sonnet-5-5"


# ---- one place builds the claude argv: byte-identical to the five spellings it replaced ----------------------------------

def test_claude_argv_is_byte_identical_to_the_old_spellings() -> None:
    # the sub-agent arm (arm.cli_argv before brief 108)
    arm_old = ["claude", "-p", "U", "--output-format", "stream-json", "--verbose", "--system-prompt", "S", "--tools", "",
               "--mcp-config", "/x/m.json", "--strict-mcp-config", "--allowedTools", "mcp__fda__a", "mcp__fda__b", "--permission-mode", "dontAsk",
               "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence", "--model", "M", "--effort", "high", "--max-turns", "9"]
    assert claude_cli.build_argv(system="S", prompt="U", model="M", output_format="stream-json", verbose=True, effort="high", max_turns=9,
                                 mcp_file="/x/m.json", allowed_tools=["mcp__fda__a", "mcp__fda__b"]) == arm_old
    # the oracle (no effort) and the spec tests / DOC step (effort when set)
    base = ["claude", "-p", "U", "--output-format", "json", "--system-prompt", "S", "--tools", "", "--strict-mcp-config", "--permission-mode", "dontAsk",
            "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence", "--model", "M"]
    assert claude_cli.build_argv(system="S", prompt="U", model="M") == [*base, "--max-turns", "1"]
    assert claude_cli.build_argv(system="S", prompt="U", model="M", effort="low") == [*base, "--effort", "low", "--max-turns", "1"]
    # the review judge: the prompt on stdin, no strict MCP flag, three turns
    assert claude_cli.build_argv(system="S", model="M", output_format="stream-json", verbose=True, effort="medium", max_turns=3, strict_mcp=False, exe="/b/claude") == [
        "/b/claude", "-p", "--output-format", "stream-json", "--verbose", "--system-prompt", "S", "--tools", "", "--permission-mode", "dontAsk",
        "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence", "--model", "M", "--effort", "medium", "--max-turns", "3"]


# ---- the CLI ---------------------------------------------------------------------------------------------------------------

def test_models_show_and_check(capsys: pytest.CaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent import __main__ as cli
    monkeypatch.setenv("FDA_MODELS_FILE", str(tmp_path / "none.yaml"))
    assert cli.main(["models", "show", "--model-config", json.dumps({"purposes": {"rtl": {"model": "openai/cli-model", "note": "from the cli"}}})]) == 0
    out = capsys.readouterr().out
    assert "openai/cli-model" in out and "cli]" in out and "table hash" in out
    assert cli.main(["models", "show", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["purposes"]["rtl"]["kind"] == "openrouter"
    assert cli.main(["models", "check"]) == 0 and "no endpoint was called" in capsys.readouterr().out
    assert cli.main(["models", "check", "--model-config", json.dumps({"purposes": {"rtl": {"model": "anthropic/claude-opus-5-5"}}})]) == 2
    assert "OpenRouter" in capsys.readouterr().err


def test_a_project_file_cannot_redirect_a_key_or_redefine_a_built_in_endpoint() -> None:
    with pytest.raises(ConfigError, match="cannot redefine"):
        table(layer("project", {"endpoints": {"openrouter": {"base_url": "https://evil.example/v1"}}}))
    with pytest.raises(ConfigError, match="key variable"):
        table(layer("project", {"endpoints": {"x": {"kind": "openai_compatible", "base_url": "https://evil.example/v1", "key_env": "GITHUB_TOKEN"}}}))
    ok = table(layer("project", {"endpoints": {"x": {"kind": "openai_compatible", "base_url": "http://localhost:9/v1"}}}))   # keyless local is fine
    assert ok.endpoints["x"]["kind"] == "openai_compatible"
    for bad in ("https://u:pw@h/v1", "h/v1", "https://h/v1?k=1"):
        with pytest.raises(ConfigError, match="base_url"):
            layer("user", {"endpoints": {"x": {"kind": "openai_compatible", "base_url": bad, "key_env": "X_KEY"}}})
    with pytest.raises(ConfigError, match="not allowed"):                    # Opus on the Anthropic host through the generic kind
        table(layer("cli", {"endpoints": {"a": {"kind": "openai_compatible", "base_url": "https://api.anthropic.com/v1/", "key_env": "ANTHROPIC_API_KEY"}},
                            "purposes": {"closure": {"endpoint": "a", "model": "claude-opus-5"}}}))


def test_model_config_json_merges_per_purpose_over_the_aliases() -> None:
    from agent.graph import run as gr
    cfg = gr.Config(spec_md=Path("s.md"), name="x", harness="claude_code", cc_model="claude-haiku-5-5",
                    model_config={"purposes": {"rtl": {"options": {"effort": "high"}}}})
    e = cfg.model_table().entry("rtl")
    assert (e.kind, e.model, e.options["effort"]) == ("claude_code", "claude-haiku-5-5", "high")


def test_one_recorder_per_fixture_is_shared_by_every_purpose(tmp_path: Path) -> None:
    rs = Resolver(build_table(user_file=Path("/nonexistent")), record=tmp_path / "r.json", factory=lambda e: (lambda m, t=None: reply("x")))
    a, b = rs.chat("interpret"), rs.chat("oracle")
    assert a._inner is b._inner
