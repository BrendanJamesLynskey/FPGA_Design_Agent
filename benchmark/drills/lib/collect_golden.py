#!/usr/bin/env python3
"""Copy what grade_constraints.py reads from a routed design into a golden folder (host paths and dates removed), so CI
grades it without Vivado.   python3 benchmark/drills/lib/collect_golden.py <design dir> <golden dir>"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BUILD = ("gates.json", "timing_summary.rpt", "utilization.rpt", "exceptions_route.rpt", "exceptions_ignored_route.rpt",
         "exceptions_coverage_route.rpt", "methodology.rpt", "mcp_paths_route.txt", "vivado.log")


def scrub(text: str) -> str:
    text = re.sub(r"^\| (Date|Host|Command)\s*:.*$", r"| \1 : (removed)", text, flags=re.M)
    return re.sub(r"/(tmp|home)/\S*?/(designs|runs)/", r"\2/", text)


def main(src: Path, dst: Path) -> None:
    shutil.rmtree(dst, ignore_errors=True)
    (dst / "build" / "base").mkdir(parents=True)
    shutil.copy(src / "design.xdc", dst / "design.xdc")
    for n in BUILD:
        f = src / "build" / "base" / n
        if f.exists():
            t = f.read_text(errors="replace")
            if n == "timing_summary.rpt":     # the summary tables only
                t = t.split("\n| Timing Details", 1)[0]
            if n == "vivado.log":             # only the constraint messages the gate reads
                t = "\n".join(l for l in t.splitlines() if re.match(r"(CRITICAL WARNING|ERROR): ", l)) + "\n"
            (dst / "build" / "base" / n).write_text(scrub(t))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
