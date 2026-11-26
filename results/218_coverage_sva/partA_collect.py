#!/usr/bin/env python3
"""Brief 218 Part A: collect the six pipeline runs (flow/sva_req.py on three pilot designs, two runs each) into committed result files.

    python3 results/218_coverage_sva/partA_collect.py <scratch root holding p1_clkmeter/{a,b}, p2_bram_rom/{a,b}, p3_crc_engine/{a,b}>

Writes ``partA/runs.csv`` (one row per design and run: the outcome counts and the graded primary column ``with_evidence``), ``partA/rows.csv``
(one row per requirement and run: status, the property, its English reading, the reason), ``partA/summary.md`` and the paired numbers through
``tools/run_stats/graded.py``: a requirement count is compared between the two runs of each design (the stability of the step), not between arms,
because Part A has one arm. The ``before`` column is the count of requirement rows that had a proved formal property in the pilot's design (read from
its ``verif/formal`` folder: none)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools" / "run_stats"))
import graded  # noqa: E402

DESIGNS = ("p1_clkmeter", "p2_bram_rom", "p3_crc_engine")
PILOT = {"p1_clkmeter": "run1", "p2_bram_rom": "run1", "p3_crc_engine": "run2"}
STATUSES = ("proved", "bounded", "vacuous", "failed", "mismatch", "unusable", "sim_only", "error", "not_run")


def main(scratch: Path) -> None:
    out = HERE / "partA"
    out.mkdir(exist_ok=True)
    runs, rows = [], []
    for d in DESIGNS:
        before = len(list((ROOT / "pilots" / "209" / d / PILOT[d] / "design" / "verif" / "formal").glob("*.sby"))) if (ROOT / "pilots" / "209" / d / PILOT[d] / "design" / "verif" / "formal").is_dir() else 0
        for k in ("a", "b"):
            ev = json.loads((scratch / d / k / "build" / "verif" / "sva" / "evidence.json").read_text())
            c = ev["counts"]
            reqs = ev["requirements"]
            runs.append({"id": d, "seed": k, "arm": "pipeline", "candidates": len(reqs), "skipped": len(ev["skipped"]),
                         **{s: c.get(s, 0) for s in STATUSES}, "with_evidence": c.get("proved", 0) + c.get("bounded", 0), "before_formal_jobs": before,
                         "module": ev.get("module"), "formal_tool": ev.get("formal_tool")})
            for rid, r in reqs.items():
                p = r.get("property") or {}
                rows.append({"design": d, "run": k, "id": rid, "status": r["status"], "requirement": r.get("text"),
                             "property": (f"{p.get('kind')}: ante {p.get('ante')}; cons {p.get('cons')}" if p else ""), "back_translation": r.get("back_translation", ""),
                             "why": r.get("why", ""), "seconds": r.get("seconds", "")})
    with (out / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0]))
        w.writeheader()
        w.writerows(runs)
    with (out / "rows.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = ["| design | run | candidates | skipped | proved | bounded | vacuous | failed | mismatch | unusable | sim_only | error | with evidence |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        lines.append(f"| {r['id']} | {r['seed']} | {r['candidates']} | {r['skipped']} | {r['proved']} | {r['bounded']} | {r['vacuous']} | {r['failed']} | {r['mismatch']} | "
                     f"{r['unusable']} | {r['sim_only']} | {r['error']} | {r['with_evidence']} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    # why the unusable rows are unusable, by the generator's own reason (a keyword rule, listed here so the count is reproducible)
    cats: dict[str, int] = {"the requirement gives no address, bit position or encoding": 0, "the requirement describes internal state the ports do not show": 0, "another reason": 0}
    for r in rows:
        if r["status"] != "unusable":
            continue
        w = r["why"].lower()
        if any(k in w for k in ("address", "encoding", "bit position")):
            cats["the requirement gives no address, bit position or encoding"] += 1
        elif any(k in w for k in ("internal", "not visible", "cannot be read", "not observable")):
            cats["the requirement describes internal state the ports do not show"] += 1
        else:
            cats["another reason"] += 1
    n_un = sum(cats.values())
    (out / "unusable_reasons.md").write_text(f"{n_un} `unusable` rows in the six runs ({len(rows)} candidate rows), by the first matching keyword in the generator's reason "
                                              "(address, encoding, bit position; then internal, not visible, cannot be read, not observable):\n\n"
                                              + "\n".join(f"- {k}: {v}" for k, v in cats.items()) + "\n")
    # the stability of the step: run b against run a on the same designs (arm = the run letter), through the paired tool of tools/run_stats
    by_arm = [{**r, "arm": r["seed"], "seed": 1} for r in runs]
    txt = graded.report(by_arm, "a", ["with_evidence", "proved", "mismatch", "unusable", "vacuous", "failed"])
    (out / "stats.txt").write_text(txt + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
