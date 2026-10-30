#!/usr/bin/env python3
"""Cut the gates-test snippets (flow/tests/data/) from real Vivado report files.

    python3 flow/tests/cut_snippets.py <build dir> <prefix>      # prefix: good | bad

Keeps each report's tool-version header (dropping the Date, Host and Command
lines, which name the build machine; absolute paths become repo-relative) and the sections the gates
parse; long per-violation detail sections are cut to their first entries.
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).parent / "data"
ROOT = Path(__file__).resolve().parents[2]
KEEP_DETAIL_LINES = {"drc": 12, "methodology": 12, "check_timing": 40, "cdc": 60}


def clean(text: str) -> list[str]:
    text = text.replace(str(ROOT) + "/", "")          # repo-relative paths only
    return [ln for ln in text.splitlines() if not ln.startswith(("| Date ", "| Host ", "| Command "))]


def cut(name: str, lines: list[str]) -> list[str]:
    if name in ("drc", "methodology"):
        i = next(k for k, ln in enumerate(lines) if ln.strip() == "2. REPORT DETAILS" and k > 20)
        return lines[: i + 2 + KEEP_DETAIL_LINES[name]]
    if name in ("check_timing", "cdc"):
        return lines[: KEEP_DETAIL_LINES[name]]
    if name == "timing_summary":
        i = next(k for k, ln in enumerate(lines) if "Design Timing Summary" in ln and ln.startswith("|"))
        head = lines[:12]
        return head + ["..."] + lines[i - 1: i + 10]
    return lines   # utilization, power: whole


def main() -> int:
    build, prefix = Path(sys.argv[1]), sys.argv[2]
    for name in ("timing_summary", "check_timing", "utilization", "drc", "methodology", "cdc", "power"):
        lines = cut(name, clean((build / f"{name}.rpt").read_text()))
        (OUT / f"{prefix}_{name}.rpt").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
