"""Run a generated stateful arm in Icarus Verilog against its stream twin (tb/tb_stream.sv)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from . import stream as S

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "designs" / "b92_history_attention" / "tb" / "tb_stream.sv"


def vectors(streams: list, arm: str, rec: dict) -> tuple[list[str], np.ndarray]:
    """streams: list of (X, PORT) arrays; each is run from the reset state. Returns the hex lines and the expected classes."""
    lines, exp = [], []
    for X, P in streams:
        cls = S.stream_predict(arm, rec, X, P)
        w = S.pack(X, P)
        for i, (a, c) in enumerate(zip(w, cls)):
            lines.append(f"{(int(a) | (int(c) << 51) | ((1 if i == 0 else 0) << 53)):014x}")
        exp.append(cls)
    return lines, np.concatenate(exp)


def run(arm: str, rec: dict, files: list[Path], name: str, streams: list, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    lines, exp = vectors(streams, arm, rec)
    (work / "v.hex").write_text("\n".join(lines) + "\n")
    lat = int(re.search(r"localparam int LATENCY = (\d+);", [f for f in files if f.stem == name][0].read_text()).group(1))
    subprocess.run(["iverilog", "-g2012", f"-DARM={name}", "-o", str(work / "sim"), str(TB)] + [str(f) for f in files], check=True)
    subprocess.run(["vvp", "-n", str(work / "sim"), f"+VEC={work / 'v.hex'}", f"+N={len(lines)}", f"+OUT={work / 's.txt'}"],
                   check=True, capture_output=True)
    s = dict(zip(*[iter((work / "s.txt").read_text().split())] * 2))
    r = {k: int(v) for k, v in s.items()}
    r["latency_param"] = lat
    r["class_counts"] = np.bincount(exp, minlength=3).tolist()
    r["ok"] = r["n"] == len(lines) == r["out"] and r["mismatches"] == 0 and r["latency_min"] == r["latency_max"] == lat
    return r
