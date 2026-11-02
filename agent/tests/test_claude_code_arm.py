"""The Claude Code arm (05c), offline: no CLI call, no model. The equivalence test builds the same sub-agent turn for
both harnesses and compares what each would be given: system prompt, tool list, limits."""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from agent.claude_code_arm import arm
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.graph import run as gr
from agent.graph.stages import MACHINE

T1 = ROOT / "designs" / "t1_dimmer_counter"

STREAM = [
    {"type": "system", "subtype": "init", "tools": ["mcp__fda__read_file"], "mcp_servers": [{"name": "fda", "status": "connected"}],
     "slash_commands": [], "skills": [], "plugins": [], "agents": [], "model": "claude-haiku-5-5", "claude_code_version": "2.1.316"},
    {"type": "assistant", "message": {"model": "claude-haiku-5-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": 5,
                                                                            "output_tokens": 3},
                                      "content": [{"type": "tool_use", "id": "t1", "name": "mcp__fda__read_file",
                                                   "input": {"path": "spec.yaml"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": False,
                                              "content": [{"type": "text", "text": "name: x"}]}]}},
    {"type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "total_cost_usd": 0.0123, "result": "DONE"},
]


class Runner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, "ok", "", 0.0)


@pytest.fixture
def rt(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", harness="claude_code", cc_model="claude-haiku-5-5")
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=Runner())
    (r.design / "spec.yaml").write_text("name: x\n")
    yield r
    import shutil
    shutil.rmtree(runs, ignore_errors=True)


def _enter(rt, n):
    rt.meter.start_stage(MACHINE[n].limits)
    rt.session.stage = MACHINE[n].name


CASES = [(0, "clarify", ("search_docs", "load_skill")), (2, "model", ()), (2, "tests", ("search_docs", "load_skill")),
         (2, "rtl", MACHINE[2].tools), (4, "rtl", MACHINE[4].tools), (9, "rtl", tuple(t for t in MACHINE[9].tools if t not in ("program", "bringup")))]


@pytest.mark.parametrize("n,role,allowed", CASES)
def test_same_prompt_tools_and_limits_as_deep_agents(rt, monkeypatch, n, role, allowed):
    import deepagents
    _enter(rt, n)
    seen = {}

    class Stub:
        def invoke(self, *a, **k):
            return {"files": {}}

    def fake_create(**kw):
        seen.update(kw)
        return Stub()
    monkeypatch.setattr(deepagents, "create_deep_agent", fake_create)
    monkeypatch.setattr(gr, "chat_model", lambda *a, **k: object())
    rt.cfg.harness = "deepagents"
    gr.run_subagent(rt, role, "PROMPT {x}".replace("{x}", role), allowed)
    da_tools = {t.name.removeprefix("fda_") for t in seen["tools"]}

    plan = gr.subagent_plan(rt, role, "PROMPT " + role, allowed)
    mcp = arm.mcp_config(rt, plan)["mcpServers"]["fda"]["args"]
    exposed = set(mcp[mcp.index("--tools") + 1].split(","))
    argv = arm.cli_argv(rt, plan, Path("/x/mcp.json"), "claude-haiku-5-5", "medium", int(plan["limits"]["turns"]))
    # 1. the system prompt passed to the CLI is the one Deep Agents got (replacing Claude Code's default)
    assert argv[argv.index("--system-prompt") + 1] == seen["system_prompt"]
    # 2. the first user message carries the same prompt and the same input files
    assert argv[2].startswith("PROMPT " + role) and plan["user_message"] == argv[2]
    # 3. the tools: every core tool Deep Agents had is exposed (the arm adds the file tools Deep Agents has built in)
    assert da_tools <= exposed and exposed - da_tools <= set(gr.FILE_TOOLS)
    assert set(plan["core_tools"]) == da_tools
    allowed_ids = argv[argv.index("--allowedTools") + 1:argv.index("--permission-mode")]
    assert set(allowed_ids) == {f"mcp__fda__{t}" for t in exposed}
    # 4. no built-in tool, only our MCP server, no settings, no skills
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv
    assert argv[argv.index("--setting-sources") + 1] == "" and "--disable-slash-commands" in argv
    # 5. the limits: --max-turns is the stage's turn limit
    assert argv[argv.index("--max-turns") + 1] == str(int(MACHINE[n].limits["turns"]))
    assert "WebFetch" not in " ".join(argv) and "Bash" not in " ".join(argv)


def test_no_hardware_or_stage_move_tool_is_ever_exposed(rt):
    for n, role, allowed in CASES:
        _enter(rt, n)
        plan = gr.subagent_plan(rt, role, "p", allowed)
        assert not {"program", "bringup", "stage_note"} & (set(plan["core_tools"]) | set(plan["file_tools"]))


def test_role_jail_on_the_mcp_server_command(rt):
    _enter(rt, 2)
    plan = gr.subagent_plan(rt, "model", "p", ())
    a = arm.mcp_config(rt, plan)["mcpServers"]["fda"]["args"]
    assert a[a.index("--role") + 1] == "model" and a[a.index("--tools") + 1] == "read_file,write_file"


def test_isolated_env_carries_only_path_home_and_the_token(tmp_path):
    env = arm.isolated_env(tmp_path, "tok")
    assert env["HOME"] == str(tmp_path) and env["CLAUDE_CONFIG_DIR"].startswith(str(tmp_path))
    assert set(env) <= {"PATH", "HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN", "DISABLE_AUTOUPDATER",
                        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "LANG"}
    assert "ANTHROPIC_API_KEY" not in env and "OPENROUTER_API_KEY" not in env and "ANTHROPIC_BASE_URL" not in env


def test_stream_becomes_the_shared_trace_with_unreported_cost(tmp_path):
    from agent.core.trace import Trace
    t = Trace(tmp_path / "t.jsonl", harness="claude_code")
    info = arm.parse_stream([json.dumps(e) for e in STREAM], t, "clarify")
    kinds = [r["kind"] for r in t.records]
    assert kinds == ["model", "tool"]
    assert t.records[0]["cost_usd"] == "unreported" and t.records[0]["tokens"] == {"input": 15, "output": 3}
    assert t.records[1]["tool"] == "read_file" and t.records[1]["result"]["ok"] is True
    assert info["result"]["total_cost_usd"] == 0.0123 and info["served_models"] == ["claude-haiku-5-5"]
    assert arm.init_report(info["init"])["mcp_servers"][0]["name"] == "fda"


def test_run_subagent_cc_end_to_end_with_a_fake_cli(rt, monkeypatch, tmp_path):
    _enter(rt, 0)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-token")
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))
        if argv[1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "2.1.316 (Claude Code)\n", "")
        (rt.design / "spec.yaml").write_text("name: y\n")
        return subprocess.CompletedProcess(argv, 0, "\n".join(json.dumps(e) for e in STREAM), "")
    monkeypatch.setattr(arm.subprocess, "run", fake_run)
    monkeypatch.setattr(arm.shutil, "which", lambda n: "/bin/claude")
    gr.run_subagent(rt, "clarify", "P", ("search_docs", "load_skill"))
    argv, kw = calls[-1]
    assert kw["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "fake-token" and not str(kw["cwd"]).startswith(str(ROOT))
    rec = json.loads((rt.run_dir / "claude_code_calls.jsonl").read_text().splitlines()[0])
    assert rec["cost_usd"] == "unreported" and rec["plan_cost_estimate_usd"] == 0.0123
    assert rec["claude_code_version"].startswith("2.1.316") and rec["models_served"] == ["claude-haiku-5-5"]
    assert rt.meter.stage["turns"] == 2 and rt.meter.run["usd"] == 0.0
    assert (rt.run_dir / "trace.jsonl").is_file()


def test_missing_token_blocks_with_the_owner_step(rt, monkeypatch):
    _enter(rt, 0)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(arm, "TOKEN_FILE", Path("/nonexistent/claude_code_oauth.env"))
    monkeypatch.setattr(arm.shutil, "which", lambda n: "/bin/claude")
    monkeypatch.setattr(arm.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "2.1.316\n", ""))
    out = gr.node_work({"run_id": rt.run_id, "stage": 0})
    assert out["stop"].startswith("claude_code blocked") and "setup-token" in out["stop"]


def test_pinned_version_is_enforced(rt, monkeypatch):
    _enter(rt, 0)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(arm.shutil, "which", lambda n: "/bin/claude")
    monkeypatch.setattr(arm.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "9.9.9\n", ""))
    with pytest.raises(gr.ArmBlocked):
        arm.run_subagent_cc(rt, gr.subagent_plan(rt, "clarify", "p", ()))


def test_summary_reports_claude_code_model_and_plan_cost(tmp_path):
    """05c: a claude_code run's summary names the CLI model (not the oracle/interview model) and the plan estimate."""
    import json
    from types import SimpleNamespace as NS
    from agent.graph import run as R
    (tmp_path / "claude_code_calls.jsonl").write_text(
        json.dumps({"claude_code_version": "2.1.316 (Claude Code)", "plan_cost_estimate_usd": 0.25}) + "\n"
        + json.dumps({"claude_code_version": "2.1.316 (Claude Code)", "plan_cost_estimate_usd": 0.5}) + "\n")
    rt = NS(run_id="r", run_dir=tmp_path, cfg=NS(name="d", model="openai/oracle", cc_model="claude-haiku-5-5",
            harness="claude_code", interview="oracle", review="off"),
            meter=NS(run={"tokens": 1, "usd": 0.0, "turns": 2, "seconds": 3.0}, unreported=1))
    s = R.summary(rt, {"history": []})
    assert s["model"] == "claude-haiku-5-5" and s["oracle_model"] == "openai/oracle"
    assert s["plan_cost_estimate_usd"] == 0.75 and s["claude_code_version"].startswith("2.1.316")


def test_real_recorded_stream_is_parsed_once_per_message(tmp_path):
    """05c: a REAL claude 2.1.316 stream (Haiku, clarify turn; ids, cwd and thinking redacted). One API message is
    split over several assistant events with the same id and usage; each is counted once, and the run total comes
    from the result event."""
    from pathlib import Path
    from agent.core.trace import Trace
    lines = (Path(__file__).parent / "fixtures" / "cc_real_stream_haiku_clarify.jsonl").read_text().splitlines()
    t = Trace(tmp_path / "t.jsonl", harness="claude_code")
    info = arm.parse_stream(lines, t, "clarify")
    msgs = {json.loads(x)["message"]["id"] for x in lines if json.loads(x).get("type") == "assistant"}
    assert len([r for r in t.records if r["kind"] == "model"]) == len(msgs)
    assert all(r["cost_usd"] == "unreported" for r in t.records if r["kind"] == "model")
    ru = info["result"]["usage"]
    assert info["tokens"]["output"] == ru["output_tokens"] and info["tokens"]["input"] >= ru["input_tokens"]
    assert info["served_models"] == ["claude-haiku-5-5"] and info["result"]["subtype"] == "success"
    rep = arm.init_report(info["init"])
    assert rep["tools"] == ["mcp__fda__list_files", "mcp__fda__read_file", "mcp__fda__write_file"]
    assert [m["name"] for m in rep["mcp_servers"]] == ["fda"] and rep["skills"] == [] and rep["slash_commands"] == []
    assert rep["apiKeySource"] == "none" and rep["permissionMode"] == "dontAsk"
    assert [r["tool"] for r in t.records if r["kind"] == "tool"]


def test_review_pages_are_graph_written_and_unreachable_by_the_cc_sub_agent(rt):
    """05c item 4. The review pages (build/review) are written by the graph (node_review), the same for both
    harnesses, from gate evidence; the Claude Code sub-agent reaches only the MCP tools of its role jail and cannot
    write them. With --review on the graph pauses with a LangGraph interrupt (python -m agent resume); Claude Code
    itself never asks (headless, dontAsk)."""
    from agent.core import dispatch
    from agent.graph.review import write_page
    from agent.graph.roles import role_session
    _enter(rt, 1)
    p = write_page(rt.design, 1, "board-and-device-planning", {"gates": [["arch_note", True, ""]], "approval": None})
    assert p.exists() and "review" in p.parts
    for role in ("clarify", "model", "tests", "rtl"):
        s = role_session(rt.session, role)
        r = dispatch(s, "write_file", {"path": "build/review/review_01.html", "content": "forged"})
        assert not r.get("ok"), role
    assert "forged" not in p.read_text()
    argv = arm.cli_argv(rt, gr.subagent_plan(rt, "rtl", "p", ()), Path("/tmp/m.json"), "claude-haiku-5-5", "medium", 5)
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk" and "--tools" in argv
