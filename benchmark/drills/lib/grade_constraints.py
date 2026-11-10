#!/usr/bin/env python3
"""Constraint grader of the brief 20 drills: are the agent's timing exceptions present, right and commented?

    python3 benchmark/drills/lib/grade_constraints.py <task dir> <design dir> [--dump mcp.txt] [--json out.json]

<task dir>/hidden/constraints.yaml says what the task needs (clocks allowed, the multicycle N, the false paths allowed).
<design dir> is the agent's design: design.xdc and its routed build build/base/ (gates.json, timing_summary.rpt,
utilization.rpt, the exception reports). The multicycle check reads a dump of the routed checkpoint made by
flow/mcp_paths.tcl: ``build/base/mcp_paths_route.txt`` (the flow writes it after routing), or ``--dump``; for an older build
with neither, the grader runs lib/mcp_paths.tcl on build/base/post_route.dcp, so the caller holds a heavy slot. Checks (each pass/fail, all must pass):

    routed           the build reached routing and gates.json passes
    clocks           only the clocks the task allows (by period), and no more BUFGs than it allows
    xdc_rules        FDA-CON-5 and FDA-CON-10 clean on every exception line (comment naming the enable; -hold N-1)
    exceptions_gate  flow/exceptions_check.py after routing: nothing ignored, every exception covers a path, no
                     TIMING-29/46/47 or XDCH-1
    multicycle       the multicycles are -setup N and -hold N-1 (N from constraints.yaml); every register they name has
                     a clock enable that is not tied and all share a register in their enable cones
                     (flow/exceptions_check.py EXC-MCP-ENABLE); no all_registers or bare * in a multicycle line
    no_broad_waivers no set_clock_groups, and set_false_path only on ports (the board's asynchronous inputs)

A design that met the spec another way (a pipeline instead of the multicycle) fails ``multicycle`` here but is recorded
as ``choice: pipeline`` when it has no multicycle line and timing is met, so the report can say which choice was made.
No LLM is involved; every input is a tool report or the agent's XDC text.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from agent.core import constraints as con  # noqa: E402
from flow import exceptions_check, gates  # noqa: E402

VIVADO = "/opt/Xilinx/2025.2/Vivado/bin/vivado"


parse_dump = exceptions_check.parse_mcp_dump


def bufg_count(build: Path) -> int | None:
    p = build / "utilization.rpt"
    if not p.exists():
        return None
    m = re.search(r"^\|\s*BUFGCTRL\s*\|\s*(\d+)", p.read_text(), re.M)
    return int(m.group(1)) if m else 0


def grade(task: Path, design: Path, dump: Path | None = None) -> dict[str, Any]:
    need = yaml.safe_load((task / "hidden" / "constraints.yaml").read_text())
    build = design / "build" / "base"
    xdc_p = design / "design.xdc"
    xdc = xdc_p.read_text() if xdc_p.exists() else ""
    lines = xdc.splitlines()
    checks: dict[str, dict[str, Any]] = {}

    g = json.loads((build / "gates.json").read_text()) if (build / "gates.json").exists() else {}
    checks["routed"] = {"pass": bool(g.get("pass")) and (build / "timing_summary.rpt").exists(),
                        "wns_ns": (g.get("timing") or {}).get("wns_ns"), "whs_ns": (g.get("timing") or {}).get("whs_ns")}

    board = ROOT / "boards" / need.get("board", "nexys_a7_100t")
    found = [x for x in con.check_xdc(xdc, board) if x["rule"] in ("FDA-CON-5", "FDA-CON-10")] if xdc else []
    checks["xdc_rules"] = {"pass": bool(xdc) and not found, "findings": found}

    if dump is None and (build / "mcp_paths_route.txt").exists():     # flow/build.tcl writes it after routing
        dump = build / "mcp_paths_route.txt"
    try:
        exc = exceptions_check.evaluate(build, "route", [xdc_p], dump)
        checks["exceptions_gate"] = {"pass": exc["pass"], "failures": exc["failures"]}
    except (OSError, ValueError) as e:
        checks["exceptions_gate"] = {"pass": False, "error": f"{type(e).__name__}: {e}"}

    mcp_lines = [(n, l) for n, l in enumerate(lines, 1) if re.match(r"\s*set_multicycle_path\b", l)]
    broad = [l.strip() for _, l in mcp_lines if re.search(r"\[all_registers\b|\[get_(cells|pins)\s+(-hier\w*\s+)?\*\s*\]", l)]
    dump_data = None
    if need.get("multicycle"):
        try:
            if dump is None and (build / "mcp_paths_route.txt").exists():     # flow/build.tcl writes it after routing
                dump = build / "mcp_paths_route.txt"
            if dump is None and (build / "post_route.dcp").exists():
                dump = build / "mcp_paths.txt"
                subprocess.run(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice", "-n", "15",
                                VIVADO, "-mode", "batch", "-nojournal", "-nolog", "-source",
                                str(Path(__file__).parent / "mcp_paths.tcl"), "-tclargs", str(build / "post_route.dcp"),
                                str(dump)], check=False, capture_output=True, timeout=1800)
            dump_data = parse_dump(dump.read_text()) if dump and dump.exists() else None
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            dump_data = {"error": f"{type(e).__name__}: {e}"}

    if dump_data and "clocks" in dump_data and "error" not in dump_data:
        periods = sorted(dump_data["clocks"].values())
        allowed = sorted(float(x) for x in need.get("clock_periods_ns", []))
        n_bufg = bufg_count(build)
        checks["clocks"] = {"pass": periods == allowed and (n_bufg is None or n_bufg <= int(need.get("max_bufg", 1))),
                            "clocks": dump_data["clocks"], "bufg": n_bufg}
    else:
        checks["clocks"] = {"pass": False, "error": "no checkpoint dump"}

    if need.get("multicycle"):
        n = int(need["multicycle"]["n"])
        info: dict[str, Any] = {"broad_lines": broad, "xdc_lines": [l.strip() for _, l in mcp_lines]}
        ok = bool(mcp_lines) and not broad
        if dump_data and "exceptions" in dump_data:
            exc = dump_data["exceptions"]
            setups = {p: e for p, e in exc.items() if e["kind"] == "setup"}
            holds = {p: e for p, e in exc.items() if e["kind"] == "hold"}
            bad = exceptions_check.enable_problems(dump_data)
            regs = sorted({c["cell"] for e in setups.values() for side in ("from", "to") for c in e["cells"][side]})
            info.update({"setup_n": sorted({e["n"] for e in setups.values()}), "hold_n": sorted({e["n"] for e in holds.values()}),
                         "registers": len(regs), "enable_problems": bad})
            ok = (ok and bool(setups) and bool(regs) and {e["n"] for e in setups.values()} == {n}
                  and {e["n"] for e in holds.values()} == {n - 1} and not bad)
        else:
            ok = False
            info["error"] = (dump_data or {}).get("error", "no checkpoint dump")
        checks["multicycle"] = {"pass": ok, **info}

    port_vars = {m.group(1) for l in lines for m in [re.match(r"\s*set\s+(\w+)\s+\[\s*(get_ports|all_inputs|all_outputs)\b", l)] if m}
    on_ports = lambda l: "get_ports" in l or any(re.search(rf"\${v}\b", l) for v in port_vars)
    waivers = [l.strip() for l in lines if re.match(r"\s*set_clock_groups\b", l) or
               (re.match(r"\s*set_false_path\b", l) and not on_ports(l) and not need.get("false_path_cells_ok"))]
    checks["no_broad_waivers"] = {"pass": not waivers, "lines": waivers}

    choice = "multicycle" if mcp_lines else ("pipeline" if checks["routed"]["pass"] else "none")
    return {"task": task.name, "design": str(design), "pass": all(c["pass"] for c in checks.values()), "choice": choice,
            "checks": checks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("task", type=Path)
    ap.add_argument("design", type=Path)
    ap.add_argument("--dump", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    r = grade(a.task, a.design, a.dump)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    print(f"{r['task']}: {'PASS' if r['pass'] else 'FAIL'} (choice: {r['choice']})")
    for k, c in r["checks"].items():
        print(f"  {'ok  ' if c['pass'] else 'FAIL'} {k}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
