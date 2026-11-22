#!/usr/bin/env python3
"""Collect the per-case results of the MIN_KEEP 1 to 3 bench of rate_match_gp (brief 168) from the cocotb simulation logs into cases.json.

    FDA_SIM_BUILD_ROOT=<dir> python3 -m pytest -q designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py -k min_keep --junitxml results/168_rm_minkeep/pytest_junit.xml
    python3 results/168_rm_minkeep/collect_cases.py <dir>/b96_rate_match_gp_k{1,2,3}/sim.log

Every case logs one `RM {json}` line: the RTL's counters, the Python twin's counters (they must be equal, and the bench asserts it), the number of frames offered and received, and whether the received
frames equal the offered ones. This script copies those lines, unchanged, into one file per MIN_KEEP; it computes nothing."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> int:
    out: dict[str, list] = {}
    for p in sys.argv[1:]:
        log = Path(p).read_text(errors="ignore")
        k = re.search(r"_k(\d)", str(p)).group(1)
        out[f"MIN_KEEP={k}"] = [json.loads(m.group(1)) for m in re.finditer(r"RM (\{.*?\})\n", log)]
    Path(__file__).with_name("cases.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, rows in out.items():
        for r in rows:
            t = r["rtl"]
            print(k, r["name"], "ppm", r["ppm"], "frames", r["frames_in"], "->", r["frames_out"], "equal", r["frames_equal"], "n_ovf", t["n_ovf"], "n_del", t["n_del"], "n_ins", t["n_ins"], "n_stall", t["n_stall"], "twin_equal", r["rtl"] == r["twin"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
