#!/usr/bin/env python3
"""Simulation check of a drill design's multicycle: the registers its multicycle names (from a flow/mcp_paths.tcl dump)
must all change on one phase of the N-clock enable (brief 20: the structural check accepts a register whose CE cone merely
contains the enable, as in CE = tick OR write; this catches it).

    python3 benchmark/drills/lib/sim_enable_check.py <task dir> <design dir> --dump mcp_paths_route.txt [--json out]

Cell names map to RTL signals by dropping the "_reg" suffix and any bit index ("u_core/level_q_reg[3]" ->
u_core.level_q). N is the exception's -setup multiplier."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmark.tools import run_task  # noqa: E402
from flow import exceptions_check  # noqa: E402


def sig(cell: str) -> str:
    c = re.sub(r"\[\d+\]$", "", cell)
    c = re.sub(r"_reg$", "", c)
    return c.replace("/", ".")


def pick(dump: dict) -> tuple[list[str], int | None]:
    cells, ns = set(), set()
    for e in dump["exceptions"].values():
        if e["kind"] == "setup":
            ns.add(e["n"])
        for side in ("from", "to"):
            cells.update(c["cell"] for c in e["cells"][side])
    return sorted({sig(c) for c in cells}), (min(ns) if ns else None)


def check(task: Path, rtl: Path, dump: Path) -> dict:
    """The simulation check on the RTL in ``rtl``; returns {pass, signals, n, phase, off_phase, ...}."""
    sigs, n = pick(exceptions_check.parse_mcp_dump(Path(dump).read_text()))
    out: dict = {"signals": sigs, "n": n}
    if not sigs or not n:
        return {**out, "pass": False, "error": "no multicycle registers in the dump"}
    import hashlib
    task = Path(task).resolve()
    tmp = ROOT / "build" / "mcp_enable" / f"{task.name}_{hashlib.sha256(str(Path(rtl).resolve()).encode()).hexdigest()[:10]}"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "mcp_enable.json").unlink(missing_ok=True)
    os.environ.update(FDA_MCP_SIGNALS=json.dumps(sigs), FDA_MCP_N=str(n), FDA_MCP_OUT=str(tmp / "mcp_enable.json"))
    from cocotb_tools.runner import get_runner
    b = run_task.load_bench(task)
    srcs = run_task.sources(task, Path(rtl).resolve())
    r = get_runner("icarus")
    try:
        r.build(sources=[str(x) for x in srcs], hdl_toplevel=b["toplevel"], parameters=b.get("parameters") or {},
                build_dir=tmp, timescale=("1ns", "1ps"), always=True,
                build_args=["-g2012"] + [f"-I{d}" for d in sorted({str(x.parent) for x in srcs})], log_file=tmp / "build.log")
    except (SystemExit, Exception) as e:
        return {**out, "pass": False, "error": f"build failed: {e}"}
    xml = tmp / "results.xml"
    xml.unlink(missing_ok=True)
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(Path(__file__).parent), os.environ.get("PYTHONPATH", "")]),
           "BENCH_TASK": str(task)}
    try:
        r.test(test_module="enable_monitor", hdl_toplevel=b["toplevel"], build_dir=tmp, test_dir=Path(__file__).parent,
               extra_env=env, parameters=b.get("parameters") or {}, timescale=("1ns", "1ps"), results_xml=str(xml),
               log_file=tmp / "sim.log")
    except SystemExit:
        pass
    res = run_task.parse_results(xml)
    detail = json.loads((tmp / "mcp_enable.json").read_text()) if (tmp / "mcp_enable.json").exists() else {}
    return {**out, **detail, "pass": bool(res) and all(res.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("task", type=Path)
    ap.add_argument("design", type=Path)
    ap.add_argument("--dump", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    out = check(a.task, a.design / "rtl", a.dump)
    if a.json:
        a.json.write_text(json.dumps(out, indent=2) + "\n")
    print(f"enable check: {'PASS' if out['pass'] else 'FAIL'}  N {out.get('n')}; registers changing off the enable phase: "
          f"{out.get('off_phase')}")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
