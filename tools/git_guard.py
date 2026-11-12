"""A guard against tests that move the caller's checkout (brief fu-0112).

A long local run once left a worktree's HEAD detached at the same commit. ``repo_state`` reads the branch and the commit of the
checkout the tests run from; the root ``conftest.py`` records it before the first test and fails the session if it differs after
the last one. Nothing in this repository's tests or tools runs ``git checkout`` / ``switch`` / ``reset`` in the caller's tree
(the agent's snapshots use their own bare repository, ``<run>/snap.git``); this keeps it that way.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def repo_state(root: Path = ROOT) -> dict[str, str | None] | None:
    """``{"branch": name or None when detached, "head": full commit}``; None when ``root`` is not a git checkout."""
    head = _git(root, "rev-parse", "HEAD")
    if head is None:
        return None
    return {"branch": _git(root, "symbolic-ref", "-q", "--short", "HEAD"), "head": head}


def describe_change(before: dict | None, after: dict | None) -> str | None:
    """None when the checkout is as it was; else one line saying what moved."""
    if before is None or after is None or before == after:
        return None
    parts = []
    if before["branch"] != after["branch"]:
        parts.append(f"branch {before['branch'] or '(detached)'} -> {after['branch'] or '(detached)'}")
    if before["head"] != after["head"]:
        parts.append(f"HEAD {before['head'][:12]} -> {after['head'][:12]}")
    return "the tests changed the checkout they ran from: " + "; ".join(parts)
