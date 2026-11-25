#!/usr/bin/env python3
"""Advisory DSP-slice register check (brief 185, enforced: false).

    python3 flow/dsp_regs_check.py <dsp_cells.txt> --period-ns 2.0 [--part-family 7series|ultrascale_plus] [--drc drc.rpt]

Reads the DSP cells' register properties (one line per cell, `<cell> <REF_NAME> AREG=1 MREG=1 PREG=0 ...`, written by flow/dsp_cells.tcl after
synthesis or routing; the same format as results/185_dsp_slices/raw/*/*/dsp_cells.txt) and the target clock period, and flags:
  DSPREG-01  a slice that multiplies with no multiplier register (MREG = 0) when the period is below the measured limit for such a slice;
  DSPREG-02  a slice with no output register (PREG = 0) when the period is below the measured limit for that;
  DSPREG-03  the slice's own minimum clock period (data sheet, measured as the 'Min Period' check) is above the target period, whatever its registers;
  DSPREG-04  Vivado's own DRC rows DPIP-1 / DPOP-1 / DPOP-2 (unregistered DSP input or output) when a drc report is given.
The limits are measured, not from memory: flow/dsp_regs_limits.json (source: results/185_dsp_slices/data/*.json). Advisory: it never fails a run;
a slice that is meant to be slow (a low-rate datapath) may waive it with a reason.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMITS = HERE / "dsp_regs_limits.json"
FAMILY = {"DSP48E1": "7series", "DSP48E2": "ultrascale_plus"}


def parse_cells(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        t = line.split()
        if len(t) < 2:
            continue
        d: dict = {"cell": t[0], "type": t[1]}
        for kv in t[2:]:
            k, _, v = kv.partition("=")
            d[k] = int(v) if v.isdigit() else v
        out.append(d)
    return out


def drc_rows(text: str) -> list[tuple[str, str, int]]:
    return [(m.group(1), m.group(2).strip(), int(m.group(3))) for m in re.finditer(r"^\|\s*(DP(?:IP|OP)-\d+)\s*\|\s*\w[\w ]*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", text, re.M)]


def check(cells: list[dict], period_ns: float, drc: str | None = None, limits: dict | None = None) -> list[dict]:
    lim = limits if limits is not None else json.loads(LIMITS.read_text())
    fs: list[dict] = []
    for c in cells:
        fam = FAMILY.get(c["type"])
        if fam is None or fam not in lim["families"]:
            continue
        L = lim["families"][fam]
        mult = str(c.get("USE_MULT", "MULTIPLY")) != "NONE"
        if mult and c.get("MREG") == 0 and period_ns < L["period_needs_mreg_below_ns"]:
            fs.append({"code": "DSPREG-01", "where": c["cell"], "severity": "advisory",
                       "message": f"{c['type']} multiplies with no multiplier register (MREG=0); measured, such a slice cannot meet {period_ns} ns "
                                  f"(best case {L['period_needs_mreg_below_ns']} ns): add the register after the multiply"})
        elif c.get("PREG") == 0 and period_ns < L["period_needs_preg_below_ns"]:
            fs.append({"code": "DSPREG-02", "where": c["cell"], "severity": "advisory",
                       "message": f"{c['type']} has no output register (PREG=0); measured, it cannot meet {period_ns} ns "
                                  f"(best case {L['period_needs_preg_below_ns']} ns): add the output register"})
        if period_ns < L["slice_min_period_ns"]:
            fs.append({"code": "DSPREG-03", "where": c["cell"], "severity": "advisory",
                       "message": f"the {c['type']} slice's own minimum clock period is {L['slice_min_period_ns']} ns; the target {period_ns} ns is faster"})
    if drc:
        for rule, what, n in drc_rows(drc):
            fs.append({"code": "DSPREG-04", "where": rule, "severity": "advisory", "message": f"Vivado {rule} ({what}) x{n}: a DSP input or output is not registered"})
    return fs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cells")
    ap.add_argument("--period-ns", type=float, required=True)
    ap.add_argument("--drc", default="")
    a = ap.parse_args()
    fs = check(parse_cells(Path(a.cells).read_text()), a.period_ns, Path(a.drc).read_text() if a.drc else None)
    for f in fs:
        print(f"{f['code']} {f['where']}: {f['message']}")
    print(f"{len(fs)} advisory finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
