"""The resolver: the one object every model call goes through (brief 108).

Call sites ask for a *purpose* (``rtl``, ``oracle``, ``spectest`` ...), optionally a stage, and get back a callable. The
resolver looks the purpose up in the :class:`~agent.models.config.Table`, builds the right client for the endpoint kind, and
writes one row per call to ``model_calls.jsonl`` in the run directory: the purpose, endpoint, kind, model, the hash of the
resolved entry and of the whole table, the tokens and the provider-reported cost. A row never holds a key, a prompt or a reply.

A purpose moves to another endpoint by editing the table, not the code: the same call site gets a Claude Code call, an
Anthropic API call, an OpenRouter call, a local OpenAI-compatible server or a recorded reply.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, Callable

from agent.models import claude_cli
from agent.models.config import ConfigError, Entry, Table, build_table, parse_cli_json


class _Logged:
    """A client with one ``model_calls.jsonl`` row per call; every attribute of the client (``model``) still shows through."""

    def __init__(self, inner: Callable, entry: Entry, owner: "Resolver"):
        self._inner, self.entry, self._owner = inner, entry, owner

    @property
    def model(self) -> str | None:
        return self.entry.model

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __call__(self, messages: list[dict], tools: list[dict] | None = None):
        t0 = time.monotonic()
        o = self._owner
        if o.tape is not None:                       # brief 107: record the reply, or (replay) serve it without any live call
            r = o.tape.call(self.entry, messages, tools, lambda: o.live_check(self.entry) or self._inner(messages, tools))
        else:
            o.live_check(self.entry)
            r = self._inner(messages, tools)
        o.log_call(self.entry, r, time.monotonic() - t0)
        return r


class Resolver:
    def __init__(self, table: Table, *, run_dir: Path | None = None, injected: Callable | None = None, replay: Path | str | None = None,
                 record: Path | str | None = None, factory: Callable[[Entry], Callable] | None = None, tape: Any = None, level1: bool = False):
        """``injected``: one client served for every chat-style call (tests); ``replay``: a recorded fixture served instead of any
        chat endpoint; ``record``: record the chat calls to this fixture; ``factory``: builds the client of an entry (tests)."""
        self.table = table
        self.run_dir = Path(run_dir) if run_dir else None
        self.injected, self.replay_path, self.record_path, self.factory = injected, Path(replay) if replay else None, record, factory
        self._clients: dict[tuple, Callable] = {}
        self.seq = 0
        self.tape = tape                          # brief 107: a record/replay tape (agent.models.tape.Tape), or None
        self.level1 = level1                      # brief 107: --deterministic at level 1: every live call must be at temperature 0

    def live_check(self, e: Entry) -> None:
        """Level 1 runtime guard: a live call whose entry is not at temperature 0 on a kind that takes one is refused, never sampled."""
        if not self.level1:
            return
        from agent.models.determinism import LEVEL1_KINDS
        from agent.models.tape import DeterminismError
        if e.kind not in LEVEL1_KINDS or e.options.get("temperature") != 0:
            raise DeterminismError(f"--deterministic (level 1): the {e.purpose}{'@' + e.stage if e.stage else ''} call on endpoint {e.endpoint!r} "
                                   f"({e.kind}) would not run at temperature 0; refused instead of sampling")

    def unreplayable(self, what: str) -> None:
        """A call a tape cannot hold (a claude_code sub-agent turn): counted when recording, refused on replay and at level 1."""
        from agent.models.tape import DeterminismError
        if self.level1:
            raise DeterminismError(f"--deterministic (level 1): {what} is a claude_code sub-agent turn, which has no temperature setting")
        if self.tape is not None:
            self.tape.note_unreplayable(what)

    # -- the table -------------------------------------------------------------------------------------------------
    def entry(self, purpose: str, stage: str | None = None, overrides: dict[str, Any] | None = None) -> Entry:
        e = self.table.entry(purpose, stage)
        if not overrides:
            return e
        from agent.models.config import SUPPORTS
        bad = [o for o in overrides if o not in SUPPORTS[e.kind]["options"]]
        if bad:
            raise ConfigError(f"{purpose}: call option(s) {bad} are not supported by endpoint kind {e.kind!r}")
        return Entry(e.purpose, e.stage, e.endpoint, e.kind, e.model, {**e.options, **overrides}, e.note, e.base_url, e.key_env, e.host_class,
                     e.path, dict(e.sources))

    def agent_spec(self, role: str, stage: str | None = None) -> dict[str, Any]:
        """The legacy view of a role: ``{harness, model, effort}`` (harness claude_code for that kind, else deepagents)."""
        from agent.models.config import ROLE_PURPOSE
        e = self.table.entry(ROLE_PURPOSE[role], stage)
        return {"harness": "claude_code" if e.kind == "claude_code" else "deepagents", "model": e.model, "effort": e.options.get("effort")}

    # -- records ---------------------------------------------------------------------------------------------------
    def log_call(self, e: Entry, r: Any, seconds: float) -> None:
        if self.run_dir is None:
            return
        self.seq += 1
        row = {"seq": self.seq, **({"tape": self.tape.mode} if self.tape is not None else {}), "purpose": e.purpose, **({"stage": e.stage} if e.stage else {}), "endpoint": e.endpoint, "kind": e.kind,
               "model": e.model, "entry_hash": e.hash, "table_hash": self.table.hash,
               "prompt_tokens": getattr(r, "prompt_tokens", None), "completion_tokens": getattr(r, "completion_tokens", None),
               "cost_usd": getattr(r, "cost", None), "seconds": round(seconds, 2),
               **({"input_tokens": r.input_tokens, "cache_write_tokens": r.cache_write_tokens, "cache_read_tokens": r.cache_read_tokens,
                   "cost_basis": r.cost_basis, "stop_reason": r.stop_reason, "stream_retries": getattr(r, "stream_retries", 0)} if e.kind == "anthropic_api" and hasattr(r, "cache_read_tokens") else {})}
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with (self.run_dir / "model_calls.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        if self.tape is not None:
            (self.run_dir / "model_tape.json").write_text(json.dumps(self.tape.state(), indent=1))

    def log_text_call(self, e: Entry, seconds: float, *, tokens: int | None = None, plan_estimate: Any = None) -> None:
        """One row for a call made as plain text (a headless Claude Code call): the cost is the plan's, never dollars."""
        class _R:
            prompt_tokens, completion_tokens, cost = tokens, None, "unreported"
        self.log_call(e, _R, seconds)

    # -- chat-style clients ----------------------------------------------------------------------------------------
    def chat(self, purpose: str, stage: str | None = None, *, overrides: dict[str, Any] | None = None, label: str | None = None) -> Callable:
        """``client(messages, tools=None) -> Reply`` for the purpose, whatever its endpoint kind."""
        e = self.entry(purpose, stage, overrides)
        if e.model is None:
            raise ConfigError(f"purpose {purpose!r} has no model configured (it is off); set one in models.yaml")
        return _Logged(self._client(e, label), e, self)

    def _client(self, e: Entry, label: str | None) -> Callable:
        if self.tape is not None and self.tape.mode == "replay":
            return self._no_live
        if e.kind != "claude_code" and self.injected is not None:
            return self.injected
        if e.kind != "claude_code" and self.replay_path is not None:
            return self._cached(("replay", str(self.replay_path)), lambda: self._replay(self.replay_path))
        if e.kind == "replay":
            if not e.path:
                raise ConfigError(f"{e.purpose}: a replay endpoint needs path: <recorded fixture>")
            return self._cached(("replay", e.path), lambda: self._replay(Path(e.path)))
        if self.table.work_marked(e):
            raise ConfigError(f"{e.purpose}: endpoint {e.endpoint!r} is marked work hardware: refused for live calls")
        key = (e.kind, e.endpoint, e.model, json.dumps(e.options, sort_keys=True), e.base_url, label if e.kind == "claude_code" else None)
        return self._cached(key, lambda: self._build(e, label))

    def _cached(self, key: tuple, make: Callable[[], Callable]) -> Callable:
        if key not in self._clients:
            self._clients[key] = make()
        return self._clients[key]

    @staticmethod
    def _no_live(messages, tools=None):
        from agent.models.tape import DeterminismError
        raise DeterminismError("replay: a live model call was attempted (the tape should have served it)")

    def text_result(self, e: Entry, system: str, user: str, *, timeout_s: float, effort: str | None, prefix: str) -> dict[str, Any]:
        """One headless ``claude -p`` text call, through the tape when there is one (record, or replay without calling the CLI)."""
        def live() -> dict[str, Any]:
            self.live_check(e)
            return claude_cli.text_call(system, user, model=e.model, effort=effort, timeout_s=timeout_s, prefix=prefix)
        if self.tape is not None:
            return self.tape.call_result(e, [{"role": "system", "content": system}, {"role": "user", "content": user}], live)
        return live()

    @staticmethod
    def _replay(path: Path) -> Callable:
        from agent.graph.llm import Replay
        return Replay(path)

    def _build(self, e: Entry, label: str | None) -> Callable:
        if self.factory is not None:
            return self.factory(e)
        o = e.options
        client: Callable
        if e.kind in ("openrouter", "openai_compatible"):
            from agent.models.endpoints import OpenRouterClient
            params = {k: o[k] for k in ("seed", "max_tokens", "stop") if k in o}
            if "effort" in o:
                params["effort"] = o["effort"]
            client = OpenRouterClient(e.model, o.get("timeout_s", 180), base_url=e.base_url or "https://openrouter.ai/api/v1",
                                      key_env=e.key_env, temperature=o.get("temperature"), retries=int(o.get("retries", 1)), params=params)
        elif e.kind == "anthropic_api":
            from agent.models.endpoints import AnthropicClient
            client = AnthropicClient(e.model, base_url=e.base_url or "https://api.anthropic.com", key_env=e.key_env,
                                     timeout_s=o.get("timeout_s", 180), temperature=o.get("temperature"), max_tokens=int(o.get("max_tokens", 8192)),
                                     stop=o.get("stop"), thinking_budget=o.get("thinking_budget"), retries=int(o.get("retries", 1)), effort=o.get("effort"),
                                     price=self.table.model_rule(e.model)["price"], accepts_temperature=self.table.model_rule(e.model)["temperature"])
        elif e.kind == "claude_code":
            from agent.models.endpoints import ClaudeCodeChat
            client = ClaudeCodeChat(e.model, effort=o.get("effort"), timeout_s=o.get("timeout_s", 900),
                                    log=(self.run_dir / "claude_code_calls.jsonl") if self.run_dir else None, label=label or e.purpose)
        else:
            raise ConfigError(f"{e.purpose}: no client for endpoint kind {e.kind!r}")
        if self.record_path:
            from agent.graph.llm import Recorder
            client = Recorder(client, Path(self.record_path))
        return client

    # -- text calls (system, user) -> text -------------------------------------------------------------------------
    def text(self, purpose: str, stage: str | None = None, *, overrides: dict[str, Any] | None = None, label: str | None = None,
             claude_log: Path | None = None, on_reply: Callable[[Any], None] | None = None, timeout_s: float | None = None) -> Callable[[str, str], str]:
        """``llm(system, user) -> text``. On a claude_code endpoint it is one tool-less headless call logged to ``claude_log`` in the
        ``claude_code_calls.jsonl`` format (so the run's plan-cost estimate counts it); elsewhere one chat call, reported to ``on_reply``
        (the run's meter)."""
        e = self.entry(purpose, stage, overrides)
        if e.model is None:
            raise ConfigError(f"purpose {purpose!r} has no model configured (it is off); set one in models.yaml")
        label = label or purpose
        if e.kind == "claude_code":
            if self.table.work_marked(e):
                raise ConfigError(f"{purpose}: endpoint {e.endpoint!r} is marked work hardware: refused for live calls")
            return self._cc_text(e, label, claude_log if claude_log is not None else (self.run_dir / "claude_code_calls.jsonl" if self.run_dir else None),
                                 timeout_s or e.options.get("timeout_s", 900))
        client = self.chat(purpose, stage, overrides=overrides, label=label)

        def llm(system: str, user: str) -> str:
            r = client([{"role": "system", "content": system}, {"role": "user", "content": user}])
            if on_reply is not None:
                on_reply(r)
            return r.text
        return llm

    def _cc_text(self, e: Entry, label: str, log: Path | None, timeout_s: float) -> Callable[[str, str], str]:
        effort = e.options.get("effort")

        def llm(system: str, user: str) -> str:
            from agent.graph.run import ArmBlocked
            t0 = time.time()
            res = self.text_result(e, system, user, timeout_s=timeout_s, effort=effort, prefix=f"fda_{label}_")
            if log is not None:
                u = res.get("usage") or {}
                tok = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
                with log.open("a") as f:
                    f.write(json.dumps({"tag": f"{label}", "role": label, "stage": "rtl-design-creation", "model_requested": e.model,
                                        "purpose": e.purpose, "endpoint": e.endpoint, "entry_hash": e.hash, "table_hash": self.table.hash,
                                        "effort": effort or "cli-default", "claude_code_version": None, "turns": res.get("num_turns"),
                                        "wall_s": round(time.time() - t0, 1), "is_error": res.get("is_error"), "tokens": tok,
                                        "cost_usd": "unreported", "plan_cost_estimate_usd": res.get("total_cost_usd")}) + "\n")
            self.log_text_call(e, time.time() - t0, tokens=None)
            if res.get("is_error") and any(k in str(res.get("result", "")).lower() for k in ("login", "authenticat", "oauth", "401")):
                raise ArmBlocked("Claude Code could not authenticate: " + str(res.get("result", ""))[:200])
            return str(res.get("result", ""))
        return llm

    # -- the interview oracle --------------------------------------------------------------------------------------
    def oracle(self) -> Callable[[str, str], dict[str, Any]]:
        """The user simulator: ``llm(system, user) -> {"answer", "quote"}``."""
        e = self.entry("oracle")
        if e.kind == "claude_code":
            from agent.claude_code_arm.oracle import cc_oracle
            return cc_oracle(e.model, (self.run_dir / "oracle_calls.jsonl") if self.run_dir else None, entry=e, resolver=self)
        client = self.chat("oracle")

        def llm(system: str, user: str) -> dict[str, Any]:
            r = client([{"role": "system", "content": system}, {"role": "user", "content": user}])
            try:
                return json.loads(r.text.strip().removeprefix("```json").removesuffix("```"))
            except ValueError:
                return {"answer": "not specified", "quote": None}
        return llm

    # -- checking ---------------------------------------------------------------------------------------------------
    def probe(self, purposes: list[str] | None = None) -> list[dict[str, Any]]:
        """One minimal call per distinct endpoint+model in use (this spends tokens: the caller asks for it). Returns one row each."""
        seen: dict[tuple, str] = {}
        rows = []
        for e in self.table.entries():
            if e.model is None or e.stage or (purposes and e.purpose not in purposes):
                continue
            k = (e.endpoint, e.kind, e.model)
            if k in seen:
                continue
            seen[k] = e.purpose
            t0 = time.time()
            try:
                if e.kind == "claude_code":
                    out = claude_cli.text_call("Reply with the single word ok.", "ok?", model=e.model, effort="low", timeout_s=120, prefix="fda_probe_")
                    ok, detail = bool(out) and not out.get("is_error"), str(out.get("result", ""))[:40]
                elif e.kind == "replay":
                    ok, detail = bool(e.path and Path(e.path).is_file()), "fixture present"
                else:
                    small = self.entry(e.purpose, None, {"max_tokens": 1} if "max_tokens" in __import__("agent.models.config", fromlist=["x"]).SUPPORTS[e.kind]["options"] else None)
                    r = self._client(small, None)([{"role": "user", "content": "ok"}], None)
                    ok, detail = True, f"{getattr(r, 'prompt_tokens', 0)}+{getattr(r, 'completion_tokens', 0)} tokens"
            except Exception as ex:                      # report any failure as a row; never include a message that could carry a key
                ok, detail = False, f"{type(ex).__name__}"
            rows.append({"purpose": e.purpose, "endpoint": e.endpoint, "kind": e.kind, "model": e.model, "ok": ok, "detail": detail,
                         "seconds": round(time.time() - t0, 1)})
        return rows


# --- convenience for single-shot scripts ---------------------------------------------------------------------------------


def resolver_for(purpose: str | tuple[str, ...], *, model: str | None = None, endpoint: str | None = None, timeout_s: float | None = None,
                 replay: Path | str | None = None, record: Path | str | None = None, run_dir: Path | None = None,
                 project_file: Path | None = None, extra: dict[str, Any] | None = None, options: dict[str, Any] | None = None,
                 command: dict[str, Any] | None = None) -> Resolver:
    """A resolver for a script or a tool that makes calls for one purpose: the user and project files apply, and ``model`` (the
    script's own ``--model`` flag, an alias) overrides the table for that purpose. Without ``endpoint`` the table's endpoint stays."""
    ent: dict[str, Any] = {}
    purposes = (purpose,) if isinstance(purpose, str) else tuple(purpose)
    if model:
        ent["model"] = model
    if endpoint:
        ent["endpoint"] = endpoint
    if timeout_s is not None or options:
        ent["options"] = {**({"timeout_s": timeout_s} if timeout_s is not None else {}), **(options or {})}
    cli: dict[str, Any] = {"purposes": {p: copy.deepcopy(ent) for p in purposes} if ent else {}}
    if extra:
        cli = parse_cli_json({**cli, **extra})
    table = build_table(project_file=project_file, cli=cli if cli["purposes"] or extra else None, command=command, replay=replay is not None)
    return Resolver(table, run_dir=run_dir, replay=replay, record=record)


def chat_client(purpose: str, **kw: Any) -> Callable:
    """``client(messages, tools=None) -> Reply`` for a script's purpose (see :func:`resolver_for`)."""
    stage = kw.pop("stage", None)
    return resolver_for(purpose, **kw).chat(purpose, stage)
