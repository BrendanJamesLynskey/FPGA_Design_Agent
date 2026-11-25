#!/usr/bin/env python3
"""Latency histograms split by class (brief 189 item 9; idea from Edwards 2026, ch 17). Advisory: ``enforced: false``.

When a latency histogram has two peaks, widening the bins hides the cause. Split the samples by a class instead (message type, the
position of the message in its packet, the byte lane the message ends in, book state, transmit contention) and see which split makes
each class a single narrow peak. ``split`` gives a histogram and a summary for every class value; ``explained`` gives, for each
candidate class, the share of the variance of the latency that the class explains (the between-class sum of squares over the total,
eta squared): 1.0 means each class value has one latency. ``packet_position`` and ``class_label`` build the two classes the hardware
probe would carry (message type, index of the message in its packet), so the same helper serves a simulation, a board capture and the
in-fabric histogram's class input.

    python3 -m flow.latency.split_hist FILE.json --rows PATH.TO.LIST --value KEY --by KEY [--by KEY ...] [--out OUT.json]

``--rows`` is a dotted path to a list of per-sample records inside the JSON (use ``.`` for the file's top-level list)."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def packet_position(index: int) -> str:
    """Position of a message in its packet, from its zero-based index: 'first', 'second', 'third', 'fourth', 'fifth_or_later'."""
    return ("first", "second", "third", "fourth")[index] if 0 <= index < 4 else "fifth_or_later"


def class_label(msg_type: str, index_in_packet: int) -> str:
    return f"{msg_type}/{packet_position(index_in_packet)}"


def histogram(values: Iterable[float]) -> dict[str, int]:
    return {str(k): v for k, v in sorted(Counter(values).items())}


def summary(values: list[float]) -> dict[str, Any]:
    s = sorted(values)
    return {"n": len(s), "min": s[0], "median": statistics.median(s), "max": s[-1], "peaks": sorted(set(s)),
            "histogram": histogram(s)} if s else {"n": 0}


def split(rows: list[dict[str, Any]], value: str, by: str) -> dict[str, dict[str, Any]]:
    """{class value: summary of ``value``} over the rows that have both keys."""
    groups: dict[str, list[float]] = {}
    for r in rows:
        if value in r and by in r:
            groups.setdefault(str(r[by]), []).append(r[value])
    return {k: summary(v) for k, v in sorted(groups.items(), key=lambda kv: (len(kv[0]), kv[0]))}


def explained(rows: list[dict[str, Any]], value: str, by: str) -> float | None:
    """Share of the variance of ``value`` explained by class ``by`` (eta squared); None when the value does not vary."""
    vals = [r[value] for r in rows if value in r and by in r]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    total = sum((v - mean) ** 2 for v in vals)
    if total == 0:
        return None
    groups: dict[str, list[float]] = {}
    for r in rows:
        if value in r and by in r:
            groups.setdefault(str(r[by]), []).append(r[value])
    between = sum(len(g) * (sum(g) / len(g) - mean) ** 2 for g in groups.values())
    return round(between / total, 4)


def analyse(rows: list[dict[str, Any]], value: str, classes: list[str]) -> dict[str, Any]:
    vals = [r[value] for r in rows if value in r]
    out: dict[str, Any] = {"value": value, "all": summary(vals), "splits": {}}
    for c in classes:
        out["splits"][c] = {"variance_explained": explained(rows, value, c), "classes": split(rows, value, c)}
    ranked = sorted(((v["variance_explained"], c) for c, v in out["splits"].items() if v["variance_explained"] is not None), reverse=True)
    out["best_split"] = ranked[0][1] if ranked else None
    out["bimodal"] = len(out["all"].get("peaks", [])) > 1
    return out


def _dig(obj: Any, path: str) -> Any:
    for part in [p for p in path.split(".") if p]:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--rows", default=".")
    ap.add_argument("--value", required=True)
    ap.add_argument("--by", action="append", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows = _dig(json.loads(Path(a.file).read_text()), a.rows)
    rec = {"enforced": False, "source": a.file, "rows_path": a.rows, **analyse(rows, a.value, a.by)}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    print(f"{a.value}: n={rec['all']['n']} peaks={rec['all'].get('peaks')} best split: {rec['best_split']}")
    for c, v in rec["splits"].items():
        print(f"  by {c}: variance explained {v['variance_explained']}; " + "; ".join(f"{k}: {s['histogram']}" for k, s in v["classes"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
