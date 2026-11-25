#!/usr/bin/env python3
"""Brief 206: build records/summary.json and the README tables from the committed records only.

    python3 results/206_power_up/summary.py           # write records/summary.json and print the Markdown tables
    python3 results/206_power_up/summary.py --check   # exit 1 if records/summary.json differs from what the records give

Rows of ``amd`` carry ``batch`` (main, b, scan): arms repeated across batches appear once per batch, so do not sum over them.
AMD: records/amd_<part>.tsv (arms.tcl), records/amd_<part>_b.tsv (arms_b.tcl), records/amd_<part>_scan.tsv (arms_scan.tcl).
Altera: records/altera/<case>.json (altera/parse_quartus.py on each compiled case).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "records"
PARTS = ("xc7a35tcpg236-1", "xck26-sfvc784-2LV-c")


def amd_rows() -> list[dict]:
    rows = []
    for part in PARTS:
        for suffix in ("", "_b", "_scan"):
            f = REC / f"amd_{part}{suffix}.tsv"
            if not f.is_file():
                continue
            d: dict = defaultdict(dict)
            for p, arm, initv, key, val in csv.reader(f.open(), delimiter="\t"):
                d[(arm, initv)][key] = val
            for (arm, initv), kv in d.items():
                if arm.endswith("_place"):
                    continue
                ff = {k[3:]: int(v) for k, v in kv.items() if k.startswith("ff.")}
                cells = {k[6:]: int(v) for k, v in kv.items() if k.startswith("cells.")}
                lut = sum(v for k, v in cells.items() if re.fullmatch(r"LUT\d", k))
                dsp = {k.rsplit(".", 1)[1]: v for k, v in kv.items() if k.startswith("dsp.") and k.count(".") == 2 and v != ""}
                bram = {k.rsplit(".", 1)[1]: v for k, v in kv.items() if re.match(r"bram\.mem_reg(_bram_0)?\.\w+$", k)}
                rows.append({"part": part, "batch": suffix.strip("_") or "main", "arm": arm, "initv": int(initv),
                             "ff_total": sum(ff.values()), "ff_by_type_init": ff, "lut": lut,
                             "lut1_inverters": int(kv.get("lut1_inverters", 0)),
                             "dsp": cells.get("DSP48E1", 0) + cells.get("DSP48E2", 0),
                             "dsp_regs": {k: int(v) for k, v in dsp.items() if k in ("AREG", "BREG", "MREG", "PREG")},
                             "bram36": cells.get("RAMB36E1", 0) + cells.get("RAMB36E2", 0), "uram": cells.get("URAM288", 0),
                             "bram_first": {k: v for k, v in bram.items() if k in ("INIT_A", "INIT_B", "DOA_REG", "DOB_REG")},
                             "init_scan_rows": int(kv["init_scan_rows"]) if "init_scan_rows" in kv else None,
                             "synth_error": kv.get("synth_error")})
    return rows


def amd_placed() -> list[dict]:
    out = []
    for part in PARTS:
        f = REC / f"amd_{part}.tsv"
        if not f.is_file():
            continue
        agg: dict = defaultdict(int)
        for p, arm, initv, key, val in csv.reader(f.open(), delimiter="\t"):
            if arm.endswith("_place") and key.startswith("placed."):
                m = re.match(r"(\S+) INIT=(\S+) IOB=\S+ site_type=(\S+)", val)
                agg[(arm[:-6], int(initv), m.group(1), m.group(2), m.group(3))] += 1
        out += [{"part": part, "arm": a, "initv": i, "ref": r, "init": n, "site_type": s, "count": c}
                for (a, i, r, n, s), c in sorted(agg.items())]
    return out


def altera_rows() -> list[dict]:
    out = []
    for f in sorted((REC / "altera").glob("q_*.json")):
        r = json.loads(f.read_text())
        m = re.match(r"q_(\w+?)_i(\d)_pb(ON|OFF)", r["case"])
        fam, initv, pb = m.group(1), int(m.group(2)), m.group(3)
        for arm, ent in r["fit_entity"].items():
            if arm == "total":
                continue
            def num(k: str):
                v = str(ent.get(k, "")).split()
                if not v:
                    return None
                try:
                    x = float(v[0])
                except ValueError:
                    return None
                return int(x) if x.is_integer() else x
            row = {"family": fam, "initv": initv, "pushback": pb, "arm": arm,
                   "logic": num("Logic Cells") if "Logic Cells" in ent else num("ALMs needed [=A-B+C]"),
                   "logic_unit": "LE" if "Logic Cells" in ent else "ALM",
                   "luts": num("LUT-Only LCs") if "LUT-Only LCs" in ent else num("Combinational ALUTs"),
                   "regs": num("Dedicated Logic Registers"), "io_regs": num("I/O Registers"),
                   "mem_bits": num("Block Memory Bits") if "Block Memory Bits" in ent else num("Memory Bits"),
                   "dsp": num("DSP Elements") if "DSP Elements" in ent else num("DSP Blocks"),
                   "fmax_mhz": r["fmax_mhz"].get(arm),
                   "netlist_power_up": r.get("netlist_power_up", {}).get(arm)}
            out.append(row)
    return out


def altera_messages() -> list[dict]:
    out = []
    for f in sorted((REC / "altera").glob("q_*.json")):
        r = json.loads(f.read_text())
        ids: dict = defaultdict(int)
        for m in r["messages"]:
            ids[(m["severity"], m["id"], re.sub(r"\[\d+\]", "[n]", m["text"]))] += 1
        out += [{"case": r["case"], "severity": s, "id": i, "text": t, "count": c} for (s, i, t), c in sorted(ids.items())]
        out += [{"case": r["case"], "io_pins": r.get("io_pins", {})}]
    return out


def build() -> dict:
    return {"amd": amd_rows(), "amd_iob": amd_placed(), "altera": altera_rows(), "altera_messages": altera_messages()}


if __name__ == "__main__":
    s = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    out = REC / "summary.json"
    if "--check" in sys.argv:
        sys.exit(0 if out.is_file() and out.read_text() == s else 1)
    out.write_text(s)
    print(f"wrote {out}")
