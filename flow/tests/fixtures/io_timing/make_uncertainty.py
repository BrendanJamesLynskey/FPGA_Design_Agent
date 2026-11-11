#!/usr/bin/env python3
"""The brief 20 part B clock-uncertainty table (U1-U8) from measure_u.tcl's reports and the Clocking Wizard read-back:
results/20_timing_exceptions/uncertainty.md and .json.
    make_uncertainty.py --collect <measure_u out dir> <clkwiz.jsonl>   copy trimmed reports into golden_u/, then write the table
    make_uncertainty.py [--check]                                      write (or check) the table from golden_u/"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from flow import gates  # noqa: E402

G = HERE / "golden_u"
OUT = ROOT / "results" / "20_timing_exceptions"
RUNS = {"u1_base": "U1 base (no jitter set)", "u2_input_jitter": "U2 set_input_jitter 0.1 on the board clock",
        "u3_system_jitter": "U3 set_system_jitter 0.1", "u6_slow_only": "U6 Slow corner only",
        "u6_fast_only": "U6 Fast corner only", "u4_margin/signoff": "U4 built with a 0.5 ns setup margin on clk200, removed before routing"}
PATHS = {"full_period": "clk200 -> clk200 (24-bit add)", "half_period": "clk200 rise -> fall (half period)",
         "crossing": "clk100 -> clk200 (two MMCM outputs)"}
SUMMARIES = {"u4_margin/placed_with_margin.rpt": "U4 placed, margin on", "u4_margin/placed_margin_removed.rpt": "U4 placed, margin removed",
             "u4_margin/routed_with_margin.rpt": "U4 routed, margin re-applied (report only)"}


def head(text: str) -> str:
    """The path summary lines of a report_timing report (slack to the uncertainty parts), nothing of the path detail."""
    keep = []
    for l in text.splitlines():
        if l.startswith(("Slack", "  Source:", "  Destination:", "  Requirement:", "  Clock Path Skew", "    Clock Pessimism",
                         "  Clock Uncertainty", "    Total System", "    Total Input", "    Discrete", "    Phase Error",
                         "    User Uncertainty", "    Destination Clock Delay", "    Source Clock Delay")):
            keep.append(l)
    return "\n".join(keep) + "\n"


def collect(src: Path, cw: Path) -> None:
    for r in RUNS:
        for p in PATHS:
            for k in ("setup", "hold"):
                f = src / r / f"{p}_{k}.rpt"
                if f.exists():
                    d = G / r
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f.name).write_text(head(f.read_text()))
        ts = src / r / "timing_summary.rpt"
        if ts.exists():
            (G / r / "timing_summary.txt").write_text(json.dumps(gates.parse_timing_summary(ts.read_text())) + "\n")
    for f, _ in SUMMARIES.items():
        p = src / f
        (G / f).parent.mkdir(parents=True, exist_ok=True)
        (G / (f[:-4] + ".txt")).write_text(json.dumps(gates.parse_timing_summary(p.read_text())) + "\n")
    shutil.copyfile(cw, G / "clkwiz.jsonl")
    xdc = next(cw.parent.rglob("cw_u.xdc"))       # the wizard's own constraints: it sets the input jitter itself
    (G / "clkwiz_xdc_lines.txt").write_text("\n".join(l for l in xdc.read_text().splitlines()
                                                     if "create_clock" in l or "jitter" in l) + "\n")


def num(rx: str, t: str) -> float | None:
    m = re.search(rx, t, re.M)
    return float(m.group(1)) if m else None


def rows() -> dict:
    out: dict = {"paths": [], "summaries": {}, "clkwiz": {}}
    for r, what in RUNS.items():
        for p, pw in PATHS.items():
            for k in ("setup", "hold"):
                f = G / r / f"{p}_{k}.rpt"
                if not f.exists():
                    continue
                t = f.read_text()
                out["paths"].append({"run": r, "what": what, "path": pw, "check": k,
                                     "slack_ns": num(r"^Slack[^:]*:\s*(-?[\d.]+)ns", t),
                                     "requirement_ns": num(r"Requirement:\s*(-?[\d.]+)ns", t),
                                     "uncertainty_ns": num(r"Clock Uncertainty:\s*(-?[\d.]+)ns", t) or 0.0,
                                     "tsj_ns": num(r"\(TSJ\):\s*(-?[\d.]+)ns", t), "tij_ns": num(r"\(TIJ\):\s*(-?[\d.]+)ns", t),
                                     "dj_ns": num(r"\(DJ\):\s*(-?[\d.]+)ns", t), "pe_ns": num(r"\(PE\):\s*(-?[\d.]+)ns", t),
                                     "cpr_ns": num(r"\(CPR\):\s*(-?[\d.]+)ns", t)})
        ts = G / r / "timing_summary.txt"
        if ts.exists():
            out["summaries"][what] = json.loads(ts.read_text())
    for f, what in SUMMARIES.items():
        out["summaries"][what] = json.loads((G / (f[:-4] + ".txt")).read_text())
    cw = json.loads((G / "clkwiz.jsonl").read_text().splitlines()[0])
    out["clkwiz"] = {k.replace("CONFIG.", ""): cw[k] for k in ("CONFIG.MMCM_CLKFBOUT_MULT_F", "CONFIG.MMCM_DIVCLK_DIVIDE",
                     "CONFIG.MMCM_CLKOUT0_DIVIDE_F", "CONFIG.MMCM_CLKOUT1_DIVIDE", "CONFIG.CLKOUT1_JITTER",
                     "CONFIG.CLKOUT1_PHASE_ERROR", "CONFIG.CLKOUT2_JITTER", "CONFIG.CLKOUT2_PHASE_ERROR")}
    out["clkwiz_xdc"] = (G / "clkwiz_xdc_lines.txt").read_text().strip().splitlines()
    return out


def md(d: dict) -> str:
    f = lambda x: "-" if x is None else f"{x:g}"
    o = ["# Brief 20 part B: clock uncertainty measured (Vivado 2025.2, xc7a100tcsg324-1, routed)", "",
         "Generated by `flow/tests/fixtures/io_timing/make_uncertainty.py` from `golden_u/` (measure_u.tcl on `io_u`: 100 MHz",
         "CLK100MHZ into an MMCME2_BASE, VCO 1000 MHz, clk200 = /5, clk100 = /10; the worst path of each kind). ns throughout.", "",
         "| run | path | check | slack | requirement | uncertainty | TSJ | TIJ | DJ | PE | CPR |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in d["paths"]:
        o.append(f"| {r['what']} | {r['path']} | {r['check']} | {f(r['slack_ns'])} | {f(r['requirement_ns'])} | {f(r['uncertainty_ns'])} | "
                 f"{f(r['tsj_ns'])} | {f(r['tij_ns'])} | {f(r['dj_ns'])} | {f(r['pe_ns'])} | {f(r['cpr_ns'])} |")
    o += ["", "| design timing summary | WNS | WHS |", "|---|---|---|"]
    for k, v in d["summaries"].items():
        o.append(f"| {k} | {f(v['wns_ns'])} | {f(v['whs_ns'])} |")
    o += ["", "Clocking Wizard read-back for the same request (100 MHz in, 200 and 100 MHz out; `flow/clkwiz_probe.tcl`, input jitter "
          "left at the wizard's default): " + ", ".join(f"{k} {v}" for k, v in d["clkwiz"].items()) + " (jitter and phase error in ps). The wizard's generated XDC: " + "; ".join(f"`{l}`" for l in d["clkwiz_xdc"]) + "."]
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--collect":
        collect(Path(sys.argv[2]), Path(sys.argv[3]))
    d = rows()
    text, js = md(d), json.dumps(d, indent=2) + "\n"
    if "--check" in sys.argv:
        sys.exit(0 if (OUT / "uncertainty.md").read_text() == text and (OUT / "uncertainty.json").read_text() == js else 1)
    (OUT / "uncertainty.md").write_text(text)
    (OUT / "uncertainty.json").write_text(js)
    print(len(d["paths"]), "paths")
