"""The Claude Code arm (brief 05c): one sub-agent turn as one headless ``claude -p`` call, configured to approximate
a plain API call. The stage machine, gates, review pages and rewind are the same graph as the Deep Agents agent
(``agent.graph.run``); only :func:`run_subagent_cc` replaces ``run_subagent``.

Anthropic models only, on the owner's Max plan, through the documented headless CLI (not the Agent SDK; never
OpenRouter). Every flag below is in the CLI reference (https://code.claude.com/docs/en/cli-reference, read
2026-11-02, CLI 2.1.316):

``--print/-p``                 headless run.
``--output-format stream-json --verbose``   one JSON event per line (the init event lists tools, MCP servers, skills).
``--system-prompt``            REPLACES Claude Code's default system prompt with ours (the stage-machine prompt).
``--tools ""``                 disables every built-in tool (Bash, Read, Edit, Write, Glob, Grep, WebFetch, WebSearch,
                               Task...). The stage machine needs none: file access, lint, simulate, build, gates and
                               docs all come from our MCP tools, which carry the role jail and the audit log. No web.
``--mcp-config`` + ``--strict-mcp-config``  only our MCP server (05a: ``python -m agent.mcp_server``), no other.
``--allowedTools mcp__fda__<name>``   exactly the stage's tool names (permission rules).
``--permission-mode dontAsk``  anything not allowed is denied, never asked (headless, nobody to ask).
``--setting-sources ""``       load no user/project/local settings files.
``--disable-slash-commands``   no skills or commands.
``--no-session-persistence``   nothing saved to disk for resume.
``--model`` / ``--effort``     pinned model id and effort level.
``--max-turns``                the Deep Agents stage limit (stages.MACHINE limits.turns, less what the stage used).
Plus the environment: an empty ``HOME`` and ``CLAUDE_CONFIG_DIR`` (no user settings, CLAUDE.md, skills, hooks, MCP),
the working directory an empty temp directory outside the repo (no CLAUDE.md found by walking up), and
``CLAUDE_CODE_OAUTH_TOKEN`` from ``claude setup-token`` (the documented headless subscription login; ``--bare`` does
not read it, so it is not used).

Not available, nearest equivalent: no temperature control (Deep Agents uses 0.2); no ``--max-budget-usd`` use (it is
for API billing; the plan has no per-call cost); the wall cap is the subprocess timeout; there is no flag to turn off
context compaction (``--autocompact`` only sets its window).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from agent.core.session import ROOT
from agent.core.trace import Trace

PINNED_CLI = "2.1.316"
MCP_NAME = "fda"
TOKEN_FILE = Path.home() / ".config" / "fpga_design_agent" / "claude_code_oauth.env"
MODELS = {"haiku": "claude-haiku-5-5", "opus": "claude-opus-5-5"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def oauth_token() -> str | None:
    """CLAUDE_CODE_OAUTH_TOKEN from the environment or the mode-600 local file; never printed."""
    t = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if t:
        return t.strip()
    try:
        if TOKEN_FILE.stat().st_mode & 0o077:
            raise ValueError(f"{TOKEN_FILE} must be readable by its owner only (chmod 600)")
        for line in TOKEN_FILE.read_text().splitlines():
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'") or None
    except FileNotFoundError:
        return None
    return None


def tool_ids(plan: dict[str, Any]) -> list[str]:
    """The MCP tool names Claude Code sees (``mcp__fda__<tool>``): the stage's core tools plus the role's file tools."""
    names = list(dict.fromkeys([*plan["file_tools"], *plan["core_tools"]]))
    return [f"mcp__{MCP_NAME}__{n}" for n in names]


def mcp_config(rt, plan: dict[str, Any]) -> dict[str, Any]:
    """The strict MCP config: our server only, jailed to this role and stage, exposing only the stage's tools."""
    names = list(dict.fromkeys([*plan["file_tools"], *plan["core_tools"]]))
    env = {"PYTHONPATH": str(ROOT), "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    for k in ("FDA_TOOLS_FILE", "FDA_BOARDS_FILE", "FDA_KNOWLEDGE"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    tf = Path.home() / ".config" / "fpga_design_agent" / "tools.yaml"
    env.setdefault("FDA_TOOLS_FILE", str(tf))
    return {"mcpServers": {MCP_NAME: {
        "command": sys.executable,
        "args": ["-m", "agent.mcp_server", "--design", str(rt.design), "--board", rt.cfg.board,
                 "--role", plan["role"], "--stage", plan["stage"], "--tools", ",".join(names)],
        "env": env}}}


def cli_argv(rt, plan: dict[str, Any], mcp_file: Path, model: str, effort: str, max_turns: int) -> list[str]:
    return ["claude", "-p", plan["user_message"], "--output-format", "stream-json", "--verbose",
            "--system-prompt", plan["system_prompt"], "--tools", "",
            "--mcp-config", str(mcp_file), "--strict-mcp-config",
            "--allowedTools", *tool_ids(plan), "--permission-mode", "dontAsk",
            "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
            "--model", model, "--effort", effort, "--max-turns", str(max_turns)]


def isolated_env(home: Path, token: str) -> dict[str, str]:
    """Nothing from the user's environment but PATH: an empty HOME and config dir, the plan's token."""
    return {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            "CLAUDE_CODE_OAUTH_TOKEN": token, "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "LANG": os.environ.get("LANG", "C.UTF-8")}


def parse_stream(lines: list[str], trace: Trace | None, stage: str, seconds: float = 0.0) -> dict[str, Any]:
    """Claude Code's stream-json -> the shared trace (05a format) and a summary. Cost is never reported by the
    plan: ``cost_usd`` is the string "unreported"; Claude Code's own estimate is kept as plan_cost_estimate_usd."""
    init, result, pending, served = None, None, {}, set()
    tokens = {"input": 0, "output": 0}
    n_tools = 0
    for line in lines:
        try:
            ev = json.loads(line)
        except (ValueError, TypeError):
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            init = ev
        elif t == "assistant":
            msg = ev.get("message") or {}
            u = msg.get("usage") or {}
            tin = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            tout = int(u.get("output_tokens") or 0)
            tokens["input"] += tin
            tokens["output"] += tout
            if msg.get("model"):
                served.add(msg["model"])
                if trace:
                    trace.model(msg["model"], {"input": tin, "output": tout}, "unreported", stage)
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    pending[c["id"]] = (str(c.get("name", "")).removeprefix(f"mcp__{MCP_NAME}__"), c.get("input") or {})
                    n_tools += 1
        elif t == "user":
            for c in (ev.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                    name, args = pending.pop(c["tool_use_id"])
                    body = c.get("content")
                    if isinstance(body, list):
                        body = "".join(x.get("text", "") for x in body if isinstance(x, dict))
                    if trace:
                        trace.tool(name, args, {"ok": not c.get("is_error"), "output": str(body)[:2000]}, stage)
        elif t == "result":
            result = ev
    return {"init": init, "result": result, "tokens": tokens, "tool_calls": n_tools, "served_models": sorted(served)}


def init_report(init: dict | None) -> dict[str, Any]:
    """What Claude Code says it loaded (evidence that no user config came in)."""
    i = init or {}
    return {k: i.get(k) for k in ("tools", "mcp_servers", "slash_commands", "skills", "plugins", "agents", "model",
                                  "permissionMode", "claude_code_version", "apiKeySource", "output_style") if k in i}


def run_subagent_cc(rt, plan: dict[str, Any]) -> dict[str, str]:
    """One sub-agent turn through ``claude -p``. Raises ArmBlocked when it cannot run at all."""
    from agent.graph.run import ArmBlocked, drop_superseded
    if shutil.which("claude") is None:
        raise ArmBlocked("the claude CLI is not on PATH")
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    if not ver.startswith(PINNED_CLI):
        raise ArmBlocked(f"Claude Code {ver!r} is not the pinned {PINNED_CLI}")
    token = oauth_token()
    if not token:
        raise ArmBlocked("CLAUDE_CODE_OAUTH_TOKEN is not set and the token file is missing (owner: run "
                         f"`claude setup-token`, save it to {TOKEN_FILE}, chmod 600)")
    rt.meter.check()
    lim = plan["limits"]
    left = max(1, int(lim.get("turns", 30) - rt.meter.stage["turns"]))
    wall = max(30.0, float(lim.get("seconds", 1800)) - rt.meter.stage["seconds"])
    before = {str(p): p.stat().st_mtime for p in rt.design.rglob("*") if p.is_file()}
    tests_before = [p for d in ("tests", "verif") for p in sorted((rt.design / d).rglob("*"))
                    if p.is_file() and "__pycache__" not in p.parts and p.name != "__init__.py"] \
        if plan["role"] == "tests" else []
    out_dir = rt.run_dir / "claude_code"
    out_dir.mkdir(exist_ok=True)
    n = len(list(out_dir.glob("*.jsonl"))) + 1
    tag = f"{n:03d}_{plan['role']}_{plan['stage']}"
    work = Path(tempfile.mkdtemp(prefix="fda_cc_"))              # HOME, config dir and cwd: all empty, outside the repo
    mcp_file = work / "mcp.json"
    mcp_file.write_text(json.dumps(mcp_config(rt, plan)))
    argv = cli_argv(rt, plan, mcp_file, rt.cfg.cc_model, rt.cfg.cc_effort, left)
    shown = list(argv)
    shown[2], shown[argv.index("--system-prompt") + 1] = f"<user message: {out_dir.name}/{tag}.user.txt>", \
        f"<system prompt: {out_dir.name}/{tag}.system.txt>"
    (out_dir / f"{tag}.argv.json").write_text(json.dumps(shown, indent=1))
    (out_dir / f"{tag}.user.txt").write_text(plan["user_message"])
    (out_dir / f"{tag}.system.txt").write_text(plan["system_prompt"])
    t0, timed_out = time.time(), False
    try:
        p = subprocess.run(argv, cwd=work, env=isolated_env(work, token), capture_output=True, text=True,
                           timeout=wall, stdin=subprocess.DEVNULL)
        out, err = p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = ""
    finally:
        shutil.rmtree(work, ignore_errors=True)
    secs = round(time.time() - t0, 1)
    lines = out.splitlines()
    trace = Trace(rt.run_dir / "trace.jsonl", harness="claude_code")
    info = parse_stream(lines, trace, plan["stage"], secs)
    res = info["result"] or {}
    (out_dir / f"{tag}.jsonl").write_text("\n".join(lines) + "\n")
    text = str(res.get("result", ""))
    if res.get("is_error") and any(k in text.lower() + err.lower() for k in ("login", "authenticat", "oauth", "401")):
        raise ArmBlocked("Claude Code could not authenticate: " + text[:200])
    turns = int(res.get("num_turns") or 0)
    for d in (rt.meter.stage, rt.meter.run):
        d["turns"] += turns
        d["tokens"] += info["tokens"]["input"] + info["tokens"]["output"]
    rec = {"tag": tag, "role": plan["role"], "stage": plan["stage"], "model_requested": rt.cfg.cc_model,
           "models_served": info["served_models"], "effort": rt.cfg.cc_effort, "claude_code_version": ver,
           "turns": turns, "max_turns": left, "tool_calls": info["tool_calls"], "wall_s": secs, "timed_out": timed_out,
           "subtype": res.get("subtype"), "is_error": res.get("is_error"), "tokens": info["tokens"],
           "cost_usd": "unreported", "plan_cost_estimate_usd": res.get("total_cost_usd"),
           "init": init_report(info["init"]), "stderr_tail": err[-500:]}
    with (rt.run_dir / "claude_code_calls.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    written = {str(p.relative_to(rt.design)): "" for p in rt.design.rglob("*")
               if p.is_file() and "build" not in p.parts and "__pycache__" not in p.parts
               and p.stat().st_mtime > before.get(str(p), 0)}
    if tests_before and written:
        from agent.graph.roles import RoleJail
        drop_superseded(rt.design, RoleJail(rt.session.jail, "tests"), tests_before, written)
    return written
