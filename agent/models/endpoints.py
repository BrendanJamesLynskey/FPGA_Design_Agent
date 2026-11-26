"""The model clients of the endpoint kinds (brief 108). Only the resolver builds these; the gate test
(``agent/tests/test_108_model_config.py``) fails when any other file constructs a model client.

- :class:`OpenRouterClient`: the chat-completions protocol through the ``openai`` SDK. Used for the ``openrouter`` kind and,
  with another ``base_url``, for ``openai_compatible`` (vLLM, a local model, a specialist fine-tune). On the OpenRouter host
  it sends ``provider: {data_collection: "deny"}`` and ``usage: {include: true}``; elsewhere neither. Cost is only what the
  provider reports (never estimated; unreported cost is ``None`` and counts against the cap at the per-call ceiling).
- :class:`AnthropicClient`: the Messages API (plain HTTPS, no extra dependency), with tools in the Anthropic shape. The API
  reports tokens, not dollars, so (brief 209b) ``cost`` is computed from the response ``usage`` (input, output, cache write, cache
  read) and the model's price table in the model config (``models:`` in ``agent.models.config``): never from a guess. A model with no
  price keeps ``cost=None`` (the per-call ceiling) and warns once. The stable prefix is marked for prompt caching, and ``temperature``
  is left out for models the config says reject it.
  Brief 224: every request streams (``"stream": true``, server-sent events read with the same ``urllib`` call), so a long reply is not
  killed by ``timeout_s`` (which is then the idle time between two events, not the length of the reply). A stream that drops, or
  that ends without ``message_stop``, is asked for again once (``retries``) and then raised as an error, never returned as a reply.
- :class:`ClaudeCodeChat`: a messages -> Reply adapter over one tool-less headless ``claude -p`` call (the subscription's
  "API-like mode"), for call sites that only need text.

Keys come from the environment variable the endpoint names (``key_env``), never from the configuration; the OpenRouter key
may also come from the owner's mode-600 file, as before. A key is never printed, logged or recorded.
"""

from __future__ import annotations

import http.client
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


def anthropic_key_file() -> Path:
    """The owner's Anthropic key file (brief 209a), outside the repository; HOME is read at call time."""
    return Path.home() / ".config" / "fpga_design_agent" / "anthropic.env"


def _key_from_file(name: str = "OPENROUTER_API_KEY", path: Path | None = None) -> str | None:
    """``NAME=...`` from a local key file (outside the repo, mode 600); never printed."""
    path = path or KEY_FILE
    try:
        if path.stat().st_mode & 0o077:
            raise ValueError(f"{path} must be readable by its owner only (chmod 600)")
        for line in path.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip() or None
    except FileNotFoundError:
        return None
    return None


def read_key(key_env: str | None) -> str | None:
    """The key named by ``key_env`` (an environment variable name); the OpenRouter key may come from the owner's key file."""
    if not key_env:
        return None
    if os.environ.get(key_env):
        return os.environ[key_env]
    if key_env == "OPENROUTER_API_KEY":
        return _key_from_file()
    if key_env == "ANTHROPIC_API_KEY":                  # brief 209a: the same owner key-file route, its own file
        return _key_from_file("ANTHROPIC_API_KEY", anthropic_key_file())
    return None


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


_WARNED_NO_PRICE: set[str] = set()


def usage_cost(usage: dict[str, Any], price: dict[str, float] | None) -> float | None:
    """USD of one call from the response ``usage`` and a price table (USD per million tokens); None when the model has no price.
    A price with no cache prices derives them from ``input`` (write 1.25x, read 0.10x)."""
    if not price:
        return None
    from agent.models.config import CACHE_READ_RATIO, CACHE_WRITE_RATIO
    p_in, p_out = float(price["input"]), float(price["output"])
    p_w = float(price["cache_write"]) if price.get("cache_write") is not None else p_in * CACHE_WRITE_RATIO
    p_r = float(price["cache_read"]) if price.get("cache_read") is not None else p_in * CACHE_READ_RATIO
    n = lambda k: int(usage.get(k) or 0)                                   # noqa: E731
    return round((n("input_tokens") * p_in + n("output_tokens") * p_out + n("cache_creation_input_tokens") * p_w
                  + n("cache_read_input_tokens") * p_r) / 1e6, 8)


class StreamDropped(RuntimeError):
    """A streamed reply that ended early, carried an error event, or could not be assembled (brief 224)."""


#: error events of a stream that are worth one more attempt (the API's overloaded and internal errors); any other is raised at once
_RETRY_STREAM_ERRORS = ("overloaded_error", "api_error")


def assemble_stream(lines) -> dict[str, Any]:
    """The Messages API's server-sent events, as the non-streaming response body (``content``, ``usage``, ``stop_reason``). ``lines`` is
    anything that yields the response lines (bytes or str). Usage: ``message_start`` carries the input and cache tokens, each
    ``message_delta`` the output tokens so far; the last value of each field wins. Raises :class:`StreamDropped` when the stream has an
    error event, ends before ``message_stop``, or a tool call that was not cut off at the limit has arguments that are not JSON."""
    blocks: dict[int, dict[str, Any]] = {}
    usage: dict[str, int] = {}
    details: dict[str, int] = {}
    stop: str | None = None
    done = False
    for raw in lines:
        line = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw).strip()
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except ValueError:
            raise StreamDropped("a stream event was not JSON") from None
        t = ev.get("type")
        if t == "message_start":
            usage.update({k: int(v) for k, v in ((ev.get("message") or {}).get("usage") or {}).items() if isinstance(v, int)})
        elif t == "content_block_start":
            b = dict(ev.get("content_block") or {})
            if b.get("type") == "tool_use":
                b["_json"] = ""
            elif b.get("type") == "thinking":
                b["_chars"] = len(b.get("thinking") or "")                           # brief 234: thinking is not kept, only counted
            elif b.get("type") == "text":
                b["text"] = b.get("text") or ""
            blocks[int(ev.get("index", len(blocks)))] = b
        elif t == "content_block_delta":
            b = blocks.get(int(ev.get("index", -1)))
            d = ev.get("delta") or {}
            if b is None:
                continue
            if d.get("type") == "text_delta" and b.get("type") == "text":
                b["text"] += d.get("text") or ""
            elif d.get("type") == "input_json_delta" and b.get("type") == "tool_use":
                b["_json"] += d.get("partial_json") or ""
            elif d.get("type") == "thinking_delta" and b.get("type") == "thinking":
                b["_chars"] = b.get("_chars", 0) + len(d.get("thinking") or "")
            # thinking and signature deltas are not kept: a reply's thinking is not replayed to the next call
        elif t == "message_delta":
            stop = (ev.get("delta") or {}).get("stop_reason") or stop
            usage.update({k: int(v) for k, v in (ev.get("usage") or {}).items() if isinstance(v, int)})
            det = (ev.get("usage") or {}).get("output_tokens_details")                 # brief 234: the API's own thinking-token count, when it gives one
            if isinstance(det, dict) and isinstance(det.get("thinking_tokens"), int):
                details["thinking_tokens"] = det["thinking_tokens"]
        elif t == "message_stop":
            done = True
        elif t == "error":
            err = ev.get("error") or {}
            e = StreamDropped(f"stream error event: {err.get('type')}: {str(err.get('message'))[:200]}")
            e.retry = err.get("type") in _RETRY_STREAM_ERRORS                       # type: ignore[attr-defined]
            raise e
    if not done:
        raise StreamDropped("the stream ended before message_stop")
    content: list[dict[str, Any]] = []
    thinking = {"blocks": sum(1 for b in blocks.values() if b.get("type") == "thinking"),
                "chars": sum(b.get("_chars", 0) for b in blocks.values() if b.get("type") == "thinking")}
    for i in sorted(blocks):
        b = blocks[i]
        if b.get("type") == "tool_use":
            try:
                b["input"] = json.loads(b.pop("_json") or "{}")
            except ValueError:
                if stop != "max_tokens":                                              # a call cut off at the limit is dropped by the caller
                    raise StreamDropped("a tool call's arguments were not complete JSON") from None
                b["input"] = {}
            content.append(b)
        elif b.get("type") == "text":
            content.append(b)
    visible = sum(len(b.get("text") or "") for b in content if b.get("type") == "text") + sum(
        len(json.dumps(b.get("input") or {})) for b in content if b.get("type") == "tool_use")
    return {"content": content, "usage": usage, "stop_reason": stop, "output_details": details,
            "thinking": thinking, "visible_chars": visible}


class AnthropicClient:
    """The Messages API over plain HTTPS, streamed. ``opener`` is the injection point of the tests."""

    def __init__(self, model: str, *, base_url: str = "https://api.anthropic.com", key_env: str | None = "ANTHROPIC_API_KEY", timeout_s: float = 180.0,
                 temperature: float | None = 0.2, max_tokens: int = 8192, stop: list[str] | None = None, thinking_budget: int | None = None,
                 retries: int = 1, opener=None, effort: str | None = None, price: dict[str, float] | None = None, accepts_temperature: bool = True, cache: bool = True):
        self.price, self.accepts_temperature, self.cache, self.effort = price, accepts_temperature, cache, effort          # brief 209b
        self.model, self.base_url, self.timeout_s, self.retries = model, base_url.rstrip("/"), timeout_s, retries
        self.temperature, self.max_tokens, self.stop, self.thinking_budget = temperature, max_tokens, stop, thinking_budget
        self._key = read_key(key_env)
        if not self._key and opener is None:
            raise ValueError(f"{key_env} is not set" + (f" and {anthropic_key_file()} has none" if key_env == "ANTHROPIC_API_KEY" else ""))
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

    CACHE = {"type": "ephemeral"}                    # the 5-minute cache entry (Messages API: ``cache_control`` on a content block)

    @classmethod
    def mark_cache(cls, system: str, msgs: list[dict], tl: list[dict]) -> tuple[Any, list[dict], list[dict]]:
        """Prompt caching markers (brief 209b), at most 4 per request (the API limit): the last tool definition and the system block
        (the prefix is rendered tools, then system, then messages), the last block of the last message (the conversation so far), and
        the last block of the user turn before the previous assistant turn, which is where the previous call wrote its entry, so a call
        that appends more than 20 blocks still finds it. Empty text blocks cannot carry a marker and are skipped."""
        def mark(m: dict) -> None:
            c = m["content"]
            if isinstance(c, str):
                if not c:
                    return
                m["content"] = c = [{"type": "text", "text": c}]
            if c and not (c[-1].get("type") == "text" and not c[-1].get("text")):
                c[-1] = {**c[-1], "cache_control": dict(cls.CACHE)}
        if tl:
            tl = [*tl[:-1], {**tl[-1], "cache_control": dict(cls.CACHE)}]
        msgs = [dict(m, content=[dict(b) for b in m["content"]] if isinstance(m["content"], list) else m["content"]) for m in msgs]
        if msgs:
            mark(msgs[-1])
            if len(msgs) >= 3 and msgs[-3]["role"] == "user":
                mark(msgs[-3])
        sysb: Any = [{"type": "text", "text": system, "cache_control": dict(cls.CACHE)}] if system else system
        return sysb, msgs, tl

    def __call__(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        t0 = time.monotonic()
        system, msgs, tl = self.to_anthropic(messages, tools)
        if self.cache:
            system, msgs, tl = self.mark_cache(system, msgs, tl)
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "messages": msgs, "stream": True}      # brief 224: always streamed
        if system:
            body["system"] = system
        if tl:
            body["tools"] = tl
        if self.stop:
            body["stop_sequences"] = list(self.stop)
        if self.effort:                                  # Messages API: output_config.effort (GA, no beta header); thinking stays adaptive (omitted)
            body["output_config"] = {"effort": self.effort}
        if self.thinking_budget:
            body["thinking"] = {"type": "enabled", "budget_tokens": int(self.thinking_budget)}
        elif self.temperature is not None and self.accepts_temperature:      # per-model rule of the config, never a caught 400
            body["temperature"] = self.temperature
        req = urllib.request.Request(f"{self.base_url}/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                              "x-api-key": self._key or ""})
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with self._open(req, timeout=self.timeout_s) as resp:
                    d = assemble_stream(resp)
                break
            except urllib.error.HTTPError as e:
                last = RuntimeError(f"Anthropic API HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
                if e.code < 500 and e.code != 429:
                    raise last from None
            except StreamDropped as e:                                                # brief 224: a dropped stream is retried, then an error
                self.stream_drops = getattr(self, "stream_drops", 0) + 1
                print(f"FDA_STREAM_DROPPED attempt {attempt + 1}: {e}", file=sys.stderr, flush=True)
                last = RuntimeError(f"Anthropic API stream dropped: {e}")
                if getattr(e, "retry", True) is False:
                    raise last from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                last = RuntimeError(f"Anthropic API unreachable: {type(e).__name__}")
        else:
            raise last or RuntimeError("Anthropic API call failed")
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in d.get("content", []) if b.get("type") == "tool_use"]
        u = d.get("usage") or {}
        cost = usage_cost(u, self.price)
        if cost is None and self.model not in _WARNED_NO_PRICE:
            _WARNED_NO_PRICE.add(self.model)
            print(f"FDA_NO_PRICE: no price for model {self.model!r} in the model config (models: <name>: price:); every call counts at the "
                  "per-call cost ceiling", file=sys.stderr, flush=True)
        i, w, r = (int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        stop = d.get("stop_reason")
        if stop == "max_tokens":
            # brief 209b: a reply cut off at max_tokens (thinking plus text) is a failed attempt, not retried at the same cap and not retried
            # larger (above ~16000 the API wants streaming). A cut-off tool call has incomplete arguments, so it is dropped, and the role is told.
            calls = []
            text = (text + "\n\n" if text else "") + (f"[the reply was cut off at the output limit of {self.max_tokens} tokens (thinking counts), so any tool call "
                                                      "in it was dropped: do less in one reply: write one file per tool call, smallest first, then continue]")
            print(f"FDA_TRUNCATED: {self.model} reply stopped at max_tokens={self.max_tokens}", file=sys.stderr, flush=True)
        return Reply(text=text, tool_calls=calls, prompt_tokens=i + w + r, completion_tokens=int(u.get("output_tokens") or 0), cost=cost,
                     seconds=round(time.monotonic() - t0, 2), provider="anthropic", input_tokens=i, cache_write_tokens=w, cache_read_tokens=r,
                     cost_basis="usage*price" if cost is not None else None, stop_reason=stop, stream_retries=attempt,
                     thinking_tokens=(d.get("output_details") or {}).get("thinking_tokens"),
                     thinking_blocks=(d.get("thinking") or {}).get("blocks", 0), visible_chars=int(d.get("visible_chars") or 0))


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
