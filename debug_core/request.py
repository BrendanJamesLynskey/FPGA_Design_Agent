"""Plain-English debug request -> intent JSON (the one step that uses a language model, brief 50A).

The model only restates the request in the intent schema (``schemas/intent.schema.json``): which signals, the trigger,
the window, and any register operations. It sees the design's signal and register names so it can map words such as
"the shell's write strobe" to an identifier, but nothing it says is trusted: every name is resolved afterwards by the
deterministic resolver (debug_core/rtl_index.py), and an unknown name is an error in the plan with suggestions.

    intent, meta = parse("capture count when the shell writes COUNT, 16 before and 32 after", Path("designs/t1_dimmer_counter"))

The client is the project's OpenRouter client (agent/graph/llm.py: ``provider: {data_collection: deny}``, cost only as the
provider reports it, Fable and Opus refused). Tests replay recorded replies (``Replay``), so CI makes no model call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from debug_core.plan import register_map, validate
from debug_core.rtl_index import ROOT, RtlIndex

DEFAULT_MODEL = "openai/gpt-6-luna"     # the project's cheap default (agent/graph/llm.py)

SYSTEM = """You turn an engineer's logic-analyser request into JSON. Reply with one JSON object and nothing else.

Schema (all keys except probes and trigger may be omitted):
{"probes": [signal names to record],
 "trigger": {"combine": "AND" or "OR", "conditions": [{"signal": name, "op": one of == != < <= > >= rise fall change, "value": integer or string such as "0x41" or "0b1x0" or "'A'" (omit for rise/fall/change)}]},
 "pre": cycles before the trigger or null, "post": cycles after the trigger or null,
 "clock": clock name if the request names one, else null,
 "setup": [register operations to do BEFORE arming], "stimulus": [register operations AFTER arming that make the event happen],
 "readback": [register reads after the capture],
 "question": "what the engineer wants to learn, one sentence",
 "unclear": ["any part of the request you could not map"]}
A register operation is {"op": "write", "register": NAME, "value": V} or {"op": "read", "register": NAME} or {"op": "wait_ms", "ms": N}.

Rules:
- Use a name from the signal list below when one clearly matches the words of the request; otherwise copy the
  engineer's own words for the signal (they will be checked, and an unknown name is reported back, never guessed).
- Signals used in the trigger are recorded automatically; list in "probes" the other signals to record.
- "N cycles before and M after" sets pre and post. "when X happens" is the trigger. "after writing V to REG" is a stimulus
  write; "with REG set to V" or "first set REG to V" is a setup write.
- Do not invent values, signals or registers that the request does not imply. Put anything unclear in "unclear".
"""


def signal_menu(idx: RtlIndex, regs: dict[str, int]) -> str:
    lines = ["Signals (register paths; probes.yaml names with their meaning):"]
    for name, a in sorted(idx.probe_aliases.items()):
        lines.append(f"  {name} ({a['width']} bits){': ' + a['why'] if a.get('why') else ''}")
    for r in idx.registers():
        mod_sig = idx.insts[r.rsplit(".", 1)[0] if "." in r else ""][0].signals.get(r.split(".")[-1])
        w = idx.width_of(r.rsplit(".", 1)[0] if "." in r else "", mod_sig) if mod_sig else None
        lines.append(f"  {r}" + (f" ({w} bits)" if w else ""))
    top = idx.insts[""][0]
    ports = [p for p in top.ports if idx.width_of("", top.signals[p]) == 1]
    lines.append("Top-level 1-bit pins: " + ", ".join(ports))
    lines.append("Registers (shell address): " + ", ".join(f"{k} 0x{v:02X}" for k, v in sorted(regs.items(), key=lambda x: x[1])))
    return "\n".join(lines)


def extract_json(text: str) -> dict[str, Any]:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j < i:
            raise ValueError("no JSON object in the reply")
        t = t[i:j + 1]
    return json.loads(t)


def clean(intent: dict[str, Any]) -> dict[str, Any]:
    """Drop keys the schema does not know and nulls in lists (a model's harmless extras), so validation judges content."""
    allowed = {"probes", "trigger", "pre", "post", "clock", "setup", "stimulus", "readback", "question", "unclear"}
    out = {k: v for k, v in intent.items() if k in allowed}
    out.setdefault("probes", [])
    out.setdefault("trigger", {"combine": "AND", "conditions": []})
    if isinstance(out.get("trigger"), dict):
        out["trigger"].setdefault("combine", "AND")
        out["trigger"]["combine"] = str(out["trigger"]["combine"]).upper()
        conds = []
        for c in out["trigger"].get("conditions") or []:
            if isinstance(c, dict):
                c = {k: v for k, v in c.items() if k in ("signal", "op", "value")}
                if c.get("value") is None:
                    c.pop("value", None)
                conds.append(c)
        out["trigger"] = {"combine": out["trigger"]["combine"], "conditions": conds}
    for k in ("setup", "stimulus", "readback"):
        if k in out:
            out[k] = [{kk: vv for kk, vv in o.items() if kk in ("op", "register", "value", "ms") and vv is not None}
                      for o in (out[k] or []) if isinstance(o, dict)]
    out["probes"] = [p for p in out["probes"] if isinstance(p, str) and p.strip()]
    return out


def parse(request: str, design: Path, client: Any = None, model: str = DEFAULT_MODEL,
          index: RtlIndex | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (intent, meta). meta: model, cost (provider-reported, None if not reported), tokens, attempts, raw replies."""
    design = design if design.is_absolute() else ROOT / design
    idx = index or RtlIndex.from_design(design)
    if client is None:
        from agent.graph.llm import OpenRouterClient
        client = OpenRouterClient(model=model, timeout_s=120)
    messages = [{"role": "system", "content": SYSTEM + "\n" + signal_menu(idx, register_map(design))},
                {"role": "user", "content": request}]
    meta: dict[str, Any] = {"model": getattr(client, "model", model), "cost": 0.0, "prompt_tokens": 0,
                            "completion_tokens": 0, "attempts": 0, "replies": []}
    last = ""
    for attempt in range(2):
        r = client(messages)
        meta["attempts"] += 1
        meta["replies"].append(r.text)
        meta["prompt_tokens"] += r.prompt_tokens
        meta["completion_tokens"] += r.completion_tokens
        meta["cost"] = None if (meta["cost"] is None or r.cost is None) else meta["cost"] + r.cost
        try:
            intent = clean(extract_json(r.text))
            bad = validate(intent, "intent")
            if not bad:
                return intent, meta
            last = "; ".join(bad)
        except (ValueError, json.JSONDecodeError) as e:
            last = str(e)
        messages += [{"role": "assistant", "content": r.text},
                     {"role": "user", "content": f"That is not valid for the schema ({last}). Reply with the JSON object only."}]
    raise ValueError(f"the request parser did not return a valid intent after {meta['attempts']} attempts: {last}")
