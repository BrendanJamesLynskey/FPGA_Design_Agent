#!/usr/bin/env python3
"""Offline replay of the spec-test role against a saved run's final design (brief 08f). No agent run, no Vivado.

    python3 tools/spectest_replay.py replay <run_dir> [--task-dir DIR] [--label NAME] [--out results/08f]
    python3 tools/spectest_replay.py table results/08f

``replay`` copies the saved design (spec.md, the interview record in spec.yaml, rtl/, build.yaml, data/, the no-shell marker, and
the agent's own tests, which only the triage step reads) into a scratch directory under runs/_spectest_replay/, then runs the
real gate once (``agent.graph.spectest.gate``: the spec-test role, the bench against the RTL, and on a failure the triage step
and at most one bench repair). Nothing is repaired in the design, so a ``design_wrong`` verdict is a catch. The result and the
generated bench go to <out>/<label>/. ``table`` joins the replays with the hidden result of the saved run
(results/course/<task>/run_N.json) into the replay table.

The scratch directory never holds anything the role may not see: the role is given its inputs as prompt text only."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COPY = ("spec.md", "spec.yaml", "build.yaml", "__init__.py", ".no_shell")


def scratch_design(run_dir: Path, label: str) -> Path:
    src = next(p for p in sorted(run_dir.iterdir()) if p.is_dir() and (p / "rtl").is_dir())
    dst = ROOT / "runs" / "_spectest_replay" / label / src.name
    shutil.rmtree(dst.parent, ignore_errors=True)
    dst.mkdir(parents=True)
    for n in COPY:
        if (src / n).is_file():
            shutil.copy2(src / n, dst / n)
    for d in ("rtl", "data", "tests"):
        if (src / d).is_dir():
            shutil.copytree(src / d, dst / d, ignore=shutil.ignore_patterns("__pycache__", "build"))
    return dst


def replay(run_dir: Path, label: str, out: Path, model: str, max_loops: int) -> dict:
    from agent.core.runner import LocalRunner
    from agent.graph import spectest
    d = scratch_design(run_dir, label)
    log = out / label / "claude_code_calls.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    role = spectest.cc_llm(model, "medium", log, "spectest")
    tri = spectest.cc_llm(model, "low", log, "spectest_triage")
    board = json.loads((run_dir / "config.json").read_text()).get("board", "nexys_a7_100t") if (run_dir / "config.json").is_file() \
        else "nexys_a7_100t"
    res = spectest.gate(d, board, LocalRunner(), role, tri, max_loops=max_loops)
    st = spectest.load_state(d)
    dest = out / label
    (dest / "spectest").mkdir(parents=True, exist_ok=True)
    for f in (d / "spectest").glob("*.py"):
        shutil.copy2(f, dest / "spectest" / f.name)
    first_run = next((h for h in st["history"] if h.get("step") == "run"), {})
    first_triage = next((h for h in st["history"] if h.get("step") == "triage"), {})
    rec = {"label": label, "run_dir": run_dir.name, "gate": res, "state": {k: v for k, v in st.items() if k != "history"},
           "history": st["history"], "first_run_ok": first_run.get("ok"), "first_run_failing": first_run.get("failing"),
           "first_triage": first_triage.get("verdict"), "first_triage_reason": first_triage.get("reason")}
    (dest / "result.json").write_text(json.dumps(rec, indent=1))
    return rec


def table(out: Path) -> str:
    rows = []
    for f in sorted(out.glob("*/result.json")):
        r = json.loads(f.read_text())
        meta = json.loads((f.parent / "meta.json").read_text()) if (f.parent / "meta.json").is_file() else {}
        rows.append((r, meta))
    lines = ["| replay | known hidden result | bench's first run | triage of the first failure | final gate | bench repaired |",
             "|---|---|---|---|---|---|"]
    for r, meta in rows:
        first = "pass" if r["first_run_ok"] else ("FAIL: " + ", ".join(r["first_run_failing"] or ["did not build"]))
        lines.append(f"| {r['label']} | {meta.get('known', '?')} | {first} | {r.get('first_triage') or '-'} | "
                     f"{r['gate']['verdict']} | {r['state'].get('bench_repaired')} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("run_dir", type=Path)
    r.add_argument("--label", required=True)
    r.add_argument("--out", type=Path, default=ROOT / "results" / "08f")
    r.add_argument("--model", default="claude-sonnet-5-5")
    r.add_argument("--max-loops", type=int, default=2)
    t = sub.add_parser("table")
    t.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "replay":
        rec = replay(a.run_dir.resolve(), a.label, a.out, a.model, a.max_loops)
        print(json.dumps({k: rec[k] for k in ("label", "gate", "first_run_ok", "first_run_failing", "first_triage")}, indent=1))
        return 0
    print(table(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
