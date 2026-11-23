#!/usr/bin/env python3
"""Second-method rule for latency figures (brief 189 item 7; idea from Edwards 2026, ch 15). Advisory: ``enforced: false``.

Rule. A latency figure is quoted only with two independent measurements that agree, and with its start and end events named
(docs/latency_definitions.md, the owner's latency-path-clarity rule). The measurement is itself a design that can be wrong: a counter
incremented in one process and read in another on the same clock edge reads one too high or one too low depending on the simulator's
process order, and a bench that reads the counter and one that reads the simulator's clock can both print a number, only one of them true.

A measurement record (JSON) looks like::

    {"claim": "decoded_event latency", "latency_clocks": 3, "start_event": "in_valid sampled", "end_event": "out_valid first seen high",
     "tolerance_clocks": 0,
     "methods": [{"name": "stamp counter", "kind": "counter", "value": 3},
                 {"name": "simulator time / period", "kind": "simulator_time", "value": 3}]}

``kind`` is the way the figure was obtained; two methods of the same kind are not independent (two counters that share a process are one
method). Known kinds: counter, simulator_time, waveform_marker, hardware_counter, external_instrument, analytic.
Findings: LAT-X-01 fewer than two methods; LAT-X-02 two methods share a kind (fewer than two independent kinds); LAT-X-03 the methods
disagree (beyond ``tolerance_clocks``, default 0), or the quoted figure differs from them; LAT-X-04 start or end event not named;
LAT-X-05 (a scan of existing files) a latency record with no ``methods`` list.

    python3 -m flow.latency.crosscheck [PATH ...] [--json OUT]       # with no path: results/**/*latency*.json"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
KINDS = ("counter", "simulator_time", "waveform_marker", "hardware_counter", "external_instrument", "analytic")


def check_record(rec: dict[str, Any], where: str = "-") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(code: str, msg: str) -> None:
        out.append({"code": code, "where": where, "claim": rec.get("claim"), "message": msg})

    for k in ("start_event", "end_event"):
        if not str(rec.get(k) or "").strip():
            add("LAT-X-04", f"{k} is not named: a latency figure names its start and end events")
    ms = [m for m in rec.get("methods") or [] if isinstance(m, dict) and isinstance(m.get("value"), (int, float))]
    if len(ms) < 2:
        add("LAT-X-01", f"{len(ms)} method(s) recorded; a second, independent method is required before the figure is quoted")
        return out
    kinds = {m.get("kind") for m in ms}
    if len(kinds) < 2:
        add("LAT-X-02", f"all methods are of kind {sorted(map(str, kinds))}: not independent")
    tol = float(rec.get("tolerance_clocks", 0) or 0)
    vals = [float(m["value"]) for m in ms]
    if max(vals) - min(vals) > tol:
        add("LAT-X-03", "methods disagree: " + ", ".join(f"{m.get('name', m.get('kind'))} = {m['value']}" for m in ms) + f" (tolerance {tol:g})")
    elif isinstance(rec.get("latency_clocks"), (int, float)) and abs(float(rec["latency_clocks"]) - vals[0]) > tol:
        add("LAT-X-03", f"quoted latency_clocks = {rec['latency_clocks']} but the methods give {vals[0]:g}")
    return out


def scan_file(p: Path, root: Path = ROOT) -> list[dict[str, Any]]:
    try:
        rel = str(p.relative_to(root))
    except ValueError:
        rel = str(p)
    try:
        obj = json.loads(p.read_text())
    except (OSError, ValueError):
        return []
    recs = obj if isinstance(obj, list) else [obj]
    out: list[dict[str, Any]] = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        where = rel + (f"[{i}]" if isinstance(obj, list) else "")
        if "methods" in r:
            out += check_record(r, where)
        elif "latency_clocks" in r or "latency" in p.name.lower():
            out.append({"code": "LAT-X-05", "where": where, "claim": r.get("claim"),
                        "message": "latency record without a methods list: one unrecorded method"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json", dest="out")
    a = ap.parse_args(argv)
    paths = [Path(p) for p in a.paths] or sorted(ROOT.glob("results/**/*latency*.json"))
    findings = [f for p in paths for f in scan_file(p)]
    rec = {"enforced": False, "files_scanned": len(paths), "findings": findings}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    for f in findings:
        print(f"{f['code']} {f['where']}: {f['message']}")
    print(f"{len(findings)} advisory finding(s) in {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
