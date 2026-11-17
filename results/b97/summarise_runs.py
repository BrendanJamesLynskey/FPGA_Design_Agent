#!/usr/bin/env python3
"""Collect the four paired runs (A0_1, A0_2, A1_1, A1_2) from their frozen worktrees into results/b97/paired/<name>/ and write ab_summary.json and
ab_summary.md (the agent before/after). Reads only the loop's own records: history.jsonl, summary.json, the diffs and the provider-reported cost.

    python3 results/b97/summarise_runs.py [runs dir, default ~/Claude_sandbox/_worktrees/97-runs]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Claude_sandbox" / "_worktrees" / "97-runs"
NAMES = ["A0_1", "A0_2", "A1_1", "A1_2", "R2_A0_1", "R2_A0_2", "R2_A1_1", "R2_A1_2"]
PRIVATE = Path.home() / "Claude_sandbox" / "_worktrees" / "97-kb" / "runs_b97"      # the private knowledge-bank worktree


def main() -> None:
    out: dict = {"commit": "9f4305aa26bab5c69ecbca8312374960d623ede2", "model": "openai/gpt-6-luna", "runs": {}}
    for n in NAMES:
        s = SRC / n / "results" / "b97" / "run"
        if not (s / "summary.json").is_file():
            out["runs"][n] = {"status": "not finished"}
            continue
        dst = HERE / "paired" / n
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        priv = PRIVATE / n                      # the transcripts and raw model calls carry the private prompt text: they go to the private repo only
        priv.mkdir(parents=True, exist_ok=True)
        for f in s.iterdir():
            if f.name.endswith(".messages.json") or f.name == "llm_calls.json":
                shutil.copy(f, priv / f.name)
            elif f.suffix in (".json", ".jsonl", ".diff"):
                shutil.copy(f, dst / f.name)
        rows = [json.loads(l) for l in (s / "history.jsonl").read_text().splitlines()]
        visits = [r for r in rows if r.get("event") == "visit"]
        summ = json.loads((s / "summary.json").read_text())
        first_kept = next((r["iteration"] for r in visits if r.get("kept")), None)
        out["runs"][n] = {**summ, "reverted": sum(1 for r in visits if not r.get("kept")), "first_kept_visit": first_kept,
                          "tool_calls": {k: sum(r.get("tools", {}).get(k, 0) for r in visits) for k in
                                         sorted({k for r in visits for k in r.get("tools", {})})},
                          "turns": sum(r.get("turns", 0) for r in visits), "wall_s": round(sum(r.get("wall_s", 0) for r in visits), 1),
                          "per_visit": [{k: r.get(k) for k in ("iteration", "kept", "reason", "clocks_before", "clocks_after", "files_changed",
                                                               "hypothesis_note")} for r in visits]}
    (HERE / "ab_summary.json").write_text(json.dumps(out, indent=1) + "\n")
    lines = ["| run | baseline | final clocks | kept / visits | first kept at visit | reverted | model turns | USD | wall s |", "|---|---|---|---|---|---|---|---|---|"]
    for n, r in out["runs"].items():
        if r.get("status"):
            lines.append(f"| {n} | | {r['status']} | | | | | | |")
            continue
        lines.append(f"| {n} | {r['baseline_clocks']} | {r['final_clocks']} | {r['kept']} / {r['visits']} | {r['first_kept_visit']} | {r['reverted']} | "
                     f"{r['turns']} | {r['usd']:.4f} | {r['wall_s']} |")
    (HERE / "ab_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
