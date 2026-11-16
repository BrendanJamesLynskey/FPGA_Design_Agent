#!/usr/bin/env python3
"""Runs the review benchmark (brief 84): each design in a split, k repeats, one arm. Writes review.json per run.

    run_bench.py --bench <review84 dir> --arm agent|baseline --split dev|heldout|all --k 3 --out <reviews dir> [--jobs 3]
                 [--claude-bin <pinned binary>] [--expect-cli 2.1.321] [--prompt-sha <sha>] [--ids rb01,rb02]

Isolation: the reviewer is given ``designs/<id>/`` only (copied by flow/review/prepare.py into runs/review/); the truth, the
authoring copies and the probes are in sibling directories it is never pointed at, and the model call has no tools. The
design is passed under its opaque id. Preflight (house rule "Evals: pin the CLI"): the binary's version must equal
``--expect-cli``; on a mismatch nothing runs and PREFLIGHT_FAIL is written. A run that already has a review.json is skipped,
so an interrupted sweep resumes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from flow.review import review  # noqa: E402
from flow.review import judge as J  # noqa: E402


def preflight(claude_bin: str, expect: str, out: Path) -> dict:
    exe = shutil.which(claude_bin) or claude_bin
    ver = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(Path(exe).resolve().read_bytes()).hexdigest()
    rec = {"claude_bin": str(Path(exe).resolve()), "version": ver, "sha256": sha, "expected": expect, "prompt_version": J.PROMPT_VERSION,
           "system_prompt_sha256": hashlib.sha256(J.SYSTEM.encode()).hexdigest(), "model": J.DEFAULT_MODEL, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not ver.startswith(expect):
        (out / "PREFLIGHT_FAIL").write_text(json.dumps(rec, indent=1))
        raise SystemExit(f"PREFLIGHT_FAIL: {ver!r} is not {expect}")
    return rec


def one(bench: Path, rid: str, arm: str, k: int, out: Path, claude_bin: str, model: str, effort: str) -> str:
    dst = out / arm / rid / f"r{k}"
    if (dst / "review.json").is_file():
        return f"{rid}/r{k}: kept"
    try:
        rep = review(bench / "designs" / rid, dst, use_judge=(arm == "agent"), model=model, effort=effort, claude_bin=claude_bin,
                     name=f"{rid}_{arm}_r{k}", tag=f"{rid}_r{k}", label=f"{rid}_r{k}")
    except Exception as e:                                         # a crashed run is recorded, never dropped
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "NOT_RUN.txt").write_text(f"{type(e).__name__}: {e}\n")
        return f"{rid}/r{k}: NOT RUN ({type(e).__name__}: {str(e)[:120]})"
    return f"{rid}/r{k}: {sum(1 for f in rep['findings'] if f['severity'] != 'info')} findings, judge_ran={rep['judge']['ran']}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=Path, required=True)
    ap.add_argument("--arm", required=True, choices=("agent", "baseline"))
    ap.add_argument("--split", default="heldout", choices=("dev", "heldout", "all"))
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--expect-cli", default="2.1.321")
    ap.add_argument("--model", default=J.DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--ids")
    a = ap.parse_args(argv)
    man = json.loads((a.bench / "MANIFEST.json").read_text())
    ids = sorted(r for r, v in man.items() if a.split == "all" or v["split"] == a.split)
    if a.ids:
        ids = [i for i in ids if i in a.ids.split(",")]
    a.out.mkdir(parents=True, exist_ok=True)
    pre = preflight(a.claude_bin, a.expect_cli, a.out) if a.arm == "agent" else {"arm": "baseline"}
    (a.out / f"preflight_{a.arm}_{a.split}.json").write_text(json.dumps({**pre, "designs": ids, "k": a.k,
                                                                         "manifest_sha256": {i: man[i]["sha256"] for i in ids}}, indent=1))
    jobs = [(r, k) for r in ids for k in range(1, a.k + 1)]
    with ThreadPoolExecutor(max_workers=a.jobs if a.arm == "agent" else 1) as ex:
        for line in ex.map(lambda j: one(a.bench, j[0], a.arm, j[1], a.out, a.claude_bin, a.model, a.effort), jobs):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
