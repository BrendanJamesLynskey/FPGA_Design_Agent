"""Run a generated network in Icarus Verilog against its twin, with the brief 87 arm test bench (tb_arm.sv): every
vector's class is checked and the in_v -> out_v latency of every sample is recorded (first half back to back, second
half with pseudo-random gaps)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from . import model as M

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "designs" / "b87_ml_trading" / "tb" / "tb_arm.sv"
FBITS = [8, 8, 4, 3, 5, 8, 2]          # the 87 feature packing (designs/b87_ml_trading/model/gen_rtl.py)
FLO = [sum(FBITS[:i]) for i in range(7)]


def pack(X: np.ndarray, cls: np.ndarray) -> list[str]:
    w = np.zeros(len(X), dtype=object)
    for j in range(7):
        w = w + (X[:, j].astype(object) << FLO[j])
    w = w + (cls.astype(object) << 38)
    return [f"{int(v):010x}" for v in w]


def random_features(n: int, seed: int) -> np.ndarray:
    """Uniform over every legal packed value of each field (also values the training data never had)."""
    rng = np.random.default_rng(seed)
    return np.stack([rng.integers(0, 1 << b, size=n) for b in FBITS], axis=1).astype(np.int64)


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
