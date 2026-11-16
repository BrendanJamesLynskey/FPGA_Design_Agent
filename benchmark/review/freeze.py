#!/usr/bin/env python3
"""Records the hashes that pin a review-benchmark evaluation before any scored run (brief 84; eval run checklist).

    freeze.py --bench <review84 dir> --claude-bin <pinned binary> --out results/84_review/freeze.json

The hashes are of the scorer, the runner, the reviewer's system prompt, the benchmark manifest (design hashes), the truth
files (their hash only, never their content) and the CLI binary. A later change to any of them shows as a different hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree(p: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(p).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=Path, required=True)
    ap.add_argument("--claude-bin", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    from flow.review import judge as J
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    rec = {"public_repo_head": head, "scorer_sha256": sha(ROOT / "benchmark/review/score.py"), "runner_sha256": sha(ROOT / "benchmark/review/run_bench.py"),
           "review_pipeline_sha256": {f: sha(ROOT / "flow/review" / f) for f in ("__init__.py", "collect.py", "judge.py", "prepare.py", "schema.py", "understand.py", "improve.py")},
           "system_prompt_sha256": hashlib.sha256(J.SYSTEM.encode()).hexdigest(), "prompt_version": J.PROMPT_VERSION, "model": J.DEFAULT_MODEL,
           "manifest_sha256": sha(a.bench / "MANIFEST.json"), "truth_tree_sha256": tree(a.bench / "truth"), "designs_tree_sha256": tree(a.bench / "designs"),
           "improvements_sha256": sha(a.bench / "improvements.yaml"), "claude_binary_sha256": sha(a.claude_bin),
           "claude_version": subprocess.run([str(a.claude_bin), "--version"], capture_output=True, text=True).stdout.strip()}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
