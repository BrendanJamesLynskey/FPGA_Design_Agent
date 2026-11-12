#!/usr/bin/env python3
"""Score a VHDL design against a benchmark task's hidden bench (brief 55), with the frozen scorer unchanged.

    python3 -m flow.vhdl_score <task_dir> --rtl <dir with *.vhd> [--sim icarus|verilator] [--seed N] [--json OUT]

The hidden benches are cocotb benches on Icarus or Verilator, with the SystemVerilog test shell. A VHDL design is
first synthesised by GHDL into a Verilog netlist (flow/vhdl.py ``to_verilog``) with the bench's parameters fixed (the
top's generics), then ``benchmark/tools/run_task.py``'s ``run`` scores that netlist exactly as it scores a
SystemVerilog design: same bench, same model, same shell, same parameters. Any *.sv/*.v already in the directory is
scored with it. A bench with a SystemVerilog wrapper (bench.yaml ``wrapper``) has the design top inside the wrapper:
the design's generics then keep their VHDL defaults unless ``--generics`` gives them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow import vhdl  # noqa: E402


def netlist_dir(task: Path, rtl: Path, out: Path, generics: dict | None = None) -> Path:
    """``out`` holding the GHDL netlist of ``rtl``'s VHDL plus its other HDL files; the directory to score."""
    sys.path.insert(0, str(ROOT / "benchmark" / "tools"))
    import run_task
    b = run_task.load_bench(task)
    vh = sorted(p for p in rtl.iterdir() if vhdl.is_vhdl(p))
    if not vh:
        raise SystemExit(f"{rtl}: no VHDL files")
    top = vhdl.top_entity(vh, b["toplevel"])
    gens = generics if generics is not None else (dict(b.get("parameters") or {}) if top.lower() == b["toplevel"].lower() else {})
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    net = vhdl.to_verilog(vh, top, gens, out / "_ghdl")
    shutil.copy(net, out / f"{top.lower()}_ghdl.v")
    shutil.rmtree(out / "_ghdl", ignore_errors=True)
    for p in rtl.iterdir():
        if p.suffix in (".sv", ".v"):
            shutil.copy(p, out / p.name)
    return out


def score(task: Path, rtl: Path, sim: str | None = None, seed: int = 1, tag: str = "vhdl",
          build_root: Path | None = None, generics: dict | None = None) -> dict:
    sys.path.insert(0, str(ROOT / "benchmark" / "tools"))
    import run_task
    task, rtl = task.resolve(), rtl.resolve()
    work = (build_root or ROOT / "build" / "vhdl_score") / f"{task.name}__{tag}"
    try:
        nd = netlist_dir(task, rtl, work / "rtl", generics)
    except (RuntimeError, SystemExit) as e:
        return {"task": task.name, "tag": tag, "sim": sim or "icarus", "seed": seed, "rtl": str(rtl), "built": False,
                "tests": {}, "pass": False, "error": f"GHDL netlist failed: {e}", "language": "vhdl"}
    r = run_task.run(task, nd, sim, seed, tag, build_root=work / "sim")
    r.update({"rtl": _rel(rtl), "language": "vhdl", "netlist": sorted(p.name for p in nd.iterdir()),
              "ghdl": vhdl.ghdl_version()})
    if r.get("log"):
        r["log"] = _rel(Path(r["log"]))
    return r


def _rel(p: Path) -> str:
    """A path relative to the repo when it is inside it (results files carry no machine paths)."""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task", type=Path)
    ap.add_argument("--rtl", type=Path, required=True)
    ap.add_argument("--sim", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default="vhdl")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    r = score(a.task, a.rtl, a.sim, a.seed, a.tag)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    for t, ok in r["tests"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {t}")
    print(f"{r['task']} [{r['tag']}, {r['sim']}, VHDL via GHDL netlist]: {'PASS' if r['pass'] else 'FAIL'}"
          f" ({sum(r['tests'].values())}/{len(r['tests'])} tests){'; ' + r['error'] if 'error' in r else ''}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
