#!/usr/bin/env python3
"""Which benchmark tasks a CI job runs (brief 07a2 fix 5, group G).

    python3 tools/ci_select.py v1|course|pool        # prints ALL, or task names separated by spaces
    python3 tools/ci_select.py v1|course|pool --k    # prints a pytest -k expression ("a or b"), empty for ALL

On a pull request the answer is the tasks the PR touches (files under that tier's task directory) plus the smoke set in
tools/ci_smoke.yaml. On a push to main, the nightly schedule or a manual run it is ALL, so main's coverage is the full
sweep. Environment: GITHUB_EVENT_NAME and PR_BASE_SHA (the base commit of the pull request, fetched by the workflow);
without a base commit the answer is ALL (never silently less than the full sweep).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TIER_DIRS = {"v1": "benchmark/tasks", "course": "benchmark/course/tasks", "pool": "benchmark/pool"}


def all_tasks(tier: str, root: Path = ROOT) -> list[str]:
    d = root / TIER_DIRS[tier]
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")) and p.name != "__pycache__")


def changed_files(base: str, root: Path = ROOT) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", base, "HEAD"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "git diff failed")
    return [l for l in out.stdout.splitlines() if l]


def select(tier: str, event: str, base: str | None, files: list[str] | None = None, root: Path = ROOT) -> list[str] | None:
    """None = every task; else the sorted list to run."""
    if event != "pull_request" or not base:
        return None
    existing = set(all_tasks(tier, root))
    smoke = yaml.safe_load((root / "tools" / "ci_smoke.yaml").read_text()).get(tier) or []
    unknown = [t for t in smoke if t not in existing]
    if unknown:
        raise SystemExit(f"tools/ci_smoke.yaml names {unknown}, which are not {tier} tasks")
    files = changed_files(base, root) if files is None else files
    prefix = TIER_DIRS[tier] + "/"
    touched = {f[len(prefix):].split("/")[0] for f in files if f.startswith(prefix)} & existing
    return sorted(set(smoke) | touched)


def main(argv: list[str]) -> int:
    k_mode = "--k" in argv
    argv = [a for a in argv if a != "--k"]
    if len(argv) != 1 or argv[0] not in TIER_DIRS:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        sel = select(argv[0], os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("PR_BASE_SHA"))
    except RuntimeError as e:                      # cannot tell what changed: run everything
        print(f"ci_select: {e}; running all", file=sys.stderr)
        sel = None
    if k_mode:
        print("" if sel is None else " or ".join(sel))
    else:
        print("ALL" if sel is None else " ".join(sel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
