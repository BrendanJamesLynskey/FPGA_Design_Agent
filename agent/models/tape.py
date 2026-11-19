"""Record and replay of every model call (brief 107, level 2).

A **tape** is a directory holding ``tape.jsonl``: one row per model call, keyed by the SHA-256 of the *resolved request* (purpose,
stage, endpoint, kind, model, the call options, the messages and the tool schemas). A replay run serves each call from the tape by
that key (the n-th call with a key gets the n-th recorded reply for it), so whatever the provider would do, the run sees the same
model output it saw when it was recorded. A call with no recording is an error, never a live call and never a guess
(:class:`DeterminismError`).

What a row holds: the key, the purpose, endpoint, model and options, one hash per message, and the reply (text, tool calls, token
counts, provider). **Not the messages.** The prompts are private (brief 99), so only their hashes are stored; the reply is model
output, which can quote private text, so a tape is a *private* store: it must live outside the repository or in a git-ignored path
(:func:`Tape.open` refuses a tracked location), and nothing that looks like a key is ever written.

Paths: a run's directory, run id and the repository path differ between runs and appear in tool results, so they are replaced by
placeholders before hashing and before storing, and put back on replay. ``timeout_s`` and ``retries`` are not part of the key (they
do not change what the model says).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

SCHEMA = 1
KEY_IGNORED_OPTIONS = ("timeout_s", "retries")
_REPLY_FIELDS = ("text", "tool_calls", "prompt_tokens", "completion_tokens", "provider")
_KEY_PATTERNS = (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), re.compile(r"(?i)bearer\s+\S{12,}"), re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
                 re.compile(r"github_pat_[A-Za-z0-9_]{16,}"), re.compile(r"AKIA[0-9A-Z]{16}"), re.compile(r"hf_[A-Za-z0-9]{20,}"),
                 re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
                 re.compile(r"(?i)(api[_-]?key|secret|token|authorization)\s*[:=]\s*\S{8,}"))


class DeterminismError(RuntimeError):
    """A deterministic or replay run cannot continue exactly: it is stopped rather than sampled or guessed."""


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class Tape:
    def __init__(self, root: Path | str, mode: str, subs: list[tuple[str, str]] | None = None):
        if mode not in ("record", "replay"):
            raise ValueError(mode)
        self.root, self.mode = Path(root), mode
        # (value, placeholder), longest value first, so a path inside a longer path is not cut
        self.subs = sorted([(v, t) for v, t in (subs or []) if v], key=lambda p: -len(p[0]))
        self.file = self.root / "tape.jsonl"
        self.served = self.live = self.misses = 0
        self.record_failures = 0                 # recordings that could not be stored after the live call (the tape is then incomplete)
        self.unreplayable = 0                    # calls a tape cannot hold (a claude_code sub-agent turn), counted in record mode
        self._seen: dict[str, int] = {}
        self._rows: dict[str, list[dict]] = {}
        if mode == "replay":
            if not self.file.is_file():
                raise DeterminismError(f"no recording at {self.file}")
            for line in self.file.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    raise DeterminismError(f"{self.file} is damaged (a line is not JSON; a killed recording?)") from None
                self._rows.setdefault(r["key"], []).append(r)
            self.header = self._rows.pop("__header__", [{}])[0]
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            self.header = {}
            if self.file.is_file() and self.file.stat().st_size:
                raise DeterminismError(f"{self.file} already holds a recording: appending would duplicate request keys; use a new --tape directory or replay it")

    # -- privacy ---------------------------------------------------------------------------------------------------
    @staticmethod
    def check_location(root: Path) -> None:
        """A tape holds model output that can quote private prompts: refuse a path git would track."""
        root = Path(root).resolve()
        d = root
        while not d.exists():                       # the nearest existing ancestor: a new nested path is still inside the checkout
            d = d.parent
        try:
            top = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
        except OSError:
            return
        if not top:
            return                                                       # not inside a git checkout
        rel = str(root.relative_to(Path(top).resolve()))
        ignored = subprocess.run(["git", "-C", top, "check-ignore", "-q", "--", rel + "/tape.jsonl"], capture_output=True).returncode == 0
        if not ignored:
            raise DeterminismError(f"{root} is inside a git checkout and not git-ignored: a tape holds model output that can quote private prompts, "
                                   "so it must live outside the repository or under a git-ignored path (runs/ is ignored)")

    @classmethod
    def open(cls, root: Path | str, mode: str, subs: list[tuple[str, str]] | None = None, **header: Any) -> "Tape":
        cls.check_location(Path(root))
        t = cls(root, mode, subs)
        if mode == "record" and not t.file.exists():
            t._append({"key": "__header__", "schema": SCHEMA, **header})
        return t

    # -- keys ------------------------------------------------------------------------------------------------------
    def _norm(self, text: str) -> str:
        text = text.replace("<<", "<<lt>>")             # a literal placeholder-looking string must survive the round trip
        for v, tok in self.subs:
            text = text.replace(v, tok)
        return text

    def _denorm(self, text: str) -> str:
        for v, tok in self.subs:
            text = text.replace(tok, v)
        return text.replace("<<lt>>", "<<")

    def request(self, e: Any, messages: list[dict], tools: list[dict] | None) -> dict[str, Any]:
        opts = {k: v for k, v in sorted(e.options.items()) if k not in KEY_IGNORED_OPTIONS}
        body = json.loads(self._norm(json.dumps({"messages": messages, "tools": tools or []}, sort_keys=True, ensure_ascii=False, default=str)))
        meta = {"purpose": e.purpose, "stage": e.stage, "endpoint": e.endpoint, "kind": e.kind, "model": e.model, "options": opts}
        return {"key": sha({**meta, **body}), **meta, "messages_sha256": [sha(m) for m in body["messages"]], "tools_sha256": sha(body["tools"])}

    # -- the call --------------------------------------------------------------------------------------------------
    def call(self, e: Any, messages: list[dict], tools: list[dict] | None, live: Callable[[], Any]) -> Any:
        """A chat-style call: ``live()`` returns a ``Reply``. Record mode calls it and stores the reply; replay mode never calls it."""
        from agent.graph.llm import Reply
        req = self.request(e, messages, tools)
        if self.mode == "replay":
            row = self._take(req)
            r = json.loads(self._denorm(json.dumps(row["reply"])))
            return Reply(text=r["text"], tool_calls=r["tool_calls"], prompt_tokens=r["prompt_tokens"], completion_tokens=r["completion_tokens"],
                         cost=0.0, seconds=0.0, provider=f"replay:{r.get('provider')}")
        reply = live()
        self.live += 1
        self._store(req, {f: getattr(reply, f, None) for f in _REPLY_FIELDS})
        return reply

    def call_result(self, e: Any, messages: list[dict], live: Callable[[], dict]) -> dict:
        """A headless text call: ``live()`` returns the parsed result dict of ``claude -p`` (``result``, ``usage``, ...)."""
        req = self.request(e, messages, None)
        keep = ("result", "is_error", "num_turns", "usage", "total_cost_usd")
        if self.mode == "replay":
            row = self._take(req)
            return json.loads(self._denorm(json.dumps(row["reply"])))
        res = live()
        self.live += 1
        self._store(req, {k: res.get(k) for k in keep if k in res})
        return res

    def note_unreplayable(self, what: str) -> None:
        if self.mode == "replay":
            raise DeterminismError(f"{what}: a claude_code sub-agent turn runs its own tool loop inside the CLI and cannot be recorded or replayed; "
                                   "put this role on a chat endpoint (openrouter, openai_compatible, anthropic_api) to get an exact replay")
        self.unreplayable += 1

    def _take(self, req: dict) -> dict:
        k = req["key"]
        n = self._seen.get(k, 0)
        rows = self._rows.get(k, [])
        if n >= len(rows):
            self.misses += 1
            near = [r for rs in self._rows.values() for r in rs if r["purpose"] == req["purpose"] and r.get("stage") == req["stage"]]
            def first_diff(r: dict) -> int:
                a, b = r["messages_sha256"], req["messages_sha256"]
                return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            best = max(near, key=lambda r: (first_diff(r), -abs(len(r["messages_sha256"]) - len(req["messages_sha256"]))), default=None)
            hint = ""
            if best is not None:
                same_meta = all(best[f] == req[f] for f in ("endpoint", "kind", "model", "options"))
                hint = (f" Closest recording: messages agree up to message #{first_diff(best)} of {len(req['messages_sha256'])}"
                        f"{'' if same_meta else '; its model, endpoint or options differ'}{'' if best['tools_sha256'] == req['tools_sha256'] else '; its tool schemas differ'}.")
            why = ("every recorded reply for this request was already served (the run made more calls than the recording)" if rows else
                   f"no recording has this request ({len(near)} recorded for purpose {req['purpose']}"
                   + (f"@{req['stage']}" if req["stage"] else "") + "; the messages, options, model or endpoint differ from the recorded run)." + hint)
            raise DeterminismError(f"replay miss for {req['purpose']}{'@' + req['stage'] if req['stage'] else ''} (request {k[:12]}, "
                                   f"{sum(self._seen.values())} calls served so far): {why.rstrip('.')}. Not sampling.")
        self._seen[k] = n + 1
        self.served += 1
        return rows[n]

    def _store(self, req: dict, reply: dict) -> None:
        text = self._norm(json.dumps(reply, ensure_ascii=False, default=str))      # insertion order kept: a replayed reply is the same bytes
        if any(p.search(text) for p in _KEY_PATTERNS):
            self.record_failures += 1
            raise DeterminismError(f"a {req['purpose']} reply holds something that looks like a key: not recorded (the run is stopped)")
        n = self._seen.get(req["key"], 0)
        self._seen[req["key"]] = n + 1
        self._append({**req, "n": n, "reply": json.loads(text)})

    def _append(self, row: dict) -> None:
        with self.file.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # -- records ---------------------------------------------------------------------------------------------------
    def sha256(self) -> str:
        return hashlib.sha256(self.file.read_bytes()).hexdigest() if self.file.is_file() else ""

    def unused(self) -> int:
        """Recorded calls a replay did not consume (an exact reproduction consumes them all)."""
        return sum(len(rs) - self._seen.get(k, 0) for k, rs in self._rows.items())

    def state(self) -> dict[str, Any]:
        rows = sum(len(rs) for rs in self._rows.values()) if self.mode == "replay" else sum(self._seen.values())
        out: dict[str, Any] = {"mode": self.mode, "tape_sha256": self.sha256(), "calls_recorded": rows, "served_from_tape": self.served,
                               "live_calls": self.live, "replay_misses": self.misses}
        if self.mode == "replay":
            out["unused_recordings"] = self.unused()
        else:
            out["unreplayable_calls"] = self.unreplayable
            out["record_failures"] = self.record_failures
        return out
