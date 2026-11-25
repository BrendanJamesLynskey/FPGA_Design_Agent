#!/usr/bin/env python3
"""Our own per-logic-level delay and per-register overhead, from post-route timing reports (brief 189 item 13; idea from Edwards 2026, ch 10, 17).

The textbook latency budget is (logic levels x delay per level) + (overhead per register stage). The book's figures are placeholders for its
own device; ours come from Vivado's post-route ``report_timing`` paths on the parts this project uses (xck26-sfvc784-2LV-c, 7a100t-csg324-1).

For every setup path that starts at a register and ends at a register (no DSP, RAM, I/O or clock-crossing in the cell list) the data-path rows
are read in order: the clock-to-Q of the source register, then for each logic level (LUT, MUXF, CARRY) the net that feeds it and the cell's own
propagation delay, then the last net and the destination register's setup time. Reported per part:

* ``per_level``: mean of (feeding net + cell delay), and the two halves, over all levels, and by cell type (LUT5, LUT6, MUXF7, CARRY8 ...);
* ``register_overhead``: clock-to-Q, the net from the source register to its first level, the last net into the destination register, the setup time
  (clock uncertainty and skew are separate and not included);
* ``fit``: ordinary least squares of (data path delay + setup) on the number of logic levels over all paths: the slope is the per-level delay in
  practice (it includes routing and fan-out growing with depth) and the intercept the fixed cost per register stage, with n, R squared and the
  range of levels covered.

These are reports of placed-and-routed fixtures of one kind (LUT networks, brief 89, Vivado 2026.1, out of context): the numbers describe LUT-dominated
paths with the fan-out of those networks, not every design. A stage budget uses them as a first estimate; the design's own report decides.

    python3 -m flow.level_delay REPORT.rpt [REPORT.rpt ...] [--out level_delay.json]"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ROW = re.compile(
    r"^\s+(?:\S+\s+)?(?P<type>[A-Z][A-Z0-9_]+) \((?P<kind>Prop|Setup|Hold)_[^)]*\)\s*(?:\n\s+)?(?P<incr>-?[0-9.]+)\s+(?P<path>-?[0-9.]+)\s+[rf]?\s*(?P<name>\S+)"
    r"|^\s+net \(fo=(?P<fo>\d+)(?:, (?:routed|estimated|unplaced))?\)\s+(?P<nincr>-?[0-9.]+)\s+(?P<npath>-?[0-9.]+)\s+(?P<nname>\S+)",
    re.M)
_LEVEL_TYPES = re.compile(r"^(LUT\d|MUXF\d|CARRY\d|SRL\w*|LUTRAM|RAMD\w*)$")
_REG_TYPES = re.compile(r"^(FDRE|FDSE|FDCE|FDPE)$")
_SETUP = re.compile(r"\(Setup_\S+\)\s*(?:\n\s+)?(-?[0-9.]+)")


def device_of(text: str) -> str | None:
    m = re.search(r"\|\s*Device\s*:\s*(\S+)", text)
    return m.group(1) if m else None


def parse_paths(text: str) -> list[dict[str, Any]]:
    """Register-to-register setup paths of a timing report, with the delay of each level and net."""
    from flow.digest import timing as T
    heads = list(re.finditer(r"^Slack \((MET|VIOLATED)\)", text, re.M))
    out = []
    for i, h in enumerate(heads):
        blk = text[h.start():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if not re.search(r"Path Type:\s+Setup", blk):
            continue
        body = T._path_body(blk)
        rows = [m for m in _ROW.finditer(body)]
        cells = [(m["type"], float(m["incr"]), m["kind"]) for m in rows if m["type"]]
        # the order of rows: cell, net, cell, net, ... cell
        seq: list[tuple[str, Any]] = []
        for m in rows:
            seq.append(("cell", (m["type"], float(m["incr"]))) if m["type"] else ("net", (float(m["nincr"]), int(m["fo"]))))
        if not seq or seq[0][0] != "cell" or not _REG_TYPES.match(seq[0][1][0]):
            continue
        if any(c[0].startswith(("DSP", "RAMB", "URAM", "IBUF", "OBUF", "BUFG", "GT")) for c in cells):
            continue
        clk2q = seq[0][1][1]
        levels, pending_net, first_net, last_net = [], None, None, 0.0
        for kind, v in seq[1:]:
            if kind == "net":
                pending_net = v
                if first_net is None:
                    first_net = v[0]
                last_net = v[0]
            elif _LEVEL_TYPES.match(v[0]):
                levels.append({"type": v[0], "cell_ns": v[1], "net_ns": pending_net[0] if pending_net else 0.0, "fanout": pending_net[1] if pending_net else None})
                pending_net = None
        if not levels:
            continue
        # the net after the last level is the one into the destination register (the last row of kind net in the body)
        sm = _SETUP.search(blk)
        dp = re.search(r"Data Path Delay:\s*(-?[0-9.]+)ns", blk)
        out.append({"levels": levels, "n_levels": len(levels), "clk_to_q_ns": clk2q, "first_net_ns": first_net or 0.0,
                    "last_net_ns": last_net, "setup_ns": float(sm.group(1)) if sm else None,
                    "data_path_ns": float(dp.group(1)) if dp else None, "vivado_logic_levels": int(re.search(r"Logic Levels:\s*(\d+)", blk)[1])})
    return out


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 4) if xs else None


def ols(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    n = len(xs)
    if n < 3 or len(set(xs)) < 2:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    icpt = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (icpt + slope * x)) ** 2 for x, y in zip(xs, ys))
    return {"slope_ns_per_level": round(slope, 4), "intercept_ns": round(icpt, 4), "r2": round(1 - ss_res / ss_tot, 4) if ss_tot else None, "n": n,
            "levels_min": int(min(xs)), "levels_max": int(max(xs))}


def summarise(paths: list[dict[str, Any]]) -> dict[str, Any]:
    levels = [lv for p in paths for lv in p["levels"]]
    by_type: dict[str, dict[str, Any]] = {}
    for t in sorted({lv["type"] for lv in levels}):
        ls = [lv for lv in levels if lv["type"] == t]
        by_type[t] = {"n": len(ls), "cell_ns": _mean([x["cell_ns"] for x in ls]), "net_ns": _mean([x["net_ns"] for x in ls]),
                      "level_ns": _mean([x["cell_ns"] + x["net_ns"] for x in ls])}
    withsetup = [p for p in paths if p["setup_ns"] is not None and p["data_path_ns"] is not None]
    return {"paths": len(paths), "levels": len(levels),
            "per_level": {"cell_ns": _mean([x["cell_ns"] for x in levels]), "net_ns": _mean([x["net_ns"] for x in levels]),
                          "level_ns": _mean([x["cell_ns"] + x["net_ns"] for x in levels]), "by_type": by_type},
            "register_overhead": {"clk_to_q_ns": _mean([p["clk_to_q_ns"] for p in paths]), "first_net_ns": _mean([p["first_net_ns"] for p in paths]),
                                  "last_net_ns": _mean([p["last_net_ns"] for p in paths]), "setup_ns": _mean([p["setup_ns"] for p in withsetup])},
            "fit": ols([p["n_levels"] for p in withsetup], [p["data_path_ns"] + p["setup_ns"] for p in withsetup])}


def analyse(reports: list[Path]) -> dict[str, Any]:
    by_part: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, list[str]] = {}
    ver = set()
    for r in reports:
        text = r.read_text(errors="replace")
        part = device_of(text) or "unknown"
        m = re.search(r"Vivado v\.?(\S+)", text)
        if m:
            ver.add(m.group(1))
        by_part.setdefault(part, []).extend(parse_paths(text))
        files.setdefault(part, []).append(str(r))
    return {"enforced": False, "vivado": sorted(ver), "parts": {p: {**summarise(ps), "reports": len(files[p])} for p, ps in sorted(by_part.items())}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rec = analyse([Path(r) for r in a.reports])
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    for part, s in rec["parts"].items():
        f = s["fit"] or {}
        print(f"{part}: {s['paths']} paths, {s['levels']} levels; per level {s['per_level']['level_ns']} ns "
              f"(cell {s['per_level']['cell_ns']} + net {s['per_level']['net_ns']}); clk-to-Q {s['register_overhead']['clk_to_q_ns']} ns, setup {s['register_overhead']['setup_ns']} ns; "
              f"fit {f.get('slope_ns_per_level')} ns/level + {f.get('intercept_ns')} ns (R2 {f.get('r2')}, n {f.get('n')}, levels {f.get('levels_min')}-{f.get('levels_max')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
