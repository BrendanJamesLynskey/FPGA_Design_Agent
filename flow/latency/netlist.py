"""Read a post-route checkpoint for the registers of a design's latency stages (brief 97). Runs Vivado: the caller holds a heavy slot
(`_handoff/take_heavy_slot.sh`), as for any Vivado run; this module never takes one."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from flow.latency.model import ROOT, LatencyError, load_stages

VIVADO = "/opt/Xilinx/2026.1/Vivado/bin/vivado"
TCL = Path(__file__).with_name("netlist_slack.tcl")


def stage_tsv(st: dict[str, Any]) -> str:
    lines = []
    for p in st["paths"].values():
        for s in p["stages"]:
            if s.get("registers"):
                lines.append("\t".join([s["id"], *s["registers"]]))
    return "\n".join(lines) + "\n"


def parse_out(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) < 5:
            continue
        num = lambda x: None if x == "-" else float(x)       # noqa: E731
        out[f[0]] = {"cells": int(f[1]), "clock": None if f[2] == "-" else f[2], "setup_slack_ns": num(f[3]), "hold_slack_ns": num(f[4])}
    return out


def run(design: Path, dcp: Path, out_json: Path, scope_gb: int = 6, timeout: int = 1800) -> dict[str, Any]:
    st = load_stages(design)
    work = ROOT / "build" / "latency"
    work.mkdir(parents=True, exist_ok=True)
    tsv, raw = work / "stages.tsv", work / "slack.tsv"
    tsv.write_text(stage_tsv(st))
    if raw.exists():
        raw.unlink()
    cmd = ["systemd-run", "--user", "--scope", "-q", f"-p", f"MemoryMax={scope_gb}G", "nice", "-n", "15", VIVADO, "-mode", "batch",
           "-nojournal", "-nolog", "-source", str(TCL), "-tclargs", str(dcp), str(tsv), str(raw)]
    p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
    if not raw.is_file():
        raise LatencyError("netlist read failed:\n" + (p.stdout + p.stderr)[-1500:])
    res = {"schema": "fda.latency_slack/1", "source": str(dcp), "stages": parse_out(raw.read_text())}
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    return res
