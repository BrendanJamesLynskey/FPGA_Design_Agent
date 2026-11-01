"""One trace format for both harnesses (Deep Agents 05b, Claude Code 05c) and for replay.

JSONL, one record per event, ``v`` = 1:

``kind: "model"``  harness, model, tokens ``{input, output}``, ``cost_usd`` (the provider-reported cost, or the
                   string ``"unreported"``: a cost is never estimated), stage, seconds, ``fake`` (true for a
                   scripted or replayed model).
``kind: "tool"``   tool, arguments, result (``ok``, ``refused``, ``rule``, ``output`` clipped), stage, seconds.

Strings are redacted before they are written (``agent.core.security.redact``). The record shape follows the
HW Design Space Agent's tracer (BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6, ``agent/trace.py``):
append-only JSONL, redaction as the last step before disk.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from agent.core.security import redact_obj

TRACE_VERSION = 1
MODEL_FIELDS = ("harness", "model", "tokens", "cost_usd", "stage", "seconds", "fake")
TOOL_FIELDS = ("tool", "arguments", "result", "stage", "seconds")


class Trace:
    def __init__(self, path: Path | None = None, harness: str = "core"):
        self.path = path
        self.harness = harness
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._seq = 0
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, rec: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            rec = redact_obj({"v": TRACE_VERSION, "seq": self._seq, "t": round(time.time(), 3), **rec})
            self.records.append(rec)
            if self.path:
                with self.path.open("a") as f:
                    f.write(json.dumps(rec, default=str) + "\n")

    def model(self, model: str, tokens: dict[str, int] | None, cost_usd: float | str, stage: str, seconds: float = 0.0,
              fake: bool = False) -> None:
        if not isinstance(cost_usd, (int, float)) and cost_usd != "unreported":
            raise ValueError("cost_usd is the provider-reported number or the string 'unreported'")
        self._write({"kind": "model", "harness": self.harness, "model": model,
                     "tokens": tokens or {"input": 0, "output": 0}, "cost_usd": cost_usd, "stage": stage,
                     "seconds": seconds, "fake": fake})

    def tool(self, name: str, arguments: dict[str, Any], result: dict[str, Any], stage: str) -> None:
        keep = {k: result.get(k) for k in ("ok", "refused", "rule", "output") if k in result}
        self._write({"kind": "tool", "tool": name, "arguments": arguments, "result": keep, "stage": stage,
                     "seconds": result.get("seconds", 0.0)})


def read_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
