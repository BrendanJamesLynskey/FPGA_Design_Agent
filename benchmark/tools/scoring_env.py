#!/usr/bin/env python3
"""Scoring-environment check (brief 07a2 fix 5, group F).

    python3 benchmark/tools/scoring_env.py <task_dir> [<task_dir> ...]     # exit 3 and a clear message if a module is missing

A task's hidden bench and model import third-party modules (the c15 softmax model imports numpy). In an interpreter without
them the cocotb run dies at import and ``run_task.py`` reports 0/0 tests, which reads like an RTL failure (batch 1, c15).
Run this first, or call ``missing_modules`` / ``check`` from a scorer. ``run_task.py`` itself is part of the frozen
scoring tools, so the check lives here, outside the manifests.
"""

from __future__ import annotations

import sys
from pathlib import Path


def missing_modules(task: Path) -> list[str]:
    """07a2 fix 5 F: third-party modules the task's hidden Python files import that this interpreter lacks (batch 1: the
    c15 model imports numpy, the scoring venv had none, and the run was scored 0/0 with no word why). Standard-library,
    repo-local and hidden/-local modules are not checked."""
    import ast
    import importlib.util

    hidden = task / "hidden"
    local = {p.stem for p in hidden.glob("*.py")} | {"benchmark", "flow", "shell", "agent", "cocotb", "cocotb_tools",
                                                   "cocotb_coverage"}
    need: set[str] = set()
    for f in sorted(hidden.glob("*.py")):
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                need |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                need.add(n.module.split(".")[0])
    return sorted(m for m in need - local - set(sys.stdlib_module_names) if importlib.util.find_spec(m) is None)


def check(task: Path) -> str | None:
    """None when the task's hidden imports are all importable here, else the environment error to show."""
    miss = missing_modules(task)
    if not miss:
        return None
    return (f"environment: {task.name}: the hidden bench imports {', '.join(miss)}, which this Python lacks "
            f"({sys.executable}); install it there (pip install {' '.join(miss)}). Not an RTL failure: no test ran.")


def main(argv: list[str]) -> int:
    bad = [e for e in (check(Path(a)) for a in argv) if e]
    for e in bad:
        print(e, file=sys.stderr)
    return 3 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
