"""The Examples page's data (brief 195): the examples, their reference runs, the pinned setup, and one run compared with its references.

Everything is computed by ``agent.repro`` (the command line's own code): the page adds nothing. The browser names an example from a list this module builds, or a run
from the list of run directories the service built; it never names a file. Starting an example goes through ``/api/run/start`` with ``kind: "example"`` and the Stage 2
guards (confirmation, usage check, one run at a time, heavy slot); the command is ``python -m agent example run <name> --no-slot``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent.repro import compare as C
from agent.repro import registry as R
from agent.repro import runner as RN

_cache: dict[str, tuple[float, Any]] = {}
TTL = 60.0


def _cached(key: str, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < TTL:
        return hit[1]
    v = fn()
    _cache[key] = (now, v)
    return v


def preflight() -> dict[str, Any]:
    """The pin checks, without the machine-specific strings the page does not need (cached a minute: it hashes the CLI binary)."""
    def go():
        reg = R.load()
        pre = R.check(reg["pins"])
        return {"ok": pre["ok"], "checks": [{k: c[k] for k in ("name", "ok", "detail", "hard")} for c in pre["checks"]]}
    return _cached("pre", go)


def listing(root: Path) -> dict[str, Any]:
    reg = R.load()
    rows = []
    for e in reg["examples"]:
        refs = RN.references(e["name"])
        rows.append({"name": e["name"], "title": e["title"], "kind": e["kind"], "covers": e["covers"], "task": e["task"], "summary": C.reference_summary(refs) if refs else None,
                     "runs": [{"id": r.get("run_id"), "hidden_pass": (r.get("outcome") or {}).get("hidden_pass"), "tests": f"{(r.get('outcome') or {}).get('tests_passed')}/{(r.get('outcome') or {}).get('tests_total')}",
                               "rtl": ((r.get("tool_results") or {}).get("rtl_sha256") or "")[:12], "lut": (r.get("tool_results") or {}).get("lut"), "ff": (r.get("tool_results") or {}).get("ff"),
                               "wns_ns": (r.get("tool_results") or {}).get("wns_ns"), "build_id": (r.get("tool_results") or {}).get("build_id"),
                               **{k: (r.get("varies") or {}).get(k) for k in ("repair_visits", "tokens", "cost_usd", "wall_s", "rtl_lines")}} for r in refs]})
    pins = {k: v for k, v in reg["pins"].items()}
    return {"examples": rows, "pins": pins, "preflight": preflight(), "limits": list(C.LIMITS), "max_usd": reg["pins"]["max_usd"],
            "guards": ["access gate", "usage check at or above the stop refuses", "one navigator run at a time", "a heavy slot, released when the run ends", "the pinned setup is checked before anything starts (pre-flight above)"],
            "command": "python -m agent example run <name>", "compare_command": "python -m agent example compare <run directory>"}


def comparison(runs_dir: Path, rid: str) -> dict[str, Any] | None:
    f = Path(runs_dir) / rid / RN.RESULT_FILE
    try:
        rec = json.loads(f.read_text())
        c = C.compare(rec, RN.references(rec["example"]))
    except (OSError, ValueError, KeyError):
        return None
    c["result_file"] = f"runs/{rid}/{RN.RESULT_FILE}"
    return c


def example_runs(runs_dir: Path, ids: list[str]) -> list[dict[str, Any]]:
    """Run directories (from the service's list) that hold an example result: what the page offers to compare."""
    out = []
    for rid in ids:
        f = Path(runs_dir) / rid / RN.RESULT_FILE
        if f.is_file():
            try:
                r = json.loads(f.read_text())
                out.append({"id": rid, "example": r.get("example"), "hidden_pass": (r.get("outcome") or {}).get("hidden_pass")})
            except ValueError:
                continue
    return out
