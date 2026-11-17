#!/usr/bin/env python3
"""Unbounded proof attempts (brief 81): k-induction and PDR on the AXI4-Lite checker, the stream checker and a generated register block.

    python3 axi_tx/formal/unbounded.py [--json results/81_verification/unbounded.json] [--timeout 900]

Every attempt is recorded, whatever it returns: PASS (a proof for all cycles), FAIL (a counterexample), UNKNOWN or TIMEOUT.
Engines: `smtbmc z3` in prove mode (k-induction) and `abc pdr` (property-directed reachability, which needs no hand-written
invariant). A proof for all cycles of the checkers' "quiet" property says: on legal traffic the checker never fires.
Needs sby, yosys, z3 and abc on PATH (set FDA_OSS_CAD to the OSS CAD Suite folder).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import run_formal as rf  # noqa: E402
from hwsw.tests import regmap_formal  # noqa: E402

ENGINES = {"k-induction": "smtbmc z3", "pdr": "abc pdr"}


def sby_run(job: Path, work: Path, timeout: float) -> tuple[str, float]:
    if work.exists():
        shutil.rmtree(work)
    t0 = time.time()
    p = subprocess.Popen(["sby", "-f", "-d", str(work), str(job)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         cwd=job.parent, start_new_session=True)
    try:
        log, _ = p.communicate(timeout=timeout)
        st = (work / "status").read_text().split()[0] if (work / "status").exists() else "ERROR"
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGTERM)
        log, _ = p.communicate()
        st = "TIMEOUT"
    (job.parent / f"{job.stem}.log").write_text(log)
    return st, round(time.time() - t0, 1)


def checker(unit: str, method: str, out: Path, timeout: float) -> dict:
    u = rf.UNITS[unit]
    d = out / f"{unit}_{method}"
    d.mkdir(parents=True, exist_ok=True)
    (d / u["rtl"]).write_text((rf.RTL / u["rtl"]).read_text())
    text = rf.sby_text(u, "-DQUIET", "prove", 20).replace(f"\n{u['rtl']}\n", f"\n{d / u['rtl']}\n")
    text = text.replace("smtbmc z3", ENGINES[method])
    (d / "job.sby").write_text(text)
    st, sec = sby_run(d / "job.sby", d / "run", timeout)
    return {"block": f"{unit} protocol rules ('quiet': never fires on legal traffic)", "method": method, "engine": ENGINES[method], "status": st, "seconds": sec}


def regmap_block(method: str, out: Path, timeout: float) -> dict:
    d = out / f"regmap_{method}"
    regmap_formal.ENGINES["prove"] = ENGINES[method]
    t0 = time.time()
    st = regmap_formal.run(ROOT / "hwsw/examples/demo_accel.yaml", d, "prove", 20, timeout=timeout)
    return {"block": "generated register block demo_accel (slave rules)", "method": method, "engine": ENGINES[method], "status": st,
            "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", type=Path, default=ROOT / "results/81_verification/unbounded.json")
    ap.add_argument("--work", type=Path, default=ROOT / "build/81/unbounded")
    ap.add_argument("--timeout", type=float, default=900)
    a = ap.parse_args(argv)
    cad = os.environ.get("FDA_OSS_CAD")
    if cad:
        os.environ["PATH"] = f"{cad}/bin:" + os.environ["PATH"]
    rows = []
    for method in ("k-induction", "pdr"):
        for unit in ("axil", "axis"):
            rows.append(checker(unit, method, a.work, a.timeout)); print(rows[-1], flush=True)
        rows.append(regmap_block(method, a.work, a.timeout)); print(rows[-1], flush=True)
    res = {"tool": subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip(), "timeout_s": a.timeout, "attempts": rows}
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
