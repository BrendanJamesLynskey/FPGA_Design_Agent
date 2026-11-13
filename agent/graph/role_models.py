"""Per-role model routing (brief 05f).

Which harness, model and effort runs each sub-agent role. The roles are the four of :mod:`agent.graph.roles`:
the Clarifier (``clarify``), the Modeller (``model``, blind golden model), the Verifier (``tests``, including the stage-9 bring-up files) and the Designer (``rtl``,
every repair it owns included). The stage machine that decides which role runs when is plain code (the
"orchestration"); no model drives it, so there is no orchestrator role to route.

The interview **oracle** (the user simulator) is not a role: it always runs on ``Config.model`` (luna by default),
whatever the profile, so runs stay comparable with every earlier F2 run.

A map is resolved in layers: the ``single`` base (``Config.harness`` / ``cc_model`` / ``cc_effort`` / ``model``
for every role: today's behaviour), then the named profile, then an explicit ``--roles`` JSON. ``config.json`` of a run
stores the profile name and the explicit overrides, so ``resume`` rebuilds the same map.

**Per-stage overrides.** The key is the role, or ``role@stage`` for one stage of the machine (stage names as in
``agent.graph.stages.MACHINE``, for example ``rtl@timing-closure`` or ``rtl@constraints``): a task such as reading STA, CDC or
methodology reports in the closure stages may do better on another model or harness than the same role elsewhere. Each
layer is partial (only the keys it names change). Precedence, lowest to highest: base < profile ``role`` < explicit
``role`` < profile ``role@stage`` < explicit ``role@stage``. To add one, put it in ``--roles``, for example
``--roles '{"rtl@timing-closure": {"model": "claude-fable-5-1"}}'``, or add it to a profile in :data:`PROFILES`. The
profile ``cvdp`` sets none.
"""

from __future__ import annotations

import json
from typing import Any

ROLE_NAMES = ("clarify", "model", "tests", "rtl")
HARNESSES = ("deepagents", "claude_code")
FORBIDDEN_OPENROUTER = ("anthropic/", "fable", "opus")      # owner rule: never Fable or Opus through OpenRouter

#: ``effort`` None: the flag is omitted and the CLI default applies (the CVDP ladder's "effort low").
PROFILES: dict[str, dict[str, dict[str, Any]]] = {
    "single": {},
    # CVDP evidence (cvdp_rtl_recommendation.md): Opus 5.5 writes RTL; the Modeller runs a *different* LLM from the
    # Designer, so a same-model misreading of the spec is not shared; tests and clarify on Sonnet.
    "cvdp": {
        "rtl": {"harness": "claude_code", "model": "claude-opus-5-5", "effort": None},
        "model": {"harness": "claude_code", "model": "claude-sonnet-5-5", "effort": "medium"},
        "tests": {"harness": "claude_code", "model": "claude-sonnet-5-5", "effort": "medium"},
        "clarify": {"harness": "claude_code", "model": "claude-sonnet-5-5", "effort": "medium"},
    },
}


def split_key(key: str) -> tuple[str, str | None]:
    role, _, stage = key.partition("@")
    return role, stage or None


def _stage_names() -> tuple[str, ...]:
    from agent.graph.stages import MACHINE
    return tuple(st.name for st in MACHINE)


def check_key(key: str) -> None:
    role, stage = split_key(key)
    if role not in ROLE_NAMES:
        raise ValueError(f"unknown role {role!r} in {key!r}; roles are {', '.join(ROLE_NAMES)}")
    if stage is not None and stage not in _stage_names():
        raise ValueError(f"unknown stage {stage!r} in {key!r}; stages are {', '.join(_stage_names())}")


def validate(roles: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for role, s in roles.items():
        if role not in ROLE_NAMES:
            raise ValueError(f"unknown role {role!r}; roles are {', '.join(ROLE_NAMES)}")
        if s.get("harness") not in HARNESSES:
            raise ValueError(f"role {role}: harness must be one of {HARNESSES}, not {s.get('harness')!r}")
        if not s.get("model"):
            raise ValueError(f"role {role}: no model")
        if s["harness"] == "deepagents" and any(f in s["model"].lower() for f in FORBIDDEN_OPENROUTER):
            raise ValueError(f"role {role}: model {s['model']!r} is not allowed through OpenRouter (owner rule)")
    return roles


def parse_roles(text: str | dict | None) -> dict[str, dict[str, Any]]:
    """The explicit overrides: a JSON object (or a path's text) of role -> partial {harness, model, effort}."""
    if not text:
        return {}
    d = text if isinstance(text, dict) else json.loads(text)
    for role, s in d.items():
        check_key(role)
        extra = set(s) - {"harness", "model", "effort"}
        if extra:
            raise ValueError(f"role {role}: unknown keys {sorted(extra)}")
    return d


def stage_overrides(cfg) -> list[str]:
    """The ``role@stage`` keys in force (profile and explicit), for the record."""
    return sorted({k for k in [*PROFILES[cfg.profile], *(cfg.roles or {})] if "@" in k})


def resolve(cfg, stage: str | None = None) -> dict[str, dict[str, Any]]:
    """role -> {harness, model, effort} for this config; with ``stage``, the map in force in that stage."""
    if cfg.profile not in PROFILES:
        raise ValueError(f"unknown profile {cfg.profile!r}; profiles are {', '.join(PROFILES)}")
    for k in [*PROFILES[cfg.profile], *(cfg.roles or {})]:
        check_key(k)
    out: dict[str, dict[str, Any]] = {}
    for r in ROLE_NAMES:
        if cfg.harness == "claude_code":
            base = {"harness": "claude_code", "model": cfg.cc_model, "effort": cfg.cc_effort}
        else:
            base = {"harness": "deepagents", "model": cfg.model, "effort": None}
        out[r] = {**base, **PROFILES[cfg.profile].get(r, {}), **((cfg.roles or {}).get(r, {}))}
        if stage is not None:
            out[r] = {**out[r], **PROFILES[cfg.profile].get(f"{r}@{stage}", {}), **((cfg.roles or {}).get(f"{r}@{stage}", {}))}
    return validate(out)


def describe(roles: dict[str, dict[str, Any]]) -> str:
    return "; ".join(f"{r}: {s['harness']} {s['model']}" + (f" ({s['effort']})" if s.get("effort") else "")
                     for r, s in roles.items())
