"""The interview oracle on the Max plan (brief 07a2-prep): the same user simulator as ``agent.__main__._oracle``, but each
answer is one headless ``claude -p`` call with no tools, instead of an OpenRouter call. Used when a run must not touch
OpenRouter (``--oracle claude_code``). Same isolation as a sub-agent turn: an empty HOME and config directory, a temporary
working directory, no tools, no MCP, no settings; only the plan's token. Anthropic models only; never Fable or Opus by default
(the model is Haiku; the oracle only looks a line up in the hidden spec)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from agent.models import claude_cli


def _argv(system: str, user: str, model: str) -> list[str]:
    from agent.models import claude_cli
    return claude_cli.build_argv(system=system, prompt=user, model=model)


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


def cc_oracle(model: str, log: Path | None = None, timeout_s: float = 300, entry=None, resolver=None) -> Callable[[str, str], dict[str, Any]]:
    from agent.access import require_or_exit      # brief 94
    require_or_exit("claude_code_arm.oracle")
    """An ``llm(system, user) -> {"answer", "quote"}`` callable for :class:`agent.graph.interview.SpecOracle`."""
    def llm(system: str, user: str) -> dict[str, Any]:
        import time
        t0 = time.monotonic()
        if resolver is not None and entry is not None:          # brief 107: through the tape when there is one
            res = resolver.text_result(entry, system, user, timeout_s=timeout_s, effort=None, prefix="fda_oracle_")
        else:
            res = claude_cli.text_call(system, user, model=model, timeout_s=timeout_s, prefix="fda_oracle_")
        if resolver is not None and entry is not None:
            resolver.log_text_call(entry, time.monotonic() - t0)
        out = parse_answer(str(res.get("result", "")))
        if log:
            with log.open("a") as f:
                f.write(json.dumps({"model": model, "question": user[:400], "reply": out, "is_error": res.get("is_error"),
                                    "plan_cost_estimate_usd": res.get("total_cost_usd")}) + "\n")
        return out
    return llm
