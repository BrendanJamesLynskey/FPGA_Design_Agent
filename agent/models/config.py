"""One configuration for every model call (brief 108): which endpoint, model and call options each purpose uses.

A **purpose** names why a model is called (``rtl``: code generation and repair; ``oracle``: the user simulator in evals; ...).
An **endpoint** names where it is called: a kind (``claude_code``, ``anthropic_api``, ``openrouter``, ``openai_compatible``,
``replay``), an address and the *name* of the environment variable that holds its key. Never a key.

The table is built from layers, lowest to highest: the built-in defaults (today's behaviour), the user file
(``~/.config/fpga_design_agent/models.yaml``), the project file (``models.yaml`` of the project, or ``--models-file``), then
the command line (the flags that existed before, as aliases, and ``--model-config``). A purpose key may be ``purpose@stage``
for one stage of the machine; stage keys beat plain keys. An option the endpoint kind does not support is an error when
the table is built, never silently ignored (built-in soft defaults are the one exception: they are dropped when the kind
cannot take them, so that switching a purpose to another kind is a one-line change).

The guardrails are in :func:`check`, applied to the final table whatever layer a value came from: no Fable or Opus through
OpenRouter or the API, Fable only with the owner's command-line flag, keys only by environment variable name, an endpoint on
work hardware refused for live calls. A project file cannot lift any of them: the keys that mark work hardware and the
Fable flag are read from the user file and the command line only, and are an error anywhere else.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

USER_FILE = Path.home() / ".config" / "fpga_design_agent" / "models.yaml"
PROJECT_FILE_NAME = "models.yaml"

#: purpose -> (what it is for, what the call sites need of an endpoint)
#: needs: ``agent`` a tool-using sub-agent turn (the Claude Code arm, or Deep Agents over a chat endpoint); ``text`` one system+user
#: -> text call; ``chat`` messages -> Reply (no tools); ``tools`` messages + tool schemas -> Reply (a chat endpoint only).
PURPOSES: dict[str, dict[str, Any]] = {
    "interpret": {"doc": "NL request and spec interpretation: the Clarifier role, the project spec drafter, the plain-English parsers", "needs": ("agent", "chat")},
    "oracle": {"doc": "the user simulator in evals (answers the Clarifier from the hidden spec)", "needs": ("text", "chat")},
    "model": {"doc": "the Modeller role: the blind golden model", "needs": ("agent",)},
    "tests": {"doc": "the Verifier role: tests and verification plan, bring-up files", "needs": ("agent",)},
    "spectest": {"doc": "the independent spec-only bench writer and its triage step", "needs": ("text",)},
    "rtl": {"doc": "the Designer role: code generation and repair; also the single-shot RTL writers", "needs": ("agent", "chat")},
    "constraints": {"doc": "the Designer in the constraints stage (inherits rtl unless set)", "needs": ("agent",)},
    "closure": {"doc": "the closure loop's writer: reads STA, area and power reports and edits RTL", "needs": ("chat",)},
    "latency": {"doc": "the latency loop's writer (needs tool calls)", "needs": ("tools",)},
    "review": {"doc": "the review judge of an existing design", "needs": ("text",)},
    "doc": {"doc": "the DOC step: handover, README and AGENT.md (inherits rtl unless set)", "needs": ("text",)},
    "route": {"doc": "the cheap skill-section classifier (off while it has no model)", "needs": ("chat",), "opt_in": True},
    "options": {"doc": "reserved: brief 104's strategy generator; no call site yet", "needs": ("chat",), "opt_in": True},
    "embed": {"doc": "reserved: embeddings; the agent calls none today", "needs": ("chat",), "opt_in": True},
}
#: the agent's four roles are purposes (clarify is ``interpret``); ``rtl`` in the constraints stage is ``constraints``
ROLE_PURPOSE = {"clarify": "interpret", "model": "model", "tests": "tests", "rtl": "rtl"}
PURPOSE_ROLE = {v: k for k, v in ROLE_PURPOSE.items()}

KINDS = ("claude_code", "anthropic_api", "openrouter", "openai_compatible", "replay")
SUPPORTS: dict[str, dict[str, frozenset[str]]] = {          # kind -> what it can do
    "claude_code": {"options": frozenset({"effort", "timeout_s"}), "needs": frozenset({"agent", "text", "chat"})},
    "anthropic_api": {"options": frozenset({"temperature", "max_tokens", "stop", "thinking_budget", "timeout_s", "retries"}),
                      "needs": frozenset({"agent", "text", "chat", "tools"})},
    "openrouter": {"options": frozenset({"temperature", "seed", "max_tokens", "stop", "effort", "timeout_s", "retries"}),
                   "needs": frozenset({"agent", "text", "chat", "tools"})},
    "openai_compatible": {"options": frozenset({"temperature", "seed", "max_tokens", "stop", "effort", "timeout_s", "retries"}),
                          "needs": frozenset({"agent", "text", "chat", "tools"})},
    "replay": {"options": frozenset(), "needs": frozenset({"text", "chat", "tools"})},
}
#: soft per-kind defaults: today's values (OpenRouterClient: temperature 0.2, 180 s, one retry; the Claude Code arm: effort medium)
KIND_DEFAULTS: dict[str, dict[str, Any]] = {
    "claude_code": {"effort": "medium"},
    "openrouter": {"temperature": 0.2, "timeout_s": 180, "retries": 1},
    "openai_compatible": {"temperature": 0.2, "timeout_s": 180, "retries": 1},
    "anthropic_api": {"temperature": 0.2, "max_tokens": 8192, "timeout_s": 180, "retries": 1},
}
BUILTIN_ENDPOINTS: dict[str, dict[str, Any]] = {
    "openrouter": {"kind": "openrouter", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
    "claude_code": {"kind": "claude_code"},
    "anthropic_api": {"kind": "anthropic_api", "base_url": "https://api.anthropic.com", "key_env": "ANTHROPIC_API_KEY"},
    "replay": {"kind": "replay"},
}
DEFAULT_MODEL = "openai/gpt-6-luna"
_OR = {"endpoint": "openrouter", "model": DEFAULT_MODEL}
BUILTIN_PURPOSES: dict[str, dict[str, Any]] = {
    **{p: dict(_OR) for p in ("interpret", "oracle", "model", "tests", "rtl", "closure", "latency")},
    "constraints": {"inherit": "rtl"},
    "doc": {"inherit": "rtl"},
    "spectest": {"endpoint": "claude_code", "model": "claude-sonnet-5-5", "options": {"effort": "medium", "timeout_s": 900}},
    "review": {"endpoint": "claude_code", "model": "claude-sonnet-5-5", "options": {"effort": "medium", "timeout_s": 900}},
    "route": {"endpoint": "openrouter", "model": None}, "options": {"endpoint": "openrouter", "model": None},
    "embed": {"endpoint": "openrouter", "model": None},
}
OPTION_NAMES = frozenset().union(*(s["options"] for s in SUPPORTS.values()))
FORBIDDEN_VIA_NETWORK = ("anthropic/", "fable", "opus")     # OpenRouter / openai_compatible on a router host, and anthropic_api (owner rule)
SECRET_WORDS = ("api_key", "apikey", "key", "token", "secret", "password", "authorization", "bearer")
KEY_PATTERNS = (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), re.compile(r"[A-Za-z0-9_\-]{32,}\.[A-Za-z0-9_\-]{10,}"),
                re.compile(r"(?i)bearer\s+\S{12,}"))
NOTE_MAX = 240
ENDPOINT_KEYS = {"kind", "base_url", "key_env", "note", "host_class", "path"}
PURPOSE_KEYS = {"endpoint", "model", "options", "note", "inherit"}
LAYER_ORDER = ("builtin", "command", "user", "project", "cli")
USER_ONLY = ("work_hardware_hosts", "host_class")         # honoured from the user file only (a project file cannot unmark or mark)


class ConfigError(ValueError):
    """The table is invalid (always raised when the table is built, before any call)."""


@dataclass
class Layer:
    name: str                                   # one of LAYER_ORDER
    data: dict[str, Any]
    source: str | None = None                   # a file path or a description
    sha256: str | None = None


@dataclass
class Entry:
    """One resolved purpose (or ``purpose@stage``): where and how its calls run. No secret and no prompt text is ever held."""
    purpose: str
    stage: str | None
    endpoint: str
    kind: str
    model: str | None
    options: dict[str, Any]
    note: str = ""
    base_url: str | None = None
    key_env: str | None = None
    host_class: str | None = None
    path: str | None = None
    sources: dict[str, str] = field(default_factory=dict)      # field -> layer name it came from

    def record(self) -> dict[str, Any]:
        return {"purpose": self.purpose, **({"stage": self.stage} if self.stage else {}), "endpoint": self.endpoint, "kind": self.kind,
                "model": self.model, "options": dict(sorted(self.options.items())), "deployment_note": self.note,
                **({"base_url": self.base_url} if self.base_url else {}), **({"key_env": self.key_env} if self.key_env else {})}

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.record(), sort_keys=True).encode()).hexdigest()[:16]

    @property
    def host(self) -> str:
        return (urlparse(self.base_url or "").hostname or "").lower()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_file(path: Path, name: str) -> Layer:
    """A user or project file as a layer. Unknown keys, secrets and bad shapes are errors."""
    import yaml
    text = Path(path).read_text()
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: not valid YAML ({e})") from None
    return Layer(name, validate_layer(data, name, str(path)), str(path), _sha(text))


def validate_layer(data: Any, layer: str, where: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: the file must be a mapping")
    extra = set(data) - {"version", "endpoints", "purposes", "default", "work_hardware_hosts", "allow_fable"}
    if "allow_fable" in data:
        raise ConfigError(f"{where}: allow_fable is not a file setting; Fable needs the owner's --allow-fable command-line flag")
    if extra:
        raise ConfigError(f"{where}: unknown top-level keys {sorted(extra)}")
    if "work_hardware_hosts" in data and layer != "user":
        raise ConfigError(f"{where}: work_hardware_hosts may only be set in the user file ({USER_FILE}), not in the {layer} layer")
    for name, ep in (data.get("endpoints") or {}).items():
        if not isinstance(ep, dict):
            raise ConfigError(f"{where}: endpoint {name!r} must be a mapping")
        bad = set(ep) - ENDPOINT_KEYS
        for k in list(ep):
            if k.lower() in SECRET_WORDS or any(w in k.lower() for w in ("secret", "password", "token")):
                raise ConfigError(f"{where}: endpoint {name!r}: {k!r} looks like a secret; name the environment variable with key_env instead")
        if bad:
            raise ConfigError(f"{where}: endpoint {name!r}: unknown keys {sorted(bad)}")
        if ep.get("kind") is not None and ep["kind"] not in KINDS:
            raise ConfigError(f"{where}: endpoint {name!r}: kind must be one of {KINDS}, not {ep['kind']!r}")
        if "host_class" in ep and layer not in ("user", "builtin"):
            raise ConfigError(f"{where}: endpoint {name!r}: host_class may only be set in the user file, not in the {layer} layer")
        ke = ep.get("key_env")
        if ke is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(ke)):
            raise ConfigError(f"{where}: endpoint {name!r}: key_env must be an environment variable NAME (upper case), not a key")
    for key, pe in {**(data.get("purposes") or {}), **({"default": data["default"]} if data.get("default") else {})}.items():
        _check_purpose_entry(key, pe, where)
    scan_for_keys(data, where)
    return data


def _check_purpose_entry(key: str, pe: Any, where: str) -> None:
    if key != "default":
        check_key(key, where)
    if not isinstance(pe, dict):
        raise ConfigError(f"{where}: purpose {key!r} must be a mapping")
    bad = set(pe) - PURPOSE_KEYS
    if bad:
        raise ConfigError(f"{where}: purpose {key!r}: unknown keys {sorted(bad)}")
    for o in (pe.get("options") or {}):
        if o not in OPTION_NAMES:
            raise ConfigError(f"{where}: purpose {key!r}: unknown option {o!r}; options are {sorted(OPTION_NAMES)}")
    if len(str(pe.get("note") or "")) > NOTE_MAX or "\n" in str(pe.get("note") or ""):
        raise ConfigError(f"{where}: purpose {key!r}: the deployment note is one line of at most {NOTE_MAX} characters (never prompt text)")


def scan_for_keys(obj: Any, where: str) -> None:
    """Refuse a value that looks like a key or token anywhere in a layer (a key must only ever be named by its variable)."""
    if isinstance(obj, dict):
        for v in obj.values():
            scan_for_keys(v, where)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            scan_for_keys(v, where)
    elif isinstance(obj, str):
        if any(p.search(obj) for p in KEY_PATTERNS):
            raise ConfigError(f"{where}: a value looks like a key or token; keys are named by environment variable (key_env), never inlined")


def _stage_names() -> tuple[str, ...]:
    from agent.graph.stages import MACHINE
    return tuple(st.name for st in MACHINE)


def check_key(key: str, where: str = "") -> tuple[str, str | None]:
    purpose, _, stage = key.partition("@")
    if purpose not in PURPOSES:
        raise ConfigError(f"{where}: unknown purpose {purpose!r} in {key!r}; purposes are {', '.join(PURPOSES)}")
    if stage and stage not in _stage_names():
        raise ConfigError(f"{where}: unknown stage {stage!r} in {key!r}; stages are {', '.join(_stage_names())}")
    return purpose, stage or None


def _merge_entry(into: dict[str, Any], new: dict[str, Any], layer: str, src: dict[str, str]) -> None:
    for k, v in new.items():
        if k == "options":
            into.setdefault("options", {})
            for ok, ov in (v or {}).items():
                into["options"][ok] = (ov, layer)
        else:
            into[k] = v
            src[k] = layer
            if k == "endpoint":                    # a new endpoint: hard options set below it for another kind no longer apply
                into["options"] = {ok: ov for ok, ov in into.get("options", {}).items() if ov[1] in (layer, "soft")}


class Table:
    """The resolved configuration: built from layers, validated, queried by purpose and stage."""

    def __init__(self, layers: list[Layer], *, allow_fable: bool = False, replay: bool = False):
        order = {n: i for i, n in enumerate(LAYER_ORDER)}
        self.layers = sorted(layers, key=lambda L: order[L.name])
        self.allow_fable = allow_fable
        self.replay = replay                      # chat calls are served from a recorded fixture: nothing live on an endpoint host
        self.endpoints: dict[str, dict[str, Any]] = {}
        self.endpoint_src: dict[str, str] = {}
        self.work_hosts: set[str] = set()
        for L in self.layers:
            for n, ep in (L.data.get("endpoints") or {}).items():
                self.endpoints[n] = {**self.endpoints.get(n, {}), **ep}
                self.endpoint_src[n] = L.name
            for h in L.data.get("work_hardware_hosts") or []:
                self.work_hosts.add(str(h).lower())
        self._raw: dict[str, dict[str, Any]] = {}
        self._src: dict[str, dict[str, str]] = {}
        self._build_raw()
        self._cache: dict[tuple[str, str | None], Entry] = {}
        self.check()

    # -- layering --------------------------------------------------------------------------------------------------
    def _build_raw(self) -> None:
        for L in self.layers:
            dflt = L.data.get("default")
            for p in PURPOSES:       # a layer's ``default`` is each non-opt-in purpose's entry in that layer, where the endpoint kind can serve it
                if dflt and not PURPOSES[p].get("opt_in") and self._serves(dflt.get("endpoint"), p):
                    self._apply(p, dflt, L.name)
            for k, e in (L.data.get("purposes") or {}).items():
                self._apply(k, e, L.name)

    def _serves(self, endpoint: str | None, purpose: str) -> bool:
        if not endpoint:
            return True
        kind = {**BUILTIN_ENDPOINTS.get(endpoint, {}), **self.endpoints.get(endpoint, {})}.get("kind")
        return kind is None or all(n in SUPPORTS[kind]["needs"] for n in PURPOSES[purpose]["needs"])

    def _apply(self, key: str, e: dict[str, Any], layer: str) -> None:
        raw = self._raw.setdefault(key, {})
        src = self._src.setdefault(key, {})
        _merge_entry(raw, e, layer, src)
        if layer == "builtin" and "options" in raw:                  # built-in option defaults are soft
            raw["options"] = {k: (v[0], "soft") for k, v in raw["options"].items()}

    def _resolve_raw(self, purpose: str, stage: str | None) -> tuple[dict[str, Any], dict[str, str]]:
        """The merged raw fields of ``purpose`` (following ``inherit``), then of ``purpose@stage`` on top."""
        def base(p: str, seen: tuple[str, ...] = ()) -> tuple[dict[str, Any], dict[str, str]]:
            raw, src = copy.deepcopy(self._raw.get(p, {})), dict(self._src.get(p, {}))
            parent = raw.pop("inherit", None)
            if parent and parent not in seen:
                praw, psrc = base(parent, (*seen, p))
                opts = {**praw.get("options", {}), **raw.get("options", {})}
                merged = {**praw, **raw}
                merged["options"] = opts
                return merged, {**psrc, **src}
            return raw, src
        raw, src = base("constraints" if (purpose, stage) == ("rtl", "constraints") else purpose)   # the Designer in the constraints stage
        if stage:
            sk = f"{purpose}@{stage}"
            if sk in self._raw:
                sraw, ssrc = copy.deepcopy(self._raw[sk]), dict(self._src[sk])
                sraw.pop("inherit", None)
                if "endpoint" in sraw:
                    raw["options"] = {k: v for k, v in raw.get("options", {}).items() if v[1] == "soft"}
                raw = {**raw, **{k: v for k, v in sraw.items() if k != "options"}, "options": {**raw.get("options", {}), **sraw.get("options", {})}}
                src = {**src, **ssrc}
        return raw, src

    def entry(self, purpose: str, stage: str | None = None) -> Entry:
        if purpose not in PURPOSES:
            raise ConfigError(f"unknown purpose {purpose!r}")
        k = (purpose, stage)
        if k not in self._cache:
            self._cache[k] = self._make(purpose, stage)
        return self._cache[k]

    def _make(self, purpose: str, stage: str | None) -> Entry:
        raw, src = self._resolve_raw(purpose, stage)
        ename = raw.get("endpoint") or "openrouter"
        ep = {**BUILTIN_ENDPOINTS.get(ename, {}), **self.endpoints.get(ename, {})}
        if not ep.get("kind"):
            raise ConfigError(f"purpose {purpose!r}: endpoint {ename!r} is not defined (define it under endpoints:)")
        kind = ep["kind"]
        opts: dict[str, Any] = {}
        soft = {**KIND_DEFAULTS.get(kind, {})}
        for o, (v, layer) in (raw.get("options") or {}).items():
            if layer == "soft":
                if o in SUPPORTS[kind]["options"]:
                    soft[o] = v
            else:
                if o not in SUPPORTS[kind]["options"]:
                    raise ConfigError(f"purpose {purpose!r}: option {o!r} (from the {layer} layer) is not supported by endpoint kind {kind!r}; "
                                      f"it supports {sorted(SUPPORTS[kind]['options']) or 'none'}")
                opts[o] = v
        for o, v in soft.items():
            opts.setdefault(o, v)
        opts = {o: v for o, v in opts.items() if v is not None}     # null = unset (the CLI default)
        if (purpose, stage) == ("rtl", "constraints"):
            purpose = "constraints"
        return Entry(purpose, stage, ename, kind, raw.get("model"), opts, str(raw.get("note") or ep.get("note") or ""), ep.get("base_url"),
                     ep.get("key_env"), ep.get("host_class"), ep.get("path"), {**src, "endpoint": self.endpoint_src.get(ename, "builtin")})

    def entries(self) -> list[Entry]:
        """Every purpose, and every ``purpose@stage`` some layer names."""
        out = [self.entry(p) for p in PURPOSES]
        for k in sorted(self._raw):
            if "@" in k:
                p, s = k.split("@")
                out.append(self.entry(p, s))
        return out

    # -- guardrails -------------------------------------------------------------------------------------------------
    def check(self) -> None:
        for e in self.entries():
            who = f"{e.purpose}{'@' + e.stage if e.stage else ''}"
            if e.model is None:
                continue                                                 # an opt-in purpose that is off
            missing = [n for n in PURPOSES[e.purpose]["needs"] if n not in SUPPORTS[e.kind]["needs"]]
            if "tools" in missing:
                raise ConfigError(f"{who}: endpoint {e.endpoint!r} (kind {e.kind}) cannot serve this purpose: its call sites need tool calls "
                                  "through a chat endpoint (openrouter, openai_compatible or anthropic_api)")
            if missing:
                raise ConfigError(f"{who}: endpoint kind {e.kind!r} cannot serve the {missing} calls of this purpose")
            m = e.model.lower()
            if e.kind in ("openrouter", "anthropic_api") or (e.kind == "openai_compatible" and self._is_router(e)):
                bad = [f for f in FORBIDDEN_VIA_NETWORK if f in m] if e.kind != "anthropic_api" else [f for f in ("fable", "opus") if f in m]
                if bad:
                    raise ConfigError(f"{who}: model {e.model!r} is not allowed through {e.kind} ({e.host or 'api'}): owner rule, "
                                      "Fable and Opus never go through OpenRouter or the API")
            if e.kind == "claude_code":
                if not m.startswith("claude-"):
                    raise ConfigError(f"{who}: claude_code runs Anthropic models only, not {e.model!r}")
                if "fable" in m and not self.allow_fable:
                    raise ConfigError(f"{who}: Fable needs the owner's explicit --allow-fable flag (command line only)")
            elif "fable" in m and not self.allow_fable:
                raise ConfigError(f"{who}: Fable needs the owner's explicit --allow-fable flag (command line only)")
            if e.kind in ("openrouter", "openai_compatible", "anthropic_api") and not e.key_env and not self._is_local(e):
                raise ConfigError(f"{who}: endpoint {e.endpoint!r} needs key_env (the NAME of the environment variable holding its key)")
            if e.kind == "openai_compatible" and not e.base_url:
                raise ConfigError(f"{who}: endpoint {e.endpoint!r} (openai_compatible) needs a base_url")
            if self.work_marked(e) and self.is_live(e):
                raise ConfigError(f"{who}: endpoint {e.endpoint!r} is marked work hardware in the user file: refused for live runs "
                                  "(batch replay only)")

    def _is_router(self, e: Entry) -> bool:
        return any(h in e.host for h in ("openrouter.ai",))

    @staticmethod
    def _is_local(e: Entry) -> bool:
        return e.host in ("localhost", "127.0.0.1", "::1")

    def work_marked(self, e: Entry) -> bool:
        ep = {**BUILTIN_ENDPOINTS.get(e.endpoint, {}), **self.endpoints.get(e.endpoint, {})}
        return ep.get("host_class") == "work_hardware" or (e.host != "" and e.host in self.work_hosts)

    def is_live(self, e: Entry) -> bool:
        """A call that really reaches the endpoint: not served from a recorded fixture."""
        if e.kind == "replay":
            return False
        return not (self.replay and e.kind != "claude_code" and "chat" in PURPOSES[e.purpose]["needs"])

    # -- records ----------------------------------------------------------------------------------------------------
    def record(self) -> dict[str, Any]:
        rows = {(f"{e.purpose}@{e.stage}" if e.stage else e.purpose): e.record() for e in self.entries()}
        body = {"purposes": rows, "layers": [{"layer": L.name, "source": L.source, "sha256": L.sha256} for L in self.layers if L.name != "builtin"]}
        out = {**body, "hash": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]}
        _assert_no_secret(out)
        return out

    @property
    def hash(self) -> str:
        return self.record()["hash"]

    def show(self) -> str:
        w = max(len(f"{e.purpose}@{e.stage}" if e.stage else e.purpose) for e in self.entries())
        lines = [f"{'purpose':<{w}}  {'endpoint':<14} {'kind':<17} {'model':<26} options  [from]"]
        for e in self.entries():
            name = f"{e.purpose}@{e.stage}" if e.stage else e.purpose
            frm = ",".join(sorted({v for k, v in e.sources.items() if k in ("endpoint", "model")})) or "builtin"
            lines.append(f"{name:<{w}}  {e.endpoint:<14} {e.kind:<17} {str(e.model or '(off)'):<26} "
                         f"{json.dumps(e.options, sort_keys=True)}  [{frm}]" + (f"  note: {e.note}" if e.note else ""))
        lines.append(f"table hash {self.hash}; layers: " + ", ".join(f"{L.name}={L.source or 'built in'}" for L in self.layers))
        return "\n".join(lines)


def _assert_no_secret(obj: Any) -> None:
    """A record never holds a key: a value matching a key pattern, or the value of any configured key variable, is a bug."""
    text = json.dumps(obj)
    for p in KEY_PATTERNS:
        if p.search(text):
            raise ConfigError("a record would contain something that looks like a key; refused")
    for var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "FDA_ACCESS_KEY"):
        v = os.environ.get(var)
        if v and len(v) >= 8 and v in text:
            raise ConfigError(f"a record would contain the value of {var}; refused")


# --- aliases: the flags that existed before 108 become a layer of the same table -------------------------------------


def legacy_layer(*, harness: str | None = None, cc_model: str | None = None, cc_effort: str | None = None, model: str | None = None,
                 oracle: str | None = None, oracle_cc_model: str | None = None, spectest_model: str | None = None,
                 spectest_effort: str | None = None, router_model: str | None = None, profile: str | None = None,
                 roles: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The command-line layer for the flags given explicitly (None = not given). ``--harness``/``--cc-model``/``--cc-effort``/``--model``
    set the four roles, the oracle and the writers exactly as before; ``--profile`` and ``--roles`` are role overrides."""
    purposes: dict[str, dict[str, Any]] = {}
    role_ps = ("interpret", "model", "tests", "rtl")
    if model:
        for p in (*role_ps, "oracle", "closure", "latency"):
            purposes[p] = {"endpoint": "openrouter", "model": model}
    if harness == "claude_code":
        for p in role_ps:
            purposes[p] = {"endpoint": "claude_code", "model": cc_model or "claude-haiku-5-5",
                           "options": {"effort": cc_effort or "medium"}}
    elif cc_model or cc_effort:                  # the DOC step and the arm read these when the Designer is on Claude Code
        pass
    if oracle == "claude_code":
        purposes["oracle"] = {"endpoint": "claude_code", "model": oracle_cc_model or "claude-haiku-5-5", "options": {"effort": None}}
    elif oracle_cc_model:
        pass
    if spectest_model or spectest_effort:
        purposes["spectest"] = {"endpoint": "claude_code", "model": spectest_model or "claude-sonnet-5-5",
                                **({"options": {"effort": spectest_effort}} if spectest_effort else {})}
    if router_model:
        purposes["route"] = {"endpoint": "openrouter", "model": router_model}
    from agent.graph.role_models import PROFILES
    for src in (PROFILES.get(profile or "single", {}), roles or {}):
        for key, s in src.items():
            role, _, stage = key.partition("@")
            pkey = ROLE_PURPOSE[role] + (f"@{stage}" if stage else "")
            e = purposes.setdefault(pkey, {})
            if "harness" in s:
                e["endpoint"] = "claude_code" if s["harness"] == "claude_code" else "openrouter"
            if "model" in s:
                e["model"] = s["model"]
            if "effort" in s:
                e.setdefault("options", {})["effort"] = s["effort"]
    return {"purposes": purposes}


def parse_cli_json(text: str | dict | None) -> dict[str, Any]:
    """``--model-config``: a JSON object in the file format (purposes, endpoints, default)."""
    if not text:
        return {}
    d = text if isinstance(text, dict) else json.loads(text)
    return validate_layer(d, "cli", "--model-config")


def build_table(*, user_file: Path | None = None, project_file: Path | None = None, cli: dict[str, Any] | None = None,
                command: dict[str, Any] | None = None, allow_fable: bool = False, replay: bool = False) -> Table:
    """The table of a run: built-in, command defaults, user file, project file, command line."""
    layers = [Layer("builtin", {"endpoints": {}, "purposes": copy.deepcopy(BUILTIN_PURPOSES)}, "built in")]
    if command:
        layers.append(Layer("command", validate_layer(command, "command", "command defaults"), "command defaults"))
    uf = user_file if user_file is not None else Path(os.environ.get("FDA_MODELS_FILE") or USER_FILE)
    if uf.is_file():
        layers.append(load_file(uf, "user"))
    if project_file is not None and project_file.is_file():
        layers.append(load_file(project_file, "project"))
    if cli:
        layers.append(Layer("cli", validate_layer(cli, "cli", "the command line"), "command line"))
    return Table(layers, allow_fable=allow_fable, replay=replay)
