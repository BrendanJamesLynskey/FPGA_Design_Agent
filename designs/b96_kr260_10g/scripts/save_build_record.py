#!/usr/bin/env python3
"""Copies a build's records into results/b96/build_<x>/ with the per-stage report bodies trimmed out of gates.json (13 MB of log text).
    python3 designs/b96_kr260_10g/scripts/save_build_record.py <build dir> <a|b>"""
import json
import shutil
import sys
from pathlib import Path

src, tag = Path(sys.argv[1]), sys.argv[2]
dst = Path(__file__).resolve().parents[3] / "results" / "b96" / f"build_{tag}"
dst.mkdir(parents=True, exist_ok=True)
g = json.loads((src / "gates.json").read_text())
g["stages"] = {k: {kk: (vv if len(json.dumps(vv)) < 2000 else f"<trimmed: {len(json.dumps(vv))} bytes>") for kk, vv in v.items()} if isinstance(v, dict) else "<trimmed>"
               for k, v in g["stages"].items()}
g["note"] = "stages trimmed for the repository (per-stage report bodies removed); every other field is as flow/gates.py wrote it"
(dst / "gates.json").write_text(json.dumps(g, indent=1))
for f in ("run.json", "stages.txt"):
    shutil.copy(src / f, dst / f)
print("saved", dst)
