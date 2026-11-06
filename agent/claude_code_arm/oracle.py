"""The interview oracle on the Max plan (brief 07a2-prep): the same user simulator as ``agent.__main__._oracle``, but each
answer is one headless ``claude -p`` call with no tools, instead of an OpenRouter call. Used when a run must not touch
OpenRouter (``--oracle claude_code``). Same isolation as a sub-agent turn: an empty HOME and config directory, a temporary
working directory, no tools, no MCP, no settings; only the plan's token. Anthropic models only; never Fable or Opus by default
(the model is Haiku; the oracle only looks a line up in the hidden spec)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from agent.claude_code_arm import arm


def _argv(system: str, user: str, model: str) -> list[str]:
    return ["claude", "-p", user, "--output-format", "json", "--system-prompt", system, "--tools", "",
            "--strict-mcp-config", "--permission-mode", "dontAsk", "--setting-sources", "", "--disable-slash-commands",
            "--no-session-persistence", "--model", model, "--max-turns", "1"]


def parse_answer(text: str) -> dict[str, Any]:
    """The JSON object in the model's reply (plain, fenced, or inside prose); ``not specified`` when there is none."""
    t = text.strip()
    for cand in (t, re.sub(r"^```(?:json)?\s*|\s*```$", "", t)):
        try:
            d = json.loads(cand)
            if isinstance(d, dict):
                return d
        except ValueError:
            pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            d = json.loads(m.group())
            if isinstance(d, dict):
                return d
        except ValueError:
            pass
    return {"answer": "not specified", "quote": None}


def cc_oracle(model: str, log: Path | None = None, timeout_s: float = 300) -> Callable[[str, str], dict[str, Any]]:
    """An ``llm(system, user) -> {"answer", "quote"}`` callable for :class:`agent.graph.interview.SpecOracle`."""
    def llm(system: str, user: str) -> dict[str, Any]:
        from agent.graph.run import ArmBlocked
        if shutil.which("claude") is None:
            raise ArmBlocked("the claude CLI is not on PATH")
        token = arm.oauth_token()
        if not token:
            raise ArmBlocked("CLAUDE_CODE_OAUTH_TOKEN is not set and the token file is missing")
        work = Path(tempfile.mkdtemp(prefix="fda_oracle_"))
        try:
            p = subprocess.run(_argv(system, user, model), cwd=work, env=arm.isolated_env(work, token), capture_output=True,
                               text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        try:
            res = json.loads(p.stdout)
        except ValueError:
            res = {}
        out = parse_answer(str(res.get("result", "")))
        if log:
            with log.open("a") as f:
                f.write(json.dumps({"model": model, "question": user[:400], "reply": out, "is_error": res.get("is_error"),
                                    "plan_cost_estimate_usd": res.get("total_cost_usd")}) + "\n")
        return out
    return llm
