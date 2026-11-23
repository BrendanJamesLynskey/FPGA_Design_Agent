#!/usr/bin/env python3
"""Brief 189 item 8: catch rate of the per-bit skew injection on a torn-pointer mutant (binary-pointer async FIFO) and on its
Gray-pointer reference. Writes results/189_verification_rules/cdc_skew.{json,md}. Advisory (enforced: false). Idea from Edwards 2026, ch 12.
    python3 -m flow.cdc_skew_table [--seeds 8]"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "flow" / "tests"))
OUT = ROOT / "results" / "189_verification_rules"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    a = ap.parse_args()
    import test_189_cdc_skew as T
    rows = []
    with tempfile.TemporaryDirectory() as d:
        for name in ("cdcfx_m12", "cdcfx_c10"):
            for skew in (None, 2, 4):
                fails = [s for s in range(1, a.seeds + 1) if not T._run(name, s, skew, Path(d))]
                rows.append({"fixture": name, "skew": skew or 1, "seeds": a.seeds, "failing_seeds": fails})
            rows.append({"fixture": name, "skew": 0, "seeds": 1, "failing_seeds": [] if T._run(name, 0, None, Path(d)) else [0]})
    rec = {"enforced": False, "tool": "Icarus Verilog 12.0 via cocotb 2.0.1", "rows": rows,
           "meaning": "skew 0 = no injection; 1 = the earlier model (a bit held at most one cycle); k = a bit held up to k cycles in a row"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cdc_skew.json").write_text(json.dumps(rec, indent=1) + "\n")
    lines = ["# Per-bit skew injection on a torn-pointer FIFO (brief 189 item 8)", "", "Advisory. Icarus 12.0, cocotb 2.0.1, fixtures in `flow/tests/fixtures/cdc_pointer` and `cdc_mutants`.", "",
             "| fixture | skew (max cycles a bit is held) | seeds run | seeds whose own test failed |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['fixture']} | {r['skew'] if r['skew'] else 'none (plain)'} | {r['seeds']} | {len(r['failing_seeds'])} {r['failing_seeds'] or ''} |")
    (OUT / "cdc_skew.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
