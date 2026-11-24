#!/usr/bin/env python3
"""Brief 208: collect the measured facts of every recorded run into measured.json (the README tables and the site's
expertise evidence read this file; every number comes from a report under runs/).

    python3 results/208/summarise.py            # writes results/208/measured.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from flow.constraint_gates import parse_clock_pairs   # noqa: E402
from flow.gates import parse_rule_table              # noqa: E402


def _read(p: Path) -> str:
    return p.read_text(errors="replace") if p.is_file() else ""


def timing_summary(text: str) -> dict:
    m = re.search(r"^\s+WNS\(ns\)\s+TNS\(ns\).*\n\s+-+.*\n\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\d+)", text, re.M)
    if not m:
        return {}
    return {"wns": float(m.group(1)), "tns": float(m.group(2)), "setup_failing": int(m.group(3)), "setup_total": int(m.group(4)),
            "whs": float(m.group(5)), "hold_failing": int(m.group(7))}


def cdc(text: str) -> dict:
    rows = re.findall(r"^(CDC-\d+)\s+(\w+)\s+(\d+)\s+", text, re.M)
    pairs = re.findall(r"^Source Clock: (\S+)\nDestination Clock: (\S+)", text, re.M)
    return {"rules": {r: int(n) for r, _s, n in rows}, "crossings": [f"{a} -> {b}" for a, b in pairs]}


def arm(d: Path) -> dict:
    out: dict = {"name": d.name}
    err = d / "JOBERROR.txt"
    if err.is_file():
        out["error"] = _read(err).strip()
    for st in ("synth", "route"):
        ci = d / f"clock_interaction_{st}.rpt"
        if not ci.is_file():
            continue
        s: dict = {}
        s["interaction"] = [{"from": p["from"], "to": p["to"], "constraints": p["constraints"], "endpoints": p["endpoints"]}
                            for p in parse_clock_pairs(_read(ci))]
        # WNS and failing endpoints per pair (the fixed-width table: columns 4 and 6)
        for row, line in zip(s["interaction"], [ln for ln in _read(ci).splitlines()
                                                if re.match(r"^[^-\s]\S*\s+\S+\s+(rise|fall|-)", ln)]):
            f = line.split()
            row["wns"] = float(f[5]) if re.match(r"^-?\d", f[5]) and "Timed" in row["constraints"] else None
            row["setup_failing"] = int(f[7]) if row["wns"] is not None else None
        ct = _read(d / f"check_timing_{st}.rpt")
        m = re.search(r"checking multiple_clock \((\d+)\)", ct)
        s["multiple_clock"] = int(m.group(1)) if m else None
        try:
            s["methodology"] = {r["rule"]: {"severity": r["severity"], "count": r["count"]}
                                for r in parse_rule_table(_read(d / f"methodology_{st}.rpt"))}
        except ValueError:
            s["methodology"] = None
        s["timing"] = timing_summary(_read(d / f"timing_summary_{st}.rpt"))
        s["cdc"] = cdc(_read(d / f"cdc_{st}.rpt"))
        dump = _read(d / f"clock_mux_dump_{st}.txt")
        s["mux_out_clocks"] = [ln.split("\t")[2] for ln in dump.splitlines() if ln.startswith("MUXOUT")]
        s["lut_on_clock"] = [ln.split("\t")[2] for ln in dump.splitlines() if ln.startswith("LUTCLK")]
        out[st] = s
    pw = {}
    for p in sorted(d.glob("power_en*.rpt")):
        t = _read(p)
        g = lambda k: float(re.search(r"^\| " + re.escape(k) + r"\s*\|\s*([0-9.]+)", t, re.M).group(1))  # noqa: E731
        pw[p.stem.replace("power_en", "")] = {"total_w": float(re.search(r"Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)", t).group(1)),
                                              "dynamic_w": g("Dynamic (W)"), "clocks_w": g("Clocks"), "signals_w": g("Signals")}
    if pw:
        out["power_by_enable_probability"] = pw
    return out


def main() -> int:
    res: dict = {"vivado": {}, "sim": {}, "analyse": [], "quartus": {}}
    for part in sorted((HERE / "runs").glob("*")):
        if part.name in ("sim", "gotchas", "quartus", "analyse"):
            continue
        for d in sorted(part.iterdir()):
            if d.is_dir():
                res["vivado"][d.name] = arm(d)
    for log in sorted((HERE / "runs" / "sim").glob("*.log")):
        for ln in _read(log).splitlines():
            if ln.startswith("SCEN "):
                f = ln.split()
                res["sim"][f[1]] = " ".join(f[2:])
    a = HERE / "runs" / "analyse" / "analyse.tsv"
    for ln in _read(a).splitlines():
        res["analyse"].append(ln.split("\t"))
    for d in sorted((HERE / "runs" / "quartus").glob("*")):
        if d.is_dir():
            q = {}
            fs = _read(d / "fit_summary.txt")
            for k in ("Total logic elements", "Logic utilization (in ALMs)", "Total registers", "Global clocks", "Clock control block"):
                m = re.search(re.escape(k) + r"\s*:\s*(.+)", fs)
                if m:
                    q[k] = m.group(1).strip()
            q["messages"] = _read(d / "messages.txt").splitlines()
            q["clock_transfers"] = _read(d / "sta_clock_transfers.rpt").count("\n")
            res["quartus"][d.name] = q
    (HERE / "measured.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print("wrote", HERE / "measured.json", len(res["vivado"]), "Vivado arms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
