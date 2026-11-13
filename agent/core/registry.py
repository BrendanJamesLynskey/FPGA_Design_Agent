"""The tool registry and the one entry point, :func:`dispatch`.

A tool is a typed Python function with a JSON schema. ``dispatch(session, name, args)`` is the only way a
harness (Deep Agents, Claude Code through the MCP server, a replayed episode) runs one. It validates the
arguments against the schema, runs the tool, redacts the result, logs the call to the audit log and the trace,
and never raises: a refusal comes back as ``{"ok": false, "refused": true, "rule": ..., "output": reason}``.

Every tool returns raw tool output and structured fields. None returns a fix hint (harness neutrality).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from agent.core.security import SecurityError, redact, redact_obj, validate_args

SCHEMA_VERSION = "1.10.1"        # bump the minor version for an added optional argument or tool, the major for a break
MAX_OUTPUT = 20_000             # characters of raw output returned to the model; the full text stays in build/ files


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., dict[str, Any]]
    hardware: bool = False
    version: str = SCHEMA_VERSION
    #: 05c2 fix 3: ``refine()`` -> ``{"properties": {name: patch}, "description": suffix}`` computed from what is
    #: available HERE (installed simulators, the bank's section ids), so the schema never offers a value that fails.
    refine: Callable[[], dict[str, Any]] | None = None

    def schema(self) -> dict[str, Any]:
        """The input schema as this machine can honour it (``input_schema`` plus ``refine``'s patches)."""
        if self.refine is None:
            return self.input_schema
        patch = self.refine().get("properties", {})
        props = {k: ({**v, **patch[k]} if k in patch else v) for k, v in self.input_schema["properties"].items()}
        return {**self.input_schema, "properties": props}

    def describe(self) -> str:
        return self.description + (" " + self.refine().get("description", "") if self.refine else "")

    def descriptor(self, refined: bool = True) -> dict[str, Any]:
        """``refined=False`` is the static, machine-independent schema (the committed snapshot)."""
        return {"name": self.name, "description": self.describe() if refined else self.description,
                "inputSchema": self.schema() if refined else self.input_schema, "version": self.version}


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None,
         hardware: bool = False, refine: Callable[[], dict[str, Any]] | None = None):
    def deco(fn):
        TOOLS[name] = Tool(name, description,
                           {"type": "object", "properties": properties, "required": required or [],
                            "additionalProperties": False}, fn, hardware, refine=refine)
        return fn
    return deco


def tool_list(refined: bool = True) -> list[dict[str, Any]]:
    from agent.core import tools as _t  # noqa: F401  (registers the tools)
    return [TOOLS[n].descriptor(refined) for n in sorted(TOOLS)]


def clip(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    h = limit // 2
    return text[:h] + f"\n... [{len(text) - limit} characters omitted] ...\n" + text[-h:]


def dispatch(session, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    from agent.core import tools as _t  # noqa: F401
    args = dict(args or {})
    t0 = time.monotonic()
    rec: dict[str, Any] = {"tool": name, "arguments": args, "stage": session.stage,
                           "role": getattr(session.jail, "role", None)}
    try:
        if name not in TOOLS:
            raise SecurityError("unknown-tool", f"no tool named {name!r}")
        tl = TOOLS[name]
        validate_args(tl.schema(), args)
        out = tl.fn(session, **args)
        res = {"ok": bool(out.pop("ok", True)), "refused": False, "tool": name, "stage": session.stage, **out}
    except SecurityError as e:
        res = {"ok": False, "refused": True, "rule": e.rule, "tool": name, "stage": session.stage, "output": str(e)}
    except Exception as e:                                      # a tool bug: report it, never crash the harness
        res = {"ok": False, "refused": False, "tool": name, "stage": session.stage,
               "output": f"internal error: {type(e).__name__}: {e}"}
    res["output"] = clip(redact(str(res.get("output", ""))))
    res = redact_obj(res)
    res["seconds"] = round(time.monotonic() - t0, 3)
    summary = res["output"][:300]
    session.audit.log({**rec, "ok": res["ok"], "refused": res["refused"], "rule": res.get("rule"),
                       "result_summary": summary, "seconds": res["seconds"],
                       **({"skills": res["skills"]} if "skills" in res else {}),
                       **({k: res[k] for k in ("sections_empty", "procedures_fallback") if res.get(k)}),
                       **({"hits": [h.get("id") for h in res["hits"]]} if res.get("hits") else {})})
    if session.trace is not None:
        session.trace.tool(name, args, res, session.stage)
    return res
