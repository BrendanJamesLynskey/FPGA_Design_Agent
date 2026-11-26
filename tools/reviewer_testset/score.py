#!/usr/bin/env python3
"""Brief 227: scoring of the requirements reviewer on the labelled test set. Code only: no model produces a score.

Input: ``results.csv`` (one row per problem, condition and run: ``id, group, condition, run, flagged, n_blocking, n_findings, named, input_tokens, output_tokens``)
and ``ids.yaml``. ``named`` is decided by ``run.py`` against the private key file (a regex over the text of the blocking findings), never by a model.

Reported (with 95 % Wilson intervals):
- recall (flagged) and recall named (flagged and the missing fact named) on the fact-missing positives (groups A and D), on the borderline group B and on the
  implementation-reach group C, each apart;
- specificity on the negatives (E hard, F easy) and the false-flag rate; precision at the set's own prevalence (stated: it depends on the mix of the set);
- the two trivial reviewers (flag everything, flag nothing) for context;
- run-to-run agreement of the flag where a condition has more than one run;
- blocking questions that changed nothing: blocking findings on negatives, and blocking findings on positives that did not name the missing fact;
- group G (undiagnosed): how many were flagged, never scored.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any

import yaml


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]" if n else "0/0"


def load_rows(path: Path) -> list[dict[str, Any]]:
    out = []
    for r in csv.DictReader(path.read_text().splitlines()):
        out.append({**r, "run": int(r["run"]), "flagged": r["flagged"] == "1", "named": r["named"] == "1", "n_blocking": int(r["n_blocking"]), "n_findings": int(r["n_findings"])})
    return out


def first_run(rows: list[dict[str, Any]], cond: str) -> dict[str, dict[str, Any]]:
    """One row per id for a condition: run 1 (the pre-registered primary); the other runs are used only for run-to-run agreement."""
    return {r["id"]: r for r in rows if r["condition"] == cond and r["run"] == 1}


def score(rows: list[dict[str, Any]], ids: dict[str, Any], cond: str) -> dict[str, Any]:
    g = ids["groups"]
    runs = first_run(rows, cond)
    grp = lambda *names: [r for r in runs.values() if r["group"] in names] if "U" in names else [runs[i] for n in names for i in g[n]["ids"] if i in runs]
    fm, border, impl = grp("A", "D"), grp("B"), grp("C")
    neg_hard, neg_easy = grp("E"), grp("F")
    neg = neg_hard + neg_easy
    pos_all = fm + border + impl

    def rec(rs: list[dict[str, Any]]) -> dict[str, Any]:
        return {"n": len(rs), "flagged": sum(r["flagged"] for r in rs), "named": sum(r["flagged"] and r["named"] for r in rs)}
    tp, fp = sum(r["flagged"] for r in fm), sum(r["flagged"] for r in neg)
    out = {"condition": cond, "fact_missing": rec(fm), "borderline": rec(border), "implementation": rec(impl),
           "negatives": {"n": len(neg), "flagged": fp, "hard_flagged": sum(r["flagged"] for r in neg_hard), "hard_n": len(neg_hard),
                         "easy_flagged": sum(r["flagged"] for r in neg_easy), "easy_n": len(neg_easy)},
           "precision_fact_missing": (tp / (tp + fp)) if tp + fp else None, "prevalence": len(fm) / (len(fm) + len(neg)) if fm or neg else None,
           "blocking_questions_on_negatives": sum(r["n_blocking"] for r in neg), "blocking_questions_on_positives_unnamed": sum(r["n_blocking"] for r in pos_all if not (r["flagged"] and r["named"])),
           "g_flagged": rec(grp("G")), "u_flagged": rec(grp("U")), "findings_per_problem": (sum(r["n_findings"] for r in runs.values()) / len(runs)) if runs else None,
           "input_tokens": sum(int(r["input_tokens"] or 0) for r in runs.values()), "output_tokens": sum(int(r["output_tokens"] or 0) for r in runs.values())}
    by = {}
    for r in rows:
        if r["condition"] == cond:
            by.setdefault(r["id"], []).append(r)
    multi = {i: v for i, v in by.items() if len(v) > 1}
    out["run_to_run"] = {"problems": len(multi), "same_flag": sum(len({x["flagged"] for x in v}) == 1 for v in multi.values())}
    return out


def render(s: dict[str, Any]) -> str:
    fm, neg = s["fact_missing"], s["negatives"]
    L = [f"### Condition `{s['condition']}` (run 1 of each problem)", "",
         "| Measure | Result |", "|---|---|",
         f"| Recall, fact-missing positives (A and D): flagged | {fmt(fm['flagged'], fm['n'])} |",
         f"| Recall, fact-missing positives: flagged and the missing fact named | {fmt(fm['named'], fm['n'])} |",
         f"| Borderline positives (B), apart: flagged / named | {fmt(s['borderline']['flagged'], s['borderline']['n'])} / {fmt(s['borderline']['named'], s['borderline']['n'])} |",
         f"| Test-reaches-into-implementation (C), apart: flagged / named | {fmt(s['implementation']['flagged'], s['implementation']['n'])} / {fmt(s['implementation']['named'], s['implementation']['n'])} |",
         f"| Specificity on all negatives (E and F): not flagged | {fmt(neg['n'] - neg['flagged'], neg['n'])} |",
         f"| Specificity, hard negatives (E) / easy negatives (F) | {fmt(neg['hard_n'] - neg['hard_flagged'], neg['hard_n'])} / {fmt(neg['easy_n'] - neg['easy_flagged'], neg['easy_n'])} |",
         f"| Precision for the fact-missing positives (at this set's prevalence {s['prevalence'] * 100:.0f}% positives) | "
         + (f"{s['precision_fact_missing'] * 100:.0f}%" if s["precision_fact_missing"] is not None else "n/a") + " |",
         f"| Flag everything (reference): recall / specificity | 100% / 0% |", f"| Flag nothing (reference): recall / specificity | 0% / 100% |",
         f"| Blocking questions that changed nothing: on negatives / on positives without the fact named | {s['blocking_questions_on_negatives']} / {s['blocking_questions_on_positives_unnamed']} |",
         f"| Run-to-run: same flag on both runs | {s['run_to_run']['same_flag']}/{s['run_to_run']['problems']} |",
         f"| Group G (undiagnosed candidates): flagged | {s['g_flagged']['flagged']}/{s['g_flagged']['n']} (not scored) |",
         f"| Unlabelled agentic problems (U, no group): flagged | {s['u_flagged']['flagged']}/{s['u_flagged']['n']} (a flag rate, not a score) |",
         f"| Findings per problem (mean) | {s['findings_per_problem']:.2f} |" if s["findings_per_problem"] is not None else "| Findings per problem | n/a |",
         f"| Tokens (input / output), run 1 | {s['input_tokens']:,} / {s['output_tokens']:,} |", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("results")
    ap.add_argument("--ids", default=str(Path(__file__).with_name("ids.yaml")))
    ap.add_argument("--condition", action="append")
    a = ap.parse_args(argv)
    rows = load_rows(Path(a.results))
    ids = yaml.safe_load(Path(a.ids).read_text())
    conds = a.condition or sorted({r["condition"] for r in rows})
    print("\n".join(render(score(rows, ids, c)) for c in conds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
