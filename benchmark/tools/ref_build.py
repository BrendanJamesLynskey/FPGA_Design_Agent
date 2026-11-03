#!/usr/bin/env python3
"""Build a task's reference design through the staged Vivado flow and record its numbers.

    benchmark/tools/ref_build.py <task_dir> [--out DIR] [--stage-only]

Stages ref/rtl and an XDC generated from hidden/spec.yaml (tools/board_xdc.py) into build/bench/<id>/ (gitignored),
then runs flow/run_vivado.sh on it (memory-guarded: refuses below 7 GB available or beside another Vivado; this tool
sets MEM_MAX=5G), the design-standards checker (flow/standards_check.py, all stages), and writes
<out>/<id>__vivado.json: every gate stage, timing, utilisation, power and run cost. Take
_handoff/heavy_slot.lock before running it (the caller's job, not this tool's).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark.tools.board_xdc import make_xdc  # noqa: E402


def architecture(spec: dict, rtl: Path) -> dict:
    """A generated architecture.yaml for the reference build (the standards checker needs one). Its predicted
    resources are deliberately broad: the reference *defines* the resource figures, so the resource gate is not a
    measure here."""
    import re
    mods = sorted({m for f in rtl.glob("*.sv") for m in re.findall(r"^\s*module\s+(\w+)", f.read_text(), re.M)})
    asyn = [p["name"] for p in spec["ports"] if p["dir"] in ("in", "inout") and p["name"] != "CLK100MHZ"]
    shell = "fpga_shell" if spec.get("registers", {}).get("shell") else None
    return {
        "schema": "fpga-design-agent/architecture/v1",
        "blocks": [{"name": m, "function": "reference RTL module"} for m in mods]
        + ([{"name": "fpga_shell", "function": "UART register window (test shell)"}] if shell else []),
        "interfaces": [{"name": "register_window", "between": ["fpga_shell", spec["top"]], "protocol": "simple"}]
        if shell else [],
        "clock_domains": [{"name": "sys", "clock": "CLK100MHZ", "freq_mhz": 100}],
        "reset": {"synchronisers": ["reset_sync"]},
        "crossings": [{"from": "async", "to": "sys", "signal": n,
                       "primitive": "reset_sync" if n == "CPU_RESETN" else "sync2"} for n in asyn],
        "predicted_resources": {"lut": [20, 20000], "ff": [20, 20000], "bram_tile": [0, 8], "dsp": [0, 8]},
    }


def stage(task: Path) -> Path:
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    d = ROOT / "build" / "bench" / task.name
    shutil.rmtree(d, ignore_errors=True)
    (d / "rtl").mkdir(parents=True)
    for f in sorted((task / "ref" / "rtl").iterdir()):
        if f.suffix in (".sv", ".v", ".svh"):
            shutil.copy2(f, d / "rtl" / f.name)
    (d / "design.xdc").write_text(make_xdc(spec))
    (d / "architecture.yaml").write_text(yaml.safe_dump(architecture(spec, d / "rtl"), sort_keys=False))
    rel = d.relative_to(ROOT)
    (d / "build.yaml").write_text(yaml.safe_dump({
        "top": spec["top"], "part": spec.get("part", "xc7a100tcsg324-1"), "board": "nexys_a7_100t",
        "sources": ["shell/rtl/*.sv", f"{rel}/rtl/*.sv"], "constraints": [f"{rel}/design.xdc"], "generics": {}},
        sort_keys=False))
    return d


def summary(task: Path, d: Path, standards: dict | None) -> dict:
    g = json.loads((d / "build" / "base" / "gates.json").read_text())
    run = json.loads((d / "build" / "base" / "run.json").read_text())
    t, u, pw = g.get("timing", {}), g.get("utilization", {}), g.get("power", {})
    return {
        "task": task.name, "pass": g.get("pass"), "first_failed_stage": g.get("first_failed_stage"),
        "stages": {s: {"ran": v.get("ran"), "pass": v.get("pass")} for s, v in g.get("stages", {}).items()},
        "gates": g.get("gates"),
        "timing": {k: t.get(k) for k in ("wns_ns", "tns_ns", "whs_ns", "ths_ns", "wpws_ns", "timing_met")},
        "utilization": {k: u.get(k) for k in ("lut", "ff", "carry4", "lutram", "bram_tile", "dsp", "iob", "bufg")},
        "power": {k: pw.get(k) for k in ("total_w", "dynamic_w", "static_w")},
        "junction_c": (g.get("power_environment") or {}).get("junction_c"),
        "bitstream_bytes": (g.get("bitstream") or {}).get("bytes"),
        "build_stamp": g.get("build_stamp"),
        "standards_pass": None if standards is None else standards.get("pass"),
        "run": {k: run.get(k) for k in ("wall_s", "vivado_peak_rss_mib", "scope_anon_peak_mib", "scope_cap_hits",
                                        "scope_oom_kills", "memory_cap", "vivado_version", "git_commit")},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "benchmark" / "results" / "reference")
    ap.add_argument("--stage-only", action="store_true")
    a = ap.parse_args()
    task = a.task.resolve()
    d = stage(task)
    if a.stage_only:
        print(d)
        return 0
    env = dict(os.environ, MEM_MAX=os.environ.get("MEM_MAX", "5G"))
    rc = subprocess.run([str(ROOT / "flow" / "run_vivado.sh"), str(d), "base"], cwd=ROOT, env=env).returncode
    if not (d / "build" / "base" / "gates.json").exists():
        print(f"{task.name}: no gates.json (runner exit {rc})")
        return 1
    sj = d / "build" / "base" / "standards.json"
    subprocess.run([sys.executable, str(ROOT / "flow" / "standards_check.py"), str(d), "--stage", "all",
                    "--json", str(sj)], cwd=ROOT)
    standards = json.loads(sj.read_text()) if sj.exists() else None
    s = summary(task, d, standards)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{task.name}__vivado.json").write_text(json.dumps(s, indent=2) + "\n")
    print(json.dumps({k: s[k] for k in ("task", "pass", "first_failed_stage", "timing", "utilization", "standards_pass")}))
    return 0 if s["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
