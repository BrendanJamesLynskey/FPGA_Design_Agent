#!/usr/bin/env python3
"""Brief 108: show that two run records differ only where the model configuration says they should.

    python tools/model_config_record_diff.py RUN_A RUN_B [--out FILE]

Compares ``config.json`` key by key and the per-role rows of ``role_usage.jsonl``. Differences under the configuration's own
keys (the resolved table, the role map, the model-config layer, the flags given) and the run's identity (id, time, paths) are
*expected*; anything else is listed as *unexpected* and makes the exit status 1. It also prints which call logs exist in
each run (``model_calls.jsonl`` for chat calls, ``claude_code_calls.jsonl`` for Claude Code calls).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: config.json keys that are the configuration itself (or follow from it)
CONFIGURATION = ("models.", "role_models.", "model_config", "explicit", "oracle_model", "profile", "roles", "harness", "cc_model", "cc_effort", "model")
#: the run's identity
IDENTITY = ("run_id", "name", "spec_md", "models_file", "isolation", "run_limits.usd")   # the run name and the cost cap are command-line choices, not model configuration


def flat(d: Any, p: str = "") -> dict[str, Any]:
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            out.update(flat(v, f"{p}{k}."))
        return out or {p.rstrip("."): {}}
    return {p.rstrip("."): d}


def load(run: Path) -> tuple[dict, list[dict]]:
    cfg = json.loads((run / "config.json").read_text())
    ru = [json.loads(l) for l in (run / "role_usage.jsonl").read_text().splitlines()] if (run / "role_usage.jsonl").is_file() else []
    return cfg, ru


def rows(run: Path, name: str) -> list[dict]:
    f = run / name
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.is_file() else []


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--out", type=Path)
    x = ap.parse_args(argv)
    (ca, ra), (cb, rb) = load(x.a), load(x.b)
    fa, fb = flat(ca), flat(cb)
    exp, unexp = [], []
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k) != fb.get(k):
            (exp if k.startswith(CONFIGURATION) or k in CONFIGURATION or k in IDENTITY else unexp).append((k, fa.get(k), fb.get(k)))
    lines = [f"# Record diff: {x.a.name} vs {x.b.name}", "", "## config.json: differences the configuration explains", ""]
    lines += [f"- `{k}`: `{json.dumps(va)}` -> `{json.dumps(vb)}`" for k, va, vb in exp if not k.startswith("models.layers")] or ["- none"]
    lines += ["", "## config.json: unexpected differences", ""] + ([f"- `{k}`: `{json.dumps(va)}` -> `{json.dumps(vb)}`" for k, va, vb in unexp] or ["- none"])
    lines += ["", "## Per role and stage (role_usage.jsonl): harness and model", "", "| stage | role | A | B |", "|---|---|---|---|"]

    def key(r: dict) -> tuple:
        return (r["stage"], r["role"])
    ma = {key(r): f"{r['harness']} {r['model']}" for r in ra}
    mb = {key(r): f"{r['harness']} {r['model']}" for r in rb}
    for k in sorted(set(ma) | set(mb)):
        lines.append(f"| {k[0]} | {k[1]} | {ma.get(k, '-')} | {mb.get(k, '-')} |" + ("" if ma.get(k) == mb.get(k) else "  (differs)"))
    lines += ["", "## Call logs", ""]
    for name in ("model_calls.jsonl", "claude_code_calls.jsonl"):
        for run in (x.a, x.b):
            r = rows(run, name)
            by = {}
            for q in r:
                kk = q.get("purpose") or q.get("role") or "?"
                by[kk] = by.get(kk, 0) + 1
            lines.append(f"- `{name}` in {run.name}: {len(r)} rows" + (f" ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))})" if by else ""))
    text = "\n".join(lines) + "\n"
    if x.out:
        x.out.write_text(text)
    print(text)
    return 1 if unexp else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
