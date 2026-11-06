#!/usr/bin/env python3
"""The knowledge bank must not contain any course-tier spec's distinctive phrases (brief 07a1; benchmark/tools/bank_grep.py applied to the course tier).

    bank_grep.py [--bank DIR] [--json OUT]

Checks the public course tasks and, when the private repository is next to this one, the held-out course tasks too.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmark.tools import bank_grep  # noqa: E402

PRIVATE = ROOT.parent / "FPGA_Design_Agent_Knowledge" / "benchmark_private" / "course" / "tasks"

if __name__ == "__main__":
    roots = [str(ROOT / "benchmark" / "course" / "tasks")] + ([str(PRIVATE)] if PRIVATE.exists() else [])
    sys.argv = [sys.argv[0], *roots, *sys.argv[1:]]
    raise SystemExit(bank_grep.main())
