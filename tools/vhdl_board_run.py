#!/usr/bin/env python3
"""The brief 55 board run: one VHDL design on the Nexys A7 (SRAM only), its UART shell self-check, conditions logged.

    python3 tools/vhdl_board_run.py <task_dir> <design dir> --json OUT

The caller holds _handoff/board.lock (the owner's one-board-job rule). Steps: operating conditions over JTAG
(tools/board_conditions.tcl: die temperature, VCCINT, VCCAUX, VCCBRAM, and the XADC's min/max registers, latched in hardware
since configuration), then flow/board_check.py (power_ok, discover, program SRAM by cable serial, identify, the task's
self-check over the UART shell, still_alive), then the conditions again, now including the min/max since this
configuration. Verdict per house rule: inside or outside the recommended operating conditions (Artix-7 -1, the knowledge
bank's `artix7-speed-grade-limits`: VCCINT 0.95-1.05 V, VCCAUX 1.71-1.89 V, VCCBRAM 0.95-1.05 V) and the board's own
limit (junction <= 85 C). The XADC samples at about 1 MSPS across channels: nanosecond droop is not visible to it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow import board_check, hw  # noqa: E402

ROC = {"VCCINT": (0.95, 1.05), "VCCAUX": (1.71, 1.89), "VCCBRAM": (0.95, 1.05), "TEMPERATURE": (None, 85.0)}


def conditions(out: Path, tag: str) -> dict:
    b = hw.load_board(None)
    with hw.HwServer(out):
        text = hw.run_vivado_tcl(ROOT / "tools" / "board_conditions.tcl", [b["cable_serial"]], out, f"conditions_{tag}",
                                 timeout_s=300)
    res: dict = {"time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for line in text.splitlines():
        m = re.match(r"FDA-COND (NOW|MAX|MIN) (.*)", line)
        if m:
            res[m.group(1).lower()] = {k: float(v) for k, v in re.findall(r"(\w+)=([-\d.eE+]+)", m.group(2))}
        if line.startswith("FDA-COND FLAGS"):
            res["flags"] = line.split()[-1]
    return res


def verdict(samples: list[dict]) -> dict:
    bad = []
    for s in samples:
        for kind in ("now", "max", "min"):
            for k, (lo, hi) in ROC.items():
                v = (s.get(kind) or {}).get(k)
                if v is None:
                    continue
                if (lo is not None and v < lo) or (hi is not None and v > hi):
                    bad.append(f"{s['time']} {kind} {k}={v}")
    return {"inside_roc": not bad, "outside": bad,
            "limits": {k: list(v) for k, v in ROC.items()}, "note": "XADC: about 1 MSPS across channels; no nanosecond droop"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task", type=Path)
    ap.add_argument("design", type=Path)
    ap.add_argument("--json", type=Path, required=True)
    a = ap.parse_args(argv)
    design = a.design.resolve()
    out = ROOT / "build" / "b55_board"
    name = f"designs.{design.name}.selfcheck"
    spec = importlib.util.spec_from_file_location(name, a.task.resolve() / "hidden" / "selfcheck.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    before = conditions(out, "before")
    board_check.RESULTS = out / "board_check"
    rc = board_check.main([str(design.relative_to(ROOT)), "--runs", "1"])
    after = conditions(out, "after")
    bc = json.loads((board_check.RESULTS / f"{design.name}.json").read_text())
    r = {"task": a.task.name, "design": str(design.relative_to(ROOT)), "board_check_rc": rc, "pass": bc.get("pass"),
         "board_check": bc, "conditions": [before, after], "verdict": verdict([before, after])}
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(r, indent=1) + "\n")
    print(json.dumps({"pass": r["pass"], "inside_roc": r["verdict"]["inside_roc"], "before": before.get("now"),
                      "after_max": after.get("max")}))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
