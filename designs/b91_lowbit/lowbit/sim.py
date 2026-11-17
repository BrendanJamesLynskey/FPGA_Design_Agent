"""Run a generated network in Icarus Verilog against its twin with the brief 87 arm test bench (tb_arm.sv): every
vector's class is checked and the in_v -> out_v latency of every sample is recorded (first half back to back, second
half with pseudo-random gaps). The packing is the brief 89 one (the 87 feature packing)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from designs.b89_lutnet_gen.lutgen import sim as S89
from . import model as M

FBITS, TB, pack, random_features = S89.FBITS, S89.TB, S89.pack, S89.random_features


def run(m: dict, sv: Path, name: str, X: np.ndarray, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    exp = M.twin_predict(m, X)
    (work / "v.hex").write_text("\n".join(pack(X, exp)) + "\n")
    lat = int(re.search(r"localparam int LATENCY = (\d+);", sv.read_text()).group(1))
    subprocess.run(["iverilog", "-g2012", f"-DARM={name}", "-o", str(work / "sim"), str(TB), str(sv)], check=True)
    subprocess.run(["vvp", "-n", str(work / "sim"), f"+VEC={work / 'v.hex'}", f"+N={len(X)}",
                    f"+OUT={work / 's.txt'}"], check=True, capture_output=True)
    s = dict(zip(*[iter((work / "s.txt").read_text().split())] * 2))
    r = {k: int(v) for k, v in s.items()}
    r["latency_param"] = lat
    r["class_counts"] = np.bincount(exp, minlength=3).tolist()
    r["ok"] = r["n"] == len(X) == r["out"] and r["mismatches"] == 0 and r["latency_min"] == r["latency_max"] == lat
    return r
