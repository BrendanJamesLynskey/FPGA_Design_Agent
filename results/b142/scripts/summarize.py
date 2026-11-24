#!/usr/bin/env python3
"""Collect the Yosys cell counts (yosys/<family>/<variant>/<name>.json) and the Vivado reports (vivado/<part>/<arm>/<name>/*.rpt) of brief 142
into summary.json and tables.md, primitive by primitive.

Canonical columns (the same for both tools): lut (LUT1..LUT6), lut6_2 (LUT6_2 cells), ff (FD*), carry4, carry8 (cells), carrybits (4 * CARRY4 + 8 * CARRY8),
f7 f8 f9 (MUXF7/8/9), dsp (DSP48*), bram18, bram36 (RAMB18*, RAMB36*), uram (URAM288*), srl (SRL16E + SRLC32E), lutram (RAM32*/RAM64*/RAM128*/RAM256*),
ctrl: flip-flop kinds (FDRE/FDSE/FDCE/FDPE) kept as the dict ``ffkinds``; everything else under ``other``.
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from manifest import BENCH  # noqa: E402


def canon(cells: dict) -> dict:
    c = lambda pat: sum(n for k, n in cells.items() if re.fullmatch(pat, k))
    out = dict(lut=c(r"LUT[1-6]"), lut6_2=c(r"LUT6_2"), ff=c(r"FD\w+|LDCE|LDPE"), carry4=c("CARRY4"), carry8=c("CARRY8"),
               f7=c("MUXF7"), f8=c("MUXF8"), f9=c("MUXF9"), dsp=c(r"DSP48\w*"), bram18=c(r"RAMB18\w*"), bram36=c(r"RAMB36\w*"),
               uram=c(r"URAM288\w*"), srl=c(r"SRL16E|SRLC32E|SRLC16E"), lutram=c(r"RAM(32|64|128|256|512)\w*|RAM\d+X\d\w*"))
    out["carrybits"] = 4 * out["carry4"] + 8 * out["carry8"]
    out["ffkinds"] = {k: n for k, n in cells.items() if re.fullmatch(r"FD[RSCP]E|LD\w+", k)}
    known = re.compile(r"LUT[1-6]|LUT6_2|FD\w+|LD\w+|CARRY[48]|MUXF[789]|DSP48\w*|RAMB(18|36)\w*|URAM288\w*|SRL16E|SRLC32E|SRLC16E|RAM(32|64|128|256|512)\w*|RAM\d+X\d\w*")
    out["other"] = {k: n for k, n in cells.items() if not known.fullmatch(k)}
    return out


def vivado_prims(text: str) -> dict:
    parts = re.split(r"\n\d+\. Primitives\n-+\n", text)
    sec = parts[-1] if len(parts) > 1 else ""
    sec = re.split(r"\n\d+\. Black Boxes", sec)[0]
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"^\|\s+(\w+)\s+\|\s+(\d+)\s+\|", sec, re.M)}


def vivado_levels(text: str):
    m = re.search(r"Logic Levels:\s+(\d+)", text)
    return int(m.group(1)) if m else None


def yosys_all():
    out = {}
    for p in sorted((HERE / "yosys").glob("*/*/*.json")):
        r = json.loads(p.read_text())
        if "cells" in r:
            out[(r["family"], r["variant"], r["name"])] = canon(r["cells"]) | {"seconds": r["seconds"]}
        else:
            out[(r["family"], r["variant"], r["name"])] = {"error": r.get("error", "?")[-200:]}
    return out


def vivado_all():
    out = {}
    for d in sorted((HERE / "vivado").glob("*/*/*")):
        if not d.is_dir():
            continue
        part, arm, name = d.parent.parent.name, d.parent.name, d.name
        rec = {}
        files = {"synth": ("utilization_synth.rpt", "timing_worst_synth.rpt"),     # synthesis-only job
                 "pre": ("utilization_impl.rpt", "timing_worst_impl.rpt"),         # impl job: after synth_design (rtl) or link_design (edif), before opt_design
                 "impl": ("utilization.rpt", "timing_worst.rpt")}                  # impl job: after route_design
        for stage, (uf, tf) in files.items():
            f = d / uf
            if f.exists():
                rec[stage] = canon(vivado_prims(f.read_text()))
                t = d / tf
                if t.exists():
                    txt = t.read_text()
                    rec[stage]["levels"] = vivado_levels(txt)
                    m = re.search(r"Slack \((MET|VIOLATED)\):\s+(-?[\d.]+)ns", txt)
                    rec[stage]["slack_ns"] = float(m.group(2)) if m else None
        if (d / "error.txt").exists():
            rec["error"] = (d / "error.txt").read_text()[-200:]
        out[(part, arm, name)] = rec
    return out


if __name__ == "__main__":
    y = yosys_all()
    v = vivado_all()
    json.dump({"yosys": {"|".join(k): x for k, x in y.items()}, "vivado": {"|".join(k): x for k, x in v.items()}}, open(HERE / "summary.json", "w"), indent=1)
    print(len(y), "yosys records,", len(v), "vivado records")
