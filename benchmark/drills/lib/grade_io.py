#!/usr/bin/env python3
"""I/O-timing grader of the brief 20 part B drills: are the agent's input delays, jitter and margin right?

    python3 benchmark/drills/lib/grade_io.py <task dir> <design dir> [--json out.json]

<task dir>/hidden/constraints.yaml says what the task needs (its I/O interfaces with their data-sheet numbers, the
board clock's input jitter, the implementation-only margin). <design dir> is the agent's design: design.xdc, build.yaml
and its routed build build/base/ (gates.json, io_paths_route.txt from flow/io_paths.tcl, timing_margin.txt). Checks
(each pass/fail, all must pass):

    routed        the build reached routing and gates.json passes
    interface     flow/io_check.py with the task's interfaces after routing: -max and -min on every interface port, equal to
                  the data-sheet formula, relative to the board clock, IOB-packed; setup and hold slack of the ports >= 0
    no_invented   FDA-CON-11/-12/-13 clean (no made-up delay on the slow ports, every non-zero delay with its formula, no
                  -min above -max, no clock used before it is defined)
    input_jitter  the board clock carries set_input_jitter of the task's value
    margin        build.yaml timing_margin_ns is the task's margin (the flow applies it for opt/place/phys_opt and takes it
                  off before routing) and design.xdc has no setup set_clock_uncertainty (which would be in sign-off)

No LLM is involved; every input is a tool report or the agent's own files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from agent.core import constraints as con  # noqa: E402
from flow import io_check  # noqa: E402


def grade(task: Path, design: Path) -> dict[str, Any]:
    need = yaml.safe_load((task / "hidden" / "constraints.yaml").read_text())
    build = design / "build" / "base"
    xdc_p = design / "design.xdc"
    xdc = xdc_p.read_text() if xdc_p.exists() else ""
    checks: dict[str, dict[str, Any]] = {}
    g = json.loads((build / "gates.json").read_text()) if (build / "gates.json").exists() else {}
    checks["routed"] = {"pass": bool(g.get("pass")) and (build / "timing_summary.rpt").exists(),
                        "wns_ns": (g.get("timing") or {}).get("wns_ns"), "whs_ns": (g.get("timing") or {}).get("whs_ns")}
    dump_p = build / "io_paths_route.txt"
    dump = io_check.parse_io_dump(dump_p.read_text()) if dump_p.exists() else None
    port = need.get("board_clock_port", "CLK100MHZ")
    board_clk = next((c for c, v in (dump or {}).get("clocks", {}).items() if not v["virtual"] and v["source"] == port), None)
    ifs = []
    for i in need.get("io_interfaces") or []:
        i = dict(i)
        if i.get("clock") == "<board clock>":
            i["clock"] = board_clk
        ifs.append(i)
    if dump is None:
        checks["interface"] = {"pass": False, "error": "no io_paths_route.txt (the build did not reach routing with this flow)"}
    else:
        r = io_check.evaluate(build, "route", [xdc_p], ifs, None,
                              (yaml.safe_load((ROOT / "boards" / need["board"] / "board.yaml").read_text()) or {}).get("slow_ports"))
        mine = [f for f in r["failures"] if f["rule"] not in ("IO-INVENTED", "IO-NO-FORMULA")]
        rep = r["interfaces"]
        slack_ok = all((x.get("setup_slack_ns") or -1) >= 0 and (x.get("hold_slack_ns") or -1) >= 0 for x in rep) and bool(rep)
        checks["interface"] = {"pass": not mine and slack_ok, "failures": mine, "interfaces": rep, "board_clock": board_clk}
    board = ROOT / "boards" / need.get("board", "nexys_a7_100t")
    found = [x for x in con.check_xdc(xdc, board) if x["rule"] in ("FDA-CON-11", "FDA-CON-12", "FDA-CON-13")] if xdc else []
    checks["no_invented"] = {"pass": bool(xdc) and not found, "findings": found}
    if need.get("input_jitter_ns") is not None:
        ij = ((dump or {}).get("clocks", {}).get(board_clk) or {}).get("input_jitter")
        # UG903 ch. 3 calls set_input_jitter 0.1 "+/-100 ps", while UG906's uncertainty formula halves it: a peak-to-peak
        # data-sheet value written as itself or as its half is accepted (the reading is recorded)
        want = float(need["input_jitter_ns"])
        checks["input_jitter"] = {"pass": ij is not None and min(abs(ij - want), abs(ij - want / 2)) < 1e-3,
                                  "input_jitter_ns": ij, "want_ns": float(need["input_jitter_ns"])}
    if need.get("timing_margin_ns") is not None:
        cfg = yaml.safe_load((design / "build.yaml").read_text()) if (design / "build.yaml").exists() else {}
        m = float((cfg or {}).get("timing_margin_ns") or 0.0)
        unc = [l.strip() for l in xdc.splitlines()
               if re.match(r"\s*set_clock_uncertainty\b", l.split("#", 1)[0]) and "-hold" not in l]
        applied = (build / "timing_margin.txt").exists()
        checks["margin"] = {"pass": abs(m - float(need["timing_margin_ns"])) < 1e-3 and applied and not unc,
                            "build_yaml_margin_ns": m, "applied_by_flow": applied, "xdc_uncertainty_lines": unc,
                            "want_ns": float(need["timing_margin_ns"])}
    delay_lines = [l.strip() for l in xdc.splitlines() if re.match(r"\s*(set_input_delay|set_output_delay|set_input_jitter|"
                                                                    r"set_clock_uncertainty|set_system_jitter)\b", l)]
    return {"task": task.name, "design": str(design), "pass": all(c["pass"] for c in checks.values()),
            "checks": checks, "xdc_timing_lines": delay_lines}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("task", type=Path)
    ap.add_argument("design", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    r = grade(a.task, a.design)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    print(f"{r['task']}: {'PASS' if r['pass'] else 'FAIL'}")
    for k, c in r["checks"].items():
        print(f"  {'ok  ' if c['pass'] else 'FAIL'} {k}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
