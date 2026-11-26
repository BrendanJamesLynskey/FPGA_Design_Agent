#!/usr/bin/env python3
"""OOC Vivado comparison of hand-written SV and Hardcaml-generated Verilog (brief 171). Run it under a heavy slot, in a memory-capped
user scope (see docs/hardcaml_scoping.md). Needs both blocks generated first (ip_lib/<block>/hardcaml/run_hc.sh gen).

    python3 tools/hardcaml/ooc_compare.py run  [--parts a7,k26]     # writes build/hc_ooc/<job>/ and results/b171/ooc_compare.json
    python3 tools/hardcaml/ooc_compare.py parse                       # rebuild the JSON from the reports

Fmax is 1000 / (clock_ns - WNS), the flow's own estimate (flow/ipchar.py); a positive-slack run therefore gives an Fmax above its clock."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "hc_ooc"
PARTS = {"a7": ("xc7a100tcsg324-1", 3.0), "k26": ("xck26-sfvc784-2LV-c", 2.0)}
# (block, label, generics)
POINTS = [
    ("pipe_reg", "skid_w64_n2_tlast_tkeep", {"W": 64, "N": 2, "MODE": 1, "TLAST_EN": 1, "TKEEP_EN": 1, "TUSER_W": 0}),
    ("pipe_reg", "full_w64_n2", {"W": 64, "N": 2, "MODE": 2, "TLAST_EN": 0, "TKEEP_EN": 0, "TUSER_W": 0}),
    ("pipe_reg", "comb_w16_n5", {"W": 16, "N": 5, "MODE": 4, "TLAST_EN": 0, "TKEEP_EN": 0, "TUSER_W": 0}),
    ("credit_chan", "w64_c5_f2_b1", {"W": 64, "CREDITS": 5, "LF": 2, "LB": 1, "TLAST_EN": 0, "TKEEP_EN": 0, "TUSER_W": 0}),
    ("credit_chan", "w16_c8_f1_b1", {"W": 16, "CREDITS": 8, "LF": 1, "LB": 1, "TLAST_EN": 0, "TKEEP_EN": 0, "TUSER_W": 0}),
    ("credit_chan", "w8_c16_f4_b4", {"W": 8, "CREDITS": 16, "LF": 4, "LB": 4, "TLAST_EN": 0, "TKEEP_EN": 0, "TUSER_W": 0}),
]


def sources(block: str, impl: str) -> list[Path]:
    if impl == "sv":
        return sorted((ROOT / "ip_lib" / block / "rtl").glob("*.sv"))
    return [ROOT / "ip_lib" / block / "hardcaml" / "build" / "rtl" / f"{block}.sv"]


def jobs(parts: list[str]) -> list[list]:
    out = []
    for pk in parts:
        part, clk = PARTS[pk]
        for block, label, g in POINTS:
            for impl in ("sv", "hc"):
                flat = [x for kv in g.items() for x in kv]
                name = f"{block}_{label}_{pk}_{impl}"
                out.append([name, part, block, clk, flat, [str(s) for s in sources(block, impl)], str(BUILD / name)])
    return out


def tcl_list(x) -> str:
    if isinstance(x, (list, tuple)):
        return "{" + " ".join(tcl_list(i) for i in x) + "}"
    return str(x)


def num(pat: str, text: str, col: int = 1):
    m = re.search(pat, text)
    return float(m.group(col)) if m else None


def parse(d: Path) -> dict:
    r = {"dir": d.name}
    if (d / "error.txt").exists():
        return {**r, "error": (d / "error.txt").read_text().strip()[:300]}
    if not (d / "utilization.rpt").exists():
        return {**r, "error": "no report"}
    u = (d / "utilization.rpt").read_text()
    t = (d / "timing_summary.rpt").read_text()
    r["lut"] = num(r"\| (?:Slice|CLB) LUTs\*?\s*\|\s*(\d+)", u)
    r["ff"] = num(r"\| (?:Slice|CLB) Registers\s*\|\s*(\d+)", u)
    r["lutram"] = num(r"\| LUT as Distributed RAM\s*\|\s*(\d+)", u)
    r["wns_ns"] = num(r"WNS\(ns\)[\s\S]*?\n\s*-+[\s\S]*?\n\s*(-?\d+\.\d+)", t)
    r["whs_ns"] = num(r"WHS\(ns\)[\s\S]*?\n\s*-+[\s\S]*?\n\s*-?\d+\.\d+\s+-?\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)", t)
    return r


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "parse"
    parts = (sys.argv[sys.argv.index("--parts") + 1].split(",") if "--parts" in sys.argv else ["a7", "k26"])
    js = jobs(parts)
    if cmd == "run":
        BUILD.mkdir(parents=True, exist_ok=True)
        jf = BUILD / "jobs.tcl"
        jf.write_text("set jobs {" + " ".join(tcl_list(j) for j in js) + "}\n")
        viv = subprocess.run([sys.executable, str(ROOT / "flow" / "version_pin.py"), "--vivado"], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run([viv, "-mode", "batch", "-nojournal", "-log", str(BUILD / "vivado.log"), "-source", str(ROOT / "tools/hardcaml/ooc_compare.tcl"),
                        "-tclargs", str(jf)], check=False)
    rows = []
    for j in js:
        r = parse(Path(j[6]))
        pk = [k for k, v in PARTS.items() if v[0] == j[1]][0]
        r.update({"block": j[2], "part": j[1], "clock_ns": j[3], "impl": "Hardcaml" if j[0].endswith("_hc") else "SV", "point": j[0]})
        if r.get("wns_ns") is not None:
            r["fmax_mhz"] = round(1000.0 / (j[3] - r["wns_ns"]), 1)
        rows.append(r)
    out = ROOT / "results" / "b171" / "ooc_compare.json"
    out.write_text(json.dumps(rows, indent=1) + "\n")
    for r in rows:
        print(r["point"], {k: r.get(k) for k in ("lut", "ff", "lutram", "wns_ns", "whs_ns", "fmax_mhz", "error")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
