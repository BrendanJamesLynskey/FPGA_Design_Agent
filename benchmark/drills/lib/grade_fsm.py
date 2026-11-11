#!/usr/bin/env python3
"""Grader of the brief 24 FSM drills: behaviour, latency and what drives the pins.

    python3 benchmark/drills/lib/grade_fsm.py <task dir> <design dir> [--json out.json] [--dcp checkpoint]

<design dir> is the agent's design (rtl/ and, for the pin check, its build/base/post_route.dcp or post_synth.dcp). Checks:

    behaviour   the hidden acceptance bench (benchmark/tools/run_task.py) passes on <design>/rtl; the bench also tells the lag
                (clocks by which the pins trail the state table) which the pins follow, from hidden/grade.yaml's allowed_lags
    pins        every output port in grade.yaml is driven by a flip-flop (FD*) when `require_flop_driven_outputs` is true
                (drill d24_registered_outputs); recorded, not required, otherwise

and records the CHOICE the design made, from the two facts: flop-driven and lag 1 = registered decode of the state; flop-driven
and lag 0 = lookahead (decode of the next state); LUT-driven and lag 0 = combinational Moore / Mealy. No LLM is involved.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def drivers(dcp: Path, ports: list[str]) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "d.txt"
        subprocess.run(["vivado", "-mode", "batch", "-nojournal", "-nolog", "-source", str(HERE / "driver_cells.tcl"), "-tclargs", str(dcp), str(out), *ports],
                       check=True, capture_output=True, text=True)
        return {l.split()[0]: l.split()[1] for l in out.read_text().splitlines() if l.strip()}


def classify(flop: bool | None, lag: int | None) -> str:
    if lag is None or flop is None:
        return "unknown"
    if flop:
        return "registered decode of the state (one clock late)" if lag >= 1 else "lookahead: registered decode of the next state"
    return "combinational (Moore decode, Mealy where the spec asks) or logic after the flip-flops"


def grade(task: Path, design: Path, dcp: Path | None = None, drv: dict[str, str] | None = None) -> dict[str, Any]:
    need = yaml.safe_load((task / "hidden" / "grade.yaml").read_text())
    checks: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as t:
        lagf = Path(t) / "lag.txt"
        env = dict(os.environ, FDA_DRILL_LAG_FILE=str(lagf), PYTHONPATH=str(ROOT))
        out = Path(t) / "r.json"
        subprocess.run([sys.executable, str(ROOT / "benchmark" / "tools" / "run_task.py"), str(task), "--rtl", str(design / "rtl"), "--json", str(out)],
                       env=env, capture_output=True, text=True)
        r = json.loads(out.read_text()) if out.exists() else {}
        lag_s = lagf.read_text().strip() if lagf.exists() else ""
    lag = int(lag_s) if lag_s.isdigit() else None
    checks["behaviour"] = {"pass": bool(r.get("pass")), "lag": lag, "allowed_lags": need["allowed_lags"],
                           "failing": [k for k, v in (r.get("tests") or {}).items() if not v] if isinstance(r.get("tests"), dict) else None}
    flop = None
    if drv is None and dcp is None:
        for n in ("post_route.dcp", "post_synth.dcp"):
            if (design / "build" / "base" / n).exists():
                dcp = design / "build" / "base" / n
                break
    if drv is None and dcp is not None:
        drv = drivers(dcp, need["output_ports"])
    if drv:
        kinds = {p: ("flop" if t.startswith("FD") else "lut" if t.startswith("LUT") else t) for p, t in drv.items()}
        flop = all(k == "flop" for k in kinds.values())
        checks["pins"] = {"pass": flop or not need["require_flop_driven_outputs"], "drivers": kinds, "required": need["require_flop_driven_outputs"]}
    else:
        checks["pins"] = {"pass": not need["require_flop_driven_outputs"], "error": "no checkpoint to read the pin drivers from",
                          "required": need["require_flop_driven_outputs"]}
    return {"task": task.name, "pass": all(c["pass"] for c in checks.values()), "checks": checks, "choice": classify(flop, lag)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task")
    ap.add_argument("design")
    ap.add_argument("--dcp")
    ap.add_argument("--json")
    a = ap.parse_args()
    rep = grade(Path(a.task), Path(a.design), Path(a.dcp) if a.dcp else None)
    print(json.dumps(rep, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1) + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
