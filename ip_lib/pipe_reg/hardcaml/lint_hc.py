#!/usr/bin/env python3
"""Lint and reset-rule check of the hand-written SV pipe_reg and the Hardcaml-generated one at the same parameter points
(brief 171): Verilator --lint-only -Wall (warning codes counted) and the check suite's reset source check
(flow/checks/resets.py: yosys-slang elaboration; RST-ASYNC-01 and RST-POL-02).  Run from the repo root:
    python3 ip_lib/pipe_reg/hardcaml/lint_hc.py [--json results/b171/pipe_reg_lint.json]"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from flow.checks import resets as R  # noqa: E402

HERE = Path(__file__).resolve().parent
SV = [ROOT / "ip_lib/pipe_reg/rtl/pipe_reg.sv", ROOT / "ip_lib/pipe_reg/rtl/pipe_reg_slice.sv"]
HC = [HERE / "build/rtl/pipe_reg.sv"]
POINTS = [(32, 2, 1, 1, 1, 4), (16, 2, 4, 0, 0, 0), (16, 5, 3, 0, 0, 0), (16, 2, 2, 0, 0, 0), (16, 5, 0, 0, 0, 0)]
VERILATOR = shutil.which("verilator") or str(Path.home() / ".local/opt/oss-cad-suite/bin/verilator")


def verilator(files, p):
    w, n, m, tl, tk, tu = p
    args = [f"-GW={w}", f"-GN={n}", f"-GMODE={m}", f"-GTLAST_EN={tl}", f"-GTKEEP_EN={tk}", f"-GTUSER_W={tu}"]
    r = subprocess.run([VERILATOR, "--lint-only", "-Wall", "--top-module", "pipe_reg", *args, *map(str, files)], capture_output=True, text=True)
    codes = Counter(re.findall(r"%(?:Warning|Error)-(\w+)", r.stderr))
    return {"rc": r.returncode, "codes": dict(codes)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = {"verilator": VERILATOR, "points": []}
    for p in POINTS:
        row = {"point(W,N,MODE,TLAST,TKEEP,TUSER)": list(p), "sv": verilator(SV, p), "hardcaml": verilator(HC, p)}
        print(p, "SV", row["sv"], "Hardcaml", row["hardcaml"])
        out["points"].append(row)
    cfg = lambda: {"synchronisers": set(R.RECOGNISED), "async_inputs": set()}
    for name, files in (("sv", SV), ("hardcaml", HC)):
        parts: dict = {}
        fs = R.source_findings(ROOT, files, cfg(), top="pipe_reg", parts=parts)
        out[f"reset_source_{name}"] = {"parts": parts, "findings": [f.get("code", str(f)) for f in fs]}
        print(name, "reset source check:", parts, "findings:", len(fs))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
