#!/usr/bin/env python3
"""Course-tier entry for benchmark/tools/check_task.py (same arguments; adds ``no_shell`` support, see no_shell.py)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmark.course.tools import no_shell  # noqa: E402
from benchmark.tools import check_task  # noqa: E402

no_shell.apply()

if __name__ == "__main__":
    raise SystemExit(check_task.main())
