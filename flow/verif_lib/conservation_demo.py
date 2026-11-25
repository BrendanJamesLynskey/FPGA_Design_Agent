#!/usr/bin/env python3
"""Run the conservation demo (correct filter vs silent-drop mutant, three seeds) and record results/189_verification_rules/conservation.json.
Advisory (enforced: false). Needs Icarus Verilog."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "flow" / "tests" / "fixtures" / "conservation"
SRCS = [ROOT / "flow" / "verif_lib" / "fda_conservation.sv", FX / "cons_filter.sv", FX / "cons_tb.sv"]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as d:
        vvp = Path(d) / "t.vvp"
        subprocess.run(["iverilog", "-g2012", "-s", "cons_tb", "-o", str(vvp), *map(str, SRCS)], check=True)
        for mutant in (0, 1):
            for seed in (1, 2, 3):
                out = subprocess.run(["vvp", str(vvp), f"+MUTANT={mutant}", f"+SEED={seed}"], capture_output=True, text=True).stdout
                m = re.search(r"CONS_(PASS|FAIL) in=(\d+) out=(\d+) dropped=(\d+)(?: first_bad_in=(\d+))?", out)
                rows.append({"design": "cons_filter silent-drop mutant" if mutant else "cons_filter", "seed": seed, "verdict": m[1],
                             "frames_in": int(m[2]), "frames_out": int(m[3]), "counted_drops": int(m[4]),
                             "first_bad_frame_in": int(m[5]) if m[5] else None})
    rec = {"enforced": False, "simulator": "Icarus Verilog 12.0", "invariant": "frames in = frames out + counted drops + frames held",
           "rows": rows}
    out = ROOT / "results" / "189_verification_rules" / "conservation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1) + "\n")
    for r in rows:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
