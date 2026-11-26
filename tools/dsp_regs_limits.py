#!/usr/bin/env python3
"""Regenerate flow/dsp_regs_limits.json (brief 185) from the committed DSP-slice measurements; nothing is typed.

    python3 tools/dsp_regs_limits.py [--check]

For each family (7series = DSP48E1 on xc7a100tcsg324-1, ultrascale_plus = DSP48E2 on xck26-sfvc784-2LV-c) and the 18-bit multiply points of
results/185_dsp_slices/data/<part>.json (one run each):
  period_needs_mreg_below_ns   the best (shortest) period reached by any point whose slice has MREG = 0;
  period_needs_preg_below_ns   the best period reached by any point whose slice has MREG = 1 and PREG = 0;
  slice_min_period_ns          the 'Min Period' a DSP pin requires in the timing summary of the fully registered point (the slice's own limit).
A target period below the first number cannot be met with MREG = 0 in the cases measured, and so on. They are best cases of a few runs, not guarantees.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results" / "185_dsp_slices" / "data"
OUT = ROOT / "flow" / "dsp_regs_limits.json"
FAM = {"a7": ("7series", "DSP48E1"), "k26": ("ultrascale_plus", "DSP48E2")}


def build() -> dict:
    fams = {}
    for pk, (fam, cell) in FAM.items():
        d = json.loads((DATA / f"{pk}.json").read_text())
        pts = [p for p in d["points"] if p["kind"] == "mul" and p["params"]["WA"] == 18 and p.get("status") == "ok" and p.get("dsp_cells")]
        def best(cond):
            f = [p["fmax_mhz"] for p in pts if cond(p["dsp_cells"][0])]
            return round(1000.0 / max(f), 2)
        # the slice's own limit: the DSP pin rows of the Min Period checks of the fully registered point (operands, multiplier, output)
        full = next(p for p in pts if p["params"]["NA"] == 1 and p["params"]["NM"] == 1 and p["params"]["NP"] == 1 and p["params"]["RSTP"] == 0 and p["params"]["WB"] == 18 and p["params"]["WA"] == 18)
        raw = ROOT / "results" / "185_dsp_slices" / "raw" / pk / full["id"] / "pulse_width_checks.txt"
        slice_min = max(float(m.group(1)) for m in re.finditer(r"^Min Period\s+\S+\s+DSP\w*/CLK\s+\S+\s+([\d.]+)", raw.read_text(), re.M))
        fams[fam] = {"part": d["part"], "tool": d["tool"], "slice": cell,
                     "period_needs_mreg_below_ns": best(lambda c: c.get("MREG") == 0),
                     "period_needs_preg_below_ns": best(lambda c: c.get("MREG") == 1 and c.get("PREG") == 0),
                     "slice_min_period_ns": slice_min}
    return {"schema": "fda-185/dsp_regs_limits/1", "source": "results/185_dsp_slices/data/{a7,k26}.json", "families": fams}


if __name__ == "__main__":
    new = json.dumps(build(), indent=1) + "\n"
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text() == new else 1)
    OUT.write_text(new)
    print(new)
