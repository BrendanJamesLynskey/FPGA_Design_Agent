#!/usr/bin/env python3
"""summarise_build.py: extract the numbers of one rig build into hil/cdc_soak/results/ (committed).

    python3 hil/cdc_soak/host/summarise_build.py hil/cdc_soak/build/full

Writes results/build_<name>.json (utilisation, power, timing, report_cdc and report_methodology summaries, bus skew,
run time and memory) and copies the per-copy delay table (delays_copies.csv) and the report_cdc summary text next to
it. Reads only the build's report files; never starts Vivado.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

RIG = Path(__file__).resolve().parents[1]


def util(rpt: str) -> dict:
    out = {}
    for name, key in (("Slice LUTs", "lut"), ("Slice Registers", "ff"), ("LUT as Memory", "lutram"),
                      ("Block RAM Tile", "bram36"), ("BUFGCTRL", "bufg"), ("MMCME2_ADV", "mmcm")):
        m = re.search(r"^\|\s*" + re.escape(name) + r"\*?\s*\|\s*([\d.]+)\s*\|.*?\|\s*(\d+)\s*\|\s*([\d.<]+)\s*\|$", rpt, re.M)
        if m:
            out[key] = {"used": float(m.group(1)), "available": int(m.group(2)), "pct": m.group(3)}
    return out


def power(rpt: str) -> dict:
    out = {}
    for name, key in (("Total On-Chip Power (W)", "total_w"), ("Dynamic (W)", "dynamic_w"),
                      ("Device Static (W)", "static_w"), ("Junction Temperature (C)", "tj_c"),
                      ("Effective TJA (C/W)", "theta_ja_c_per_w"), ("Max Ambient (C)", "max_ambient_c")):
        m = re.search(r"\|\s*" + re.escape(name) + r"\s*\|\s*([\d.]+)", rpt)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"\|\s*Confidence Level\s*\|\s*(\w+)", rpt)
    if m:
        out["confidence"] = m.group(1)
    return out


def timing(rpt: str) -> dict:
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)",
                  rpt, re.S)
    if not m:
        return {}
    g = m.groups()
    return {"wns_ns": float(g[0]), "tns_ns": float(g[1]), "setup_failing": int(g[2]), "setup_endpoints": int(g[3]),
            "whs_ns": float(g[4]), "ths_ns": float(g[5]), "hold_failing": int(g[6]), "hold_endpoints": int(g[7]),
            "wpws_ns": float(g[8]), "met": "All user specified timing constraints are met" in rpt}


def cdc(rpt: str) -> dict:
    ids = {}
    m = re.search(r"ID\s+Severity\s+Count\s+Description\n-+.*?\n(.*?)\n\n", rpt, re.S)
    if m:
        for ln in m.group(1).splitlines():
            p = ln.split(None, 3)
            if len(p) == 4:
                ids[p[0]] = {"severity": p[1], "count": int(p[2]), "description": p[3].strip()}
    waived = {}
    m = re.search(r"ID\s+Waived Endpoints\s*\n-+.*?\n(.*?)\n(?:Note|\n)", rpt, re.S)
    if m:
        for ln in m.group(1).splitlines():
            p = ln.split()
            if len(p) == 2 and p[1].isdigit():
                waived[p[0]] = int(p[1])
    rows = []
    for ln in rpt.splitlines():
        mm = re.match(r"^(Critical|Warning|Info)\s+(\S+)\s+(\S+)\s+(.*?)\s{2,}(.*?)\s{2,}(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", ln)
        if mm:
            g = mm.groups()
            rows.append({"severity": g[0], "from": g[1], "to": g[2], "type": g[3], "exceptions": g[4],
                         "endpoints": int(g[5]), "safe": int(g[6]), "unsafe": int(g[7]), "unknown": int(g[8]),
                         "no_async_reg": int(g[9])})
    return {"ids": ids, "waived_endpoints": waived, "clock_pairs": rows}


def methodology(rpt: str) -> dict:
    out = {}
    parts = rpt.split("2. REPORT DETAILS")          # the first one is the table of contents
    for ln in (parts[1] if len(parts) > 2 else parts[0]).splitlines():
        p = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(p) == 4 and p[3].isdigit():
            out[p[0]] = {"severity": p[1], "description": p[2], "checks": int(p[3])}
    return out


def bus_skew(rpt: str) -> dict:
    rows = re.findall(r"^\s+(Slow|Fast)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d.]+)\s*$", rpt, re.M)
    slacks = [float(r[3]) for r in rows]
    actual = [float(r[2]) for r in rows]
    return {"constraints": len(rows), "worst_slack_ns": min(slacks) if slacks else None,
            "largest_skew_ns": max(actual) if actual else None, "met": bool(rows) and min(slacks) >= 0}


def cdc_by_variant(details: str, copies_csv: str) -> dict:
    """Which report_cdc IDs (waived or not) hit each variant, from a -details report and the copy map."""
    var = {}
    for ln in copies_csv.splitlines()[1:]:
        p = ln.split(",")
        if len(p) > 1 and p[0].isdigit():
            var[int(p[0])] = p[1]
    out: dict[str, dict[str, int]] = {}
    for ln in details.splitlines():
        m = re.match(r"\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+.*?g_copy\[(\d+)\]\S*\s+(Yes|No|Y|N)?\s*$", ln)
        if m and int(m.group(3)) in var:
            key = f"{m.group(1)} {m.group(2)}" + (" (waived)" if m.group(4) in ("Yes", "Y") else "")
            d = out.setdefault(var[int(m.group(3))], {})
            d[key] = d.get(key, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    bdir = Path(sys.argv[1]).resolve()
    name = bdir.name
    rd = lambda f: (bdir / f).read_text(errors="replace") if (bdir / f).exists() else ""  # noqa: E731
    stages = {}
    for ln in rd("stages.txt").splitlines():
        p = ln.split()
        if len(p) == 2:
            stages[p[0]] = float(p[1])
    peak = re.search(r"Maximum resident set size \(kbytes\): (\d+)", rd("time.txt"))
    out = {"build": name, "utilisation": util(rd("util.rpt")), "power": power(rd("power.rpt")),
           "timing": timing(rd("timing_summary.rpt")), "report_cdc": cdc(rd("cdc_summary.rpt")),
           "report_cdc_without_waivers": cdc(rd("cdc_summary_nowaiver.rpt")),
           "report_methodology": methodology(rd("methodology.rpt")),
           "report_methodology_without_waivers": methodology(rd("methodology_nowaiver.rpt")),
           "bus_skew": bus_skew(rd("bus_skew.rpt")), "stages_s": stages,
           "cdc_ids_by_variant": cdc_by_variant(rd("cdc_details.rpt"), rd("delays_copies.csv")),
           "vivado_peak_rss_mb": round(int(peak.group(1)) / 1024) if peak else None}
    res = RIG / "results"
    res.mkdir(exist_ok=True)
    (res / f"build_{name}.json").write_text(json.dumps(out, indent=1) + "\n")
    for f, dst in (("delays_copies.csv", f"delays_copies_{name}.csv"), ("delays_paths.csv", f"delays_paths_{name}.csv"),
                   ("cdc_summary.rpt", f"cdc_summary_{name}.rpt")):
        # the per-path table of the full build is large; it stays in the build directory
        if (bdir / f).exists() and (bdir / f).stat().st_size < 1_500_000:
            shutil.copyfile(bdir / f, res / dst)
    print(json.dumps({k: out[k] for k in ("utilisation", "power", "timing")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
