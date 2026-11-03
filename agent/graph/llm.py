"""The model client for the Deep Agents agent (brief 05b).

- :class:`OpenRouterClient`: OpenRouter's chat completions through the ``openai`` SDK, ``provider:
  {data_collection: "deny"}``, ``usage: {include: true}``; cost is only what the provider reports (never estimated;
  unreported cost is recorded as ``None`` and counted against the cap as the per-call ceiling).
- :class:`Recorder` wraps a client and writes every call to an episode fixture; :class:`Replay` serves the
  fixture back in order (CI: no network, no spend).
- :func:`chat_model`: a LangChain chat model whose every call goes through a :class:`Meter` that enforces the
  stage and run limits (turns, seconds, USD) before the call is made.

Adapted from the owner's CVDP RTL Agent (``agent/cvdp_agent/llm.py`` and ``deep.py``: the OpenRouter body, the
provider-reported cost rule, and the LangChain adapter for Deep Agents), MIT.
"""

from __future__ import annotations

import json
import os
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


KEY_FILE = Path.home() / ".config" / "fpga_design_agent" / "openrouter.env"


def _key_from_file() -> str | None:
    """OPENROUTER_API_KEY=... from the local key file (outside the repo, mode 600); never printed."""
    try:
        if KEY_FILE.stat().st_mode & 0o077:
            raise ValueError(f"{KEY_FILE} must be readable by its owner only (chmod 600)")
        for line in KEY_FILE.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip() or None
    except FileNotFoundError:
        return None
    return None


class OpenRouterClient:
    def __init__(self, model: str = DEFAULT_MODEL, timeout_s: float = 180.0):
        import openai
        if any(f in model.lower() for f in FORBIDDEN):
            raise ValueError(f"model {model!r} is not allowed through OpenRouter (owner rule)")
        key = os.environ.get("OPENROUTER_API_KEY") or _key_from_file()
        if not key:
            raise ValueError(f"OPENROUTER_API_KEY is not set and {KEY_FILE} has none")
        self.model = model
        self._c = openai.OpenAI(api_key=key, base_url=OPENROUTER_BASE, timeout=timeout_s, max_retries=1)

    def __call__(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        t0 = time.monotonic()
        body = {"usage": {"include": True}, "provider": {"data_collection": "deny"}}
        r = self._c.chat.completions.create(model=self.model, messages=messages, temperature=0.2, extra_body=body,
                                            **({"tools": tools} if tools else {}))
        u = r.usage
        extra = (getattr(u, "model_extra", None) or {}) if u else {}
        m = r.choices[0].message if r.choices else None
        calls = [{"id": c.id, "name": c.function.name, "args": json.loads(c.function.arguments or "{}")}
                 for c in (getattr(m, "tool_calls", None) or [])]
        return Reply(text=(m.content if m else "") or "", tool_calls=calls,
                     prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                     completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                     cost=extra.get("cost"), seconds=round(time.monotonic() - t0, 2),
                     provider=getattr(r, "provider", None) or (r.model_extra or {}).get("provider"))


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
    reserved: int = 0          # brief 05g: turns held back for the roles that run after the current one

    def start_stage(self, limits: dict[str, float]) -> None:
        self.stage_limits = limits
        self.stage = {"turns": 0, "seconds": 0.0, "usd": 0.0, "tokens": 0}
        self.t_stage = time.monotonic()

    def check(self) -> None:
        self.stage["seconds"] = round(time.monotonic() - self.t_stage, 1)
        self.run["seconds"] = round(time.monotonic() - self.t_run, 1)
        for scope, used, lim in (("stage", self.stage, self.stage_limits), ("run", self.run, self.run_limits)):
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
        for d in (self.stage, self.run):
            d["turns"] += 1
            d["usd"] = round(d["usd"] + usd, 6)
            d["tokens"] += r.prompt_tokens + r.completion_tokens


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
