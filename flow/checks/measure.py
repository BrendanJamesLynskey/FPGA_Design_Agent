"""Digest size against the raw reports it replaces (brief 71), in tokens approximated as characters / 4 (the convention
of knowledge/PACKS.md and flow/handover.agent_tokens).

    python3 -m flow.checks.measure designs/<d> [more designs] --scope synth --json results/71_check_suite/tokens.json

For each design: the check suite runs with no Vivado (the reports must already exist, from the build or an earlier
``--vivado auto`` run); "raw" is every record file the checks read (each counted once) plus the build's gates.json, the
text an agent would otherwise have to read; "digest" is the text the ``check`` tool returns, at each level.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flow import checks as C


def measure(design: Path, scope: str) -> dict:
    rep = C.run(design, "all", scope, "summary", vivado=None)
    recs = sorted({design / r for c in rep["checks"] for r in c.get("records") or [] if (design / r).is_file()})
    gates = design / "build" / "base" / "gates.json"
    raw = {r.name: r.stat().st_size for r in recs}
    out = {"design": design.name, "scope": rep["scope"], "verdict": "pass" if rep["pass"] else "not pass",
           "checks": {c["check"]: ("partial" if c["status"] == "pass" and c.get("incomplete") else c["status"]) for c in rep["checks"]},
           "raw_files": raw, "raw_tokens": sum(raw.values()) // 4,
           "raw_tokens_without_reset_scan": sum(v for k, v in raw.items() if not k.startswith("reset_scan")) // 4,
           "gates_json_tokens": gates.stat().st_size // 4 if gates.is_file() else None, "digest_tokens": {}}
    for lv in C.LEVELS:
        out["digest_tokens"][lv] = len(C.digest(rep, lv)) // 4
    out["digest_standard"] = C.digest(rep, "standard")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--scope", default="synth")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rows = [measure(Path(d).resolve(), a.scope) for d in a.designs]
    for r in rows:
        print(f"{r['design']:22} raw {r['raw_tokens']:>8} (+ gates.json {r['gates_json_tokens']}) digest "
              + " ".join(f"{k} {v}" for k, v in r["digest_tokens"].items()))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"method": "tokens = characters / 4", "rows": rows}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
