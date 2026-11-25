#!/usr/bin/env python3
"""The cycle-cost line of every trading block (brief 190, item 26; idea from Edwards 2026, ch 2: every block states what it adds).

    python3 flow/cycle_cost.py --check          # every trading design: values match their records, tables in the docs are current
    python3 flow/cycle_cost.py --write          # (re)write the tables between the markers in each design's doc
    python3 flow/cycle_cost.py --coverage       # which designs on the trading list have a cycle_cost.yaml

A block on a trading path (feed in, order out) states **what it adds to the path in clocks, between which two events, and why it adds zero where it
adds zero**, so the path total is a sum of lines that can be audited, not one number nobody can take apart (docs/documentation_standard.md,
"Trading blocks: the cycle-cost line"). Each such design has ``designs/<d>/cycle_cost.yaml``:

    design: <d>
    doc: docs/<file>.md            # the table goes between <!-- cycle_cost:begin --> and <!-- cycle_cost:end --> in this file
    unit: "<what a clock is, and the clock period>"
    rows:
      - id: <short id>
        block: <module or stage>
        from_event: <text>         to_event: <text>
        record: results/...json    to: [json, path]    from: [json, path] (optional; absent = 0)    from_record: (optional; default: record)
        why: <required when the cost is 0, and when the block is partly off the path>
    totals:
      - label: <text>   sum_of: [row ids]   record: results/...json   path: [json, path]     # the sum must equal the record's own total

Every clocks figure is **computed from a committed record** (the difference of two fields), never typed; the check fails if a record cannot be read, a
row with 0 clocks has no ``why``, a total is not the sum of its rows or not the record's own figure, or the doc's table differs from the rendering.
The path of a block that is not a trading block is not this tool's business: ``TRADING`` lists the designs that must have the file (advisory:
``--coverage`` reports a missing one; ``--check`` does not fail for it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
BEGIN, END = "<!-- cycle_cost:begin -->", "<!-- cycle_cost:end -->"
#: designs whose blocks sit on a feed-in to order-out path; a new trading design is added here
TRADING = ("b110_itch_ouch", "b58a_trigger", "b119_tcp_fast")


def _get(root: Path, record: str, path: list[str]) -> float:
    d: Any = json.loads((root / record).read_text())
    for k in path:
        d = d[k]
    if isinstance(d, bool) or not isinstance(d, (int, float)):
        raise ValueError(f"{record} {path}: not a number ({d!r})")
    return d


def load(design: Path) -> dict[str, Any] | None:
    f = design / "cycle_cost.yaml"
    return yaml.safe_load(f.read_text()) if f.is_file() else None


def evaluate(spec: dict[str, Any], root: Path = ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """(rows with their computed clocks, totals with their sums, problems)."""
    probs: list[str] = []
    rows: list[dict[str, Any]] = []
    for r in spec.get("rows") or []:
        try:
            to = _get(root, r["record"], r["to"])
            fr = _get(root, r.get("from_record", r["record"]), r["from"]) if r.get("from") else 0
        except (OSError, KeyError, ValueError, TypeError) as e:
            probs.append(f"row {r.get('id')}: {type(e).__name__}: {e}")
            continue
        c = to - fr
        if c == int(c):
            c = int(c)
        if c < 0 and not r.get("why"):
            probs.append(f"row {r['id']}: negative cost {c} needs a why (the block starts before its input event)")
        if c == 0 and not str(r.get("why") or "").strip():
            probs.append(f"row {r['id']}: adds 0 clocks and says no why")
        rows.append({**r, "clocks": c})
    by = {r["id"]: r for r in rows}
    totals: list[dict[str, Any]] = []
    for t in spec.get("totals") or []:
        try:
            s = sum(by[i]["clocks"] for i in t["sum_of"])
            rec = _get(root, t["record"], t["path"])
        except (KeyError, OSError, ValueError, TypeError) as e:
            probs.append(f"total {t.get('label')}: {type(e).__name__}: {e}")
            continue
        if s != rec:
            probs.append(f"total {t['label']}: the rows sum to {s} but the record says {rec}")
        totals.append({**t, "sum": s, "record_value": rec})
    return rows, totals, probs


def render(spec: dict[str, Any], rows: list[dict[str, Any]], totals: list[dict[str, Any]]) -> str:
    out = [f"Cycle cost of each block on the path ({spec['unit']}). Each figure is the difference of two fields of the record named; a row of 0 says why.", "",
           "| Block | Adds (clocks) | From event | To event | Record | Why |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['block']} | {r['clocks']} | {r['from_event']} | {r['to_event']} | `{r['record']}` | {str(r.get('why') or '').strip() or '-'} |")
    for t in totals:
        out.append(f"| **{t['label']}** | **{t['sum']}** | | | `{t['record']}` | sum of {', '.join(t['sum_of'])}; equals the record's own figure |")
    return "\n".join(out)


def _doc_problem(design: Path, spec: dict[str, Any], text: str) -> str | None:
    f = design / spec["doc"]
    if not f.is_file():
        return f"{f}: the doc named in cycle_cost.yaml does not exist"
    t = f.read_text()
    if BEGIN not in t or END not in t:
        return f"{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}: no {BEGIN} ... {END} markers"
    cur = t.split(BEGIN, 1)[1].split(END, 1)[0].strip("\n")
    return None if cur == text else f"{f.name}: the cycle-cost table is not current (run: python3 flow/cycle_cost.py --write)"


def check(root: Path = ROOT, designs: tuple[str, ...] | None = None) -> list[str]:
    probs: list[str] = []
    for d in designs or sorted(p.name for p in (root / "designs").iterdir() if (p / "cycle_cost.yaml").is_file()):
        design = root / "designs" / d
        spec = load(design)
        if spec is None:
            continue
        rows, totals, p = evaluate(spec, root)
        probs += [f"{d}: {x}" for x in p]
        if not p:
            q = _doc_problem(design, spec, render(spec, rows, totals))
            if q:
                probs.append(f"{d}: {q}")
    return probs


def write(root: Path = ROOT) -> list[Path]:
    done = []
    for design in sorted((root / "designs").iterdir()):
        spec = load(design)
        if spec is None:
            continue
        rows, totals, p = evaluate(spec, root)
        if p:
            raise SystemExit(f"{design.name}: " + "; ".join(p))
        f = design / spec["doc"]
        t = f.read_text()
        head, rest = t.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        f.write_text(f"{head}{BEGIN}\n{render(spec, rows, totals)}\n{END}{tail}")
        done.append(f)
    return done


def coverage(root: Path = ROOT) -> dict[str, bool]:
    return {d: (root / "designs" / d / "cycle_cost.yaml").is_file() for d in TRADING}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--coverage", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        for f in write():
            print("wrote", f.relative_to(ROOT))
        return 0
    if a.coverage:
        cov = coverage()
        for d, ok in cov.items():
            print(f"{'ok     ' if ok else 'MISSING'} {d}")
        return 0
    probs = check()
    for p in probs:
        print("problem:", p)
    print("cycle cost: ok" if not probs else f"cycle cost: {len(probs)} problem(s)")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
