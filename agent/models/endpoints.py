"""The model clients of the endpoint kinds (brief 108). Only the resolver builds these; the gate test
(``agent/tests/test_108_model_config.py``) fails when any other file constructs a model client.

- :class:`OpenRouterClient`: the chat-completions protocol through the ``openai`` SDK. Used for the ``openrouter`` kind and,
  with another ``base_url``, for ``openai_compatible`` (vLLM, a local model, a specialist fine-tune). On the OpenRouter host
  it sends ``provider: {data_collection: "deny"}`` and ``usage: {include: true}``; elsewhere neither. Cost is only what the
  provider reports (never estimated; unreported cost is ``None`` and counts against the cap at the per-call ceiling).
- :class:`AnthropicClient`: the Messages API (plain HTTPS, no extra dependency), with tools in the Anthropic shape. The API
  reports tokens, not dollars, so ``cost`` is ``None``.
- :class:`ClaudeCodeChat`: a messages -> Reply adapter over one tool-less headless ``claude -p`` call (the subscription's
  "API-like mode"), for call sites that only need text.

Keys come from the environment variable the endpoint names (``key_env``), never from the configuration; the OpenRouter key
may also come from the owner's mode-600 file, as before. A key is never printed, logged or recorded.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent.graph.llm import DEFAULT_MODEL, FORBIDDEN, OPENROUTER_BASE, Reply
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


def read_key(key_env: str | None) -> str | None:
    """The key named by ``key_env`` (an environment variable name); the OpenRouter key may come from the owner's key file."""
    if not key_env:
        return None
    return os.environ.get(key_env) or (_key_from_file() if key_env == "OPENROUTER_API_KEY" else None)


class OpenRouterClient:
    temperature: float | None = 0.2
    router: bool = True                           # send OpenRouter's provider and usage fields
    params: dict[str, Any] = {}                   # seed, max_tokens, stop, reasoning effort

    def __init__(self, model: str = DEFAULT_MODEL, timeout_s: float = 180.0, *, base_url: str = OPENROUTER_BASE, key_env: str | None = "OPENROUTER_API_KEY",
                 temperature: float | None = 0.2, retries: int = 1, router: bool | None = None, params: dict[str, Any] | None = None):
        import openai
        if router is None:
            router = "openrouter.ai" in base_url
        if router and any(f in model.lower() for f in FORBIDDEN):
            raise ValueError(f"model {model!r} is not allowed through OpenRouter (owner rule)")
        key = read_key(key_env)
        if not key and "localhost" not in base_url and "127.0.0.1" not in base_url:
            raise ValueError(f"{key_env} is not set" + (f" and {KEY_FILE} has none" if key_env == "OPENROUTER_API_KEY" else ""))
        self.model, self.temperature, self.router, self.params = model, temperature, router, dict(params or {})
        self._c = openai.OpenAI(api_key=key or "none", base_url=base_url, timeout=timeout_s, max_retries=retries)

    #: brief 42 amendment 3: a response that cannot be parsed (the SDK's body parse, or a tool call whose ``arguments`` are not
    #: JSON) is asked for again, up to this many extra times; every arm gets it. Three of the first six brief 42 runs died on one.
    MALFORMED_RETRIES = 2

    def __call__(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        t0 = time.monotonic()
        body = {"usage": {"include": True}, "provider": {"data_collection": "deny"}} if self.router else {}
        extra = {k: v for k, v in self.params.items() if k not in ("effort",)}
        if self.params.get("effort"):
            body["reasoning"] = {"effort": self.params["effort"]}
        for attempt in range(self.MALFORMED_RETRIES + 1):
            try:
                r = self._c.chat.completions.create(model=self.model, messages=messages,
                                                    **({"temperature": self.temperature} if self.temperature is not None else {}),
                                                    **({"extra_body": body} if body else {}), **extra,
                                                    **({"tools": tools} if tools else {}))
                u = r.usage
                uextra = (getattr(u, "model_extra", None) or {}) if u else {}
                m = r.choices[0].message if r.choices else None
                calls = [{"id": c.id, "name": c.function.name, "args": json.loads(c.function.arguments or "{}")}
                         for c in (getattr(m, "tool_calls", None) or [])]
                break
            except json.JSONDecodeError as e:
                self.malformed_retries = getattr(self, "malformed_retries", 0) + 1
                print(f"FDA_MALFORMED attempt {attempt + 1}: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr, flush=True)
                if attempt == self.MALFORMED_RETRIES:
                    raise
        return Reply(text=(m.content if m else "") or "", tool_calls=calls,
                     prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                     completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                     cost=uextra.get("cost"), seconds=round(time.monotonic() - t0, 2),
                     provider=getattr(r, "provider", None) or (r.model_extra or {}).get("provider"))


class AnthropicClient:
    """The Messages API over plain HTTPS. ``opener`` is the injection point of the tests."""

    def __init__(self, model: str, *, base_url: str = "https://api.anthropic.com", key_env: str | None = "ANTHROPIC_API_KEY", timeout_s: float = 180.0,
                 temperature: float | None = 0.2, max_tokens: int = 8192, stop: list[str] | None = None, thinking_budget: int | None = None,
                 retries: int = 1, opener=None):
        self.model, self.base_url, self.timeout_s, self.retries = model, base_url.rstrip("/"), timeout_s, retries
        self.temperature, self.max_tokens, self.stop, self.thinking_budget = temperature, max_tokens, stop, thinking_budget
        self._key = read_key(key_env)
        if not self._key and opener is None:
            raise ValueError(f"{key_env} is not set")
        self._open = opener or urllib.request.urlopen

    @staticmethod
    def to_anthropic(messages: list[dict], tools: list[dict] | None) -> tuple[str, list[dict], list[dict]]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        out: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "tool":
                blk = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m.get("content") or ""}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) and out[-1]["content"][-1].get("type") == "tool_result":
                    out[-1]["content"].append(blk)
                else:
                    out.append({"role": "user", "content": [blk]})
            elif m["role"] == "assistant":
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for c in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": c["id"], "name": c["function"]["name"],
                                   "input": json.loads(c["function"]["arguments"] or "{}")})
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            else:
                out.append({"role": "user", "content": m["content"]})
        tl = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
               "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}} for t in (tools or [])]
        return system, out, tl

    def __call__(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        t0 = time.monotonic()
        system, msgs, tl = self.to_anthropic(messages, tools)
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "messages": msgs}
        if system:
            body["system"] = system
        if tl:
            body["tools"] = tl
        if self.stop:
            body["stop_sequences"] = list(self.stop)
        if self.thinking_budget:
            body["thinking"] = {"type": "enabled", "budget_tokens": int(self.thinking_budget)}
        elif self.temperature is not None:
            body["temperature"] = self.temperature
        req = urllib.request.Request(f"{self.base_url}/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                              "x-api-key": self._key or ""})
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with self._open(req, timeout=self.timeout_s) as resp:
                    d = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                last = RuntimeError(f"Anthropic API HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
                if e.code < 500 and e.code != 429:
                    raise last from None
            except (urllib.error.URLError, TimeoutError) as e:
                last = RuntimeError(f"Anthropic API unreachable: {type(e).__name__}")
        else:
            raise last or RuntimeError("Anthropic API call failed")
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in d.get("content", []) if b.get("type") == "tool_use"]
        u = d.get("usage") or {}
        return Reply(text=text, tool_calls=calls, prompt_tokens=int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
                     + int(u.get("cache_creation_input_tokens") or 0), completion_tokens=int(u.get("output_tokens") or 0), cost=None,
                     seconds=round(time.monotonic() - t0, 2), provider="anthropic")


class ClaudeCodeChat:
    """messages -> Reply over one tool-less headless Claude Code call (the Max plan). No tool calls: a caller that passes
    tools is refused with a clear error (the table check already refuses a purpose whose call sites need them)."""

    def __init__(self, model: str, *, effort: str | None = None, timeout_s: float = 900, log: Path | None = None, label: str = "chat"):
        self.model, self.effort, self.timeout_s, self.log, self.label = model, effort, timeout_s, log, label

    def __call__(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        if tools:
            raise RuntimeError("a claude_code endpoint cannot take tool calls here: put this purpose on a chat endpoint")
        from agent.models import claude_cli
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        user = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
        t0 = time.time()
        res = claude_cli.text_call(system, user, model=self.model, effort=self.effort, timeout_s=self.timeout_s, prefix=f"fda_{self.label}_")
        u = res.get("usage") or {}
        tok_in = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        tok_out = int(u.get("output_tokens") or 0)
        if self.log is not None:
            with self.log.open("a") as f:
                f.write(json.dumps({"tag": self.label, "role": self.label, "model_requested": self.model, "effort": self.effort or "cli-default",
                                    "turns": res.get("num_turns"), "wall_s": round(time.time() - t0, 1), "is_error": res.get("is_error"),
                                    "tokens": tok_in + tok_out, "cost_usd": "unreported",
                                    "plan_cost_estimate_usd": res.get("total_cost_usd")}) + "\n")
        return Reply(text=str(res.get("result", "")), tool_calls=[], prompt_tokens=tok_in, completion_tokens=tok_out, cost=0.0,
                     seconds=round(time.time() - t0, 2), provider="claude_code")
