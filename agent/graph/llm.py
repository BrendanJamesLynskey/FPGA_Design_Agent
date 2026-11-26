"""The model client for the Deep Agents agent (brief 05b).

- The model clients (:class:`OpenRouterClient` and the others) live in :mod:`agent.models.endpoints` and are built only by the
  resolver (brief 108). Cost is only what the provider reports (never estimated; unreported cost is recorded as ``None`` and
  counted against the cap as the per-call ceiling).
- :class:`Recorder` wraps a client and writes every call to an episode fixture; :class:`Replay` serves the
  fixture back in order (CI: no network, no spend).
- :func:`chat_model`: a LangChain chat model whose every call goes through a :class:`Meter` that enforces the
  stage and run limits (turns, seconds, USD) before the call is made.

Adapted from the owner's CVDP RTL Agent (``agent/cvdp_agent/llm.py`` and ``deep.py``: the OpenRouter body, the
provider-reported cost rule, and the LangChain adapter for Deep Agents), MIT.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
FORBIDDEN = ("anthropic/", "fable", "opus")     # owner rule: never Fable or Opus through OpenRouter
UNREPORTED_COST_CEILING = 0.05                   # USD charged to the cap for a call whose cost was not reported


@dataclass
class Reply:
    text: str
    tool_calls: list[dict[str, Any]]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = 0.0
    seconds: float = 0.0
    provider: str | None = None
    input_tokens: int = 0            # brief 209b: Anthropic usage, uncached input (prompt_tokens is the sum of the three input fields)
    cache_write_tokens: int = 0      # cache_creation_input_tokens
    cache_read_tokens: int = 0       # cache_read_input_tokens
    stop_reason: str | None = None   # brief 209b: the API's stop_reason ("max_tokens" means the reply was cut off)
    stream_retries: int = 0          # brief 224: streams that dropped and were asked for again before this reply arrived
    thinking_tokens: int | None = None   # brief 234: usage.output_tokens_details.thinking_tokens when the API gives it (None: not reported)
    thinking_blocks: int = 0             # brief 234: thinking blocks in the reply (their text is empty unless display is on)
    visible_chars: int = 0               # brief 234: characters of text and tool-call arguments in the reply (output_tokens minus these is thinking)
    cost_basis: str | None = None    # "usage*price" when the cost was computed from usage and a price table, else None


def __getattr__(name: str):
    """``OpenRouterClient`` and the key-file helpers moved to :mod:`agent.models.endpoints` (brief 108: only the resolver builds
    a model client); the old import path still names them."""
    if name in ("OpenRouterClient", "KEY_FILE", "_key_from_file"):
        from agent.models import endpoints
        return getattr(endpoints, name)
    raise AttributeError(name)


class Recorder:
    def __init__(self, inner, path: Path):
        self.inner, self.path, self.calls = inner, Path(path), []

    def __call__(self, messages, tools=None):
        r = self.inner(messages, tools)
        self.calls.append(r.__dict__)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.calls, indent=1))
        return r


class Replay:
    def __init__(self, calls: list[dict[str, Any]] | Path):
        self.calls = json.loads(Path(calls).read_text()) if isinstance(calls, (str, Path)) else list(calls)
        self.i = 0

    def __call__(self, messages, tools=None):
        if self.i >= len(self.calls):
            raise AssertionError("replay: the agent made more model calls than were recorded")
        c = self.calls[self.i]
        self.i += 1
        return Reply(**c)


class BudgetExceeded(Exception):
    pass


@dataclass
class Meter:
    """Counts turns, seconds and USD per stage visit and per run; refuses a call that would start past a limit."""
    run_limits: dict[str, float]
    stage_limits: dict[str, float] = field(default_factory=dict)
    run: dict[str, float] = field(default_factory=lambda: {"turns": 0, "seconds": 0.0, "usd": 0.0, "tokens": 0})
    stage: dict[str, float] = field(default_factory=lambda: {"turns": 0, "seconds": 0.0, "usd": 0.0, "tokens": 0})
    t_stage: float = field(default_factory=time.monotonic)
    t_run: float = field(default_factory=time.monotonic)
    unreported: int = 0
    truncated: int = 0         # brief 209b: calls whose reply stopped at max_tokens
    usd_scale: float = 1.0     # brief 209b: multiplies every stage USD limit (the run cap is scaled by the caller); recorded in the run summary
    split: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0})
    turns_auto: int = 0        # brief 234: the run turn cap last set from the design's size (0: the cap is as configured)
    reserved: int = 0          # brief 05g: turns held back for the roles that run after the current one

    def start_stage(self, limits: dict[str, float]) -> None:
        self.stage_limits = {**limits, **({"usd": round(limits["usd"] * self.usd_scale, 6)} if "usd" in limits else {})}
        self.stage = {"turns": 0, "seconds": 0.0, "usd": 0.0, "tokens": 0}
        self.t_stage = time.monotonic()

    def check(self) -> None:
        self.stage["seconds"] = round(time.monotonic() - self.t_stage, 1)
        self.run["seconds"] = round(time.monotonic() - self.t_run, 1)
        # brief 209b: the run limit is tested first. When both were exceeded the stage message won, node_work's handler (which re-raises only
        # a message starting "run ") treated it as a stage stop and the run went on past its cap (smoke run: 1.01 USD against --max-usd 0.9).
        for scope, used, lim in (("run", self.run, self.run_limits), ("stage", self.stage, self.stage_limits)):
            for k in ("turns", "seconds", "usd"):
                held = self.reserved if k == "turns" else 0
                if k in lim and used[k] >= lim[k] - held:
                    raise BudgetExceeded(f"{scope} {k} limit {lim[k] - held} reached ({used[k]})"
                                         + (f", {held} held back for the roles that follow" if held else ""))

    def turns_left(self) -> int:
        """Turns the current role may still use: the smaller of the stage and run budgets, less the reserve."""
        left = [int(lim["turns"] - used["turns"]) for used, lim in ((self.stage, self.stage_limits), (self.run, self.run_limits))
                if "turns" in lim]
        return max(0, min(left or [0]) - self.reserved)

    def add(self, r: Reply) -> None:
        usd = r.cost if r.cost is not None else UNREPORTED_COST_CEILING
        self.unreported += r.cost is None
        self.truncated += getattr(r, "stop_reason", None) == "max_tokens"
        for d in (self.stage, self.run):
            d["turns"] += 1
            d["usd"] = round(d["usd"] + usd, 6)
            d["tokens"] += r.prompt_tokens + r.completion_tokens
        self.split["input"] += getattr(r, "input_tokens", 0) or 0
        self.split["output"] += r.completion_tokens
        self.split["cache_write"] += getattr(r, "cache_write_tokens", 0) or 0
        self.split["cache_read"] += getattr(r, "cache_read_tokens", 0) or 0


def chat_model(client, meter: Meter, log: list):
    """A LangChain chat model over ``client`` for create_deep_agent."""
    from typing import Any as _Any

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.utils.function_calling import convert_to_openai_tool

    def to_dicts(msgs):
        out = []
        for m in msgs:
            role = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}.get(m.type, "user")
            d = {"role": role, "content": m.content if isinstance(m.content, str) else json.dumps(m.content)}
            if role == "assistant" and getattr(m, "tool_calls", None):
                d["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                    "name": c["name"], "arguments": json.dumps(c["args"])}} for c in m.tool_calls]
            if role == "tool":
                d["tool_call_id"] = m.tool_call_id
            out.append(d)
        return out

    class FdaChatModel(BaseChatModel):
        tools_: list = []
        meta: _Any = None

        @property
        def _llm_type(self):
            return "fda"

        def _get_ls_params(self, stop=None, **kw):
            p = super()._get_ls_params(stop=stop, **kw)
            p["ls_provider"] = "fda"
            return p

        def bind_tools(self, tools, **kw):
            return self.model_copy(update={"tools_": [convert_to_openai_tool(t) for t in tools]})

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            meter.check()                                   # raises BudgetExceeded before spending
            r = client(to_dicts(messages), self.tools_ or None)
            meter.add(r)
            log.append({"turn": meter.run["turns"], "cost": r.cost, "tokens": r.prompt_tokens + r.completion_tokens,
                        "tools": [c["name"] for c in r.tool_calls]})
            msg = AIMessage(content=r.text, tool_calls=[{"name": c["name"], "args": c["args"], "id": c["id"]}
                                                        for c in r.tool_calls])
            return ChatResult(generations=[ChatGeneration(message=msg)])

    return FdaChatModel()
