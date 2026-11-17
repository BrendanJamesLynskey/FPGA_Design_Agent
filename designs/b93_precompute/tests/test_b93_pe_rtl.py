"""The partial-evaluation blocks against the 87 / 89 integer models (Icarus Verilog), and Verilator -Wall lint.

Each block gets the early features at e_v and the late feature (packed bits 35:28, zeroed in e_f) FILL clocks or more
later; the class must equal the model's class on the full vector, on the whole 87 test split, on 20,000 random packed
vectors and on a sweep that crosses every value of the late feature with random early features; out_v must follow l_v
by exactly 1 clock. B93_RECORD=<dir> writes <dir>/block_equivalence.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import lobsim as L
from designs.b89_lutnet_gen.lutgen import model as M89
from designs.b89_lutnet_gen.lutgen import sim as S89
from designs.b93_precompute.model import gen_rtl as G

HERE = Path(__file__).resolve().parents[1]
TB = HERE / "tb" / "tb_pe.sv"
GEN = HERE / "rtl" / "gen"
GBT = json.loads((G.G87.MODELS / "gbt.json").read_text())
LG = json.loads(G.LG_MODEL.read_text())
BLOCKS = {"gbt_pe": ("gbt", 1), "gbt_pe2": ("gbt", 2), "lgs_pe": ("lg", 1), "lgs_pe2": ("lg", 2)}
_results: dict = {}


def predict(kind: str, X: np.ndarray) -> np.ndarray:
    return A.gbt_predict_int(GBT, X) if kind == "gbt" else M89.twin_predict(LG, X)


def sweep(n_per: int, seed: int) -> np.ndarray:
    """Every value of the late feature against random other features."""
    rng = np.random.default_rng(seed)
    X = S89.random_features(256 * n_per, seed)
    X[:, G.LATE] = np.tile(np.arange(256), n_per)
    return X


@pytest.fixture(scope="module")
def vectors():
    Xt, _, _ = L.split("test")
    return {"test_split": Xt, "random_20000": S89.random_features(20000, 9301), "late_sweep": sweep(40, 9302)}


def test_generated_rtl_is_current():
    assert subprocess.run(["python3", "-m", "designs.b93_precompute.model.gen_rtl", "--check"],
                          cwd=G.ROOT).returncode == 0


@pytest.mark.parametrize("name", list(BLOCKS))
def test_block_equals_model(name, vectors, tmp_path):
    kind, fill = BLOCKS[name]
    rec = {}
    for tag, X in vectors.items():
        exp = predict(kind, X)
        (tmp_path / "v.hex").write_text("\n".join(S89.pack(X, exp)) + "\n")
        subprocess.run(["iverilog", "-g2012", f"-DDUT={name}", "-o", str(tmp_path / "sim"), str(TB), str(GEN / f"{name}.sv")],
                       check=True)
        subprocess.run(["vvp", "-n", str(tmp_path / "sim"), f"+VEC={tmp_path / 'v.hex'}", f"+N={len(X)}",
                        f"+OUT={tmp_path / 's.txt'}"], check=True, capture_output=True)
        s = dict(zip(*[iter((tmp_path / "s.txt").read_text().split())] * 2))
        r = {k: int(v) for k, v in s.items()}
        r["class_counts"] = np.bincount(exp, minlength=3).tolist()
        rec[tag] = r
        assert r["n"] == len(X) == r["out"], (tag, r)
        assert r["mismatches"] == 0 and r["latency_bad"] == 0, (tag, r)
    _results[name] = rec


@pytest.mark.skipif(shutil.which("verilator") is None, reason="no verilator (CI installs it)")
@pytest.mark.parametrize("name", list(BLOCKS))
def test_verilator_wall_clean(name):
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module", name, str(GEN / f"{name}.sv")],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr[:2000]


def teardown_module(_m):
    out = os.environ.get("B93_RECORD")
    if out and _results:
        p = Path(out) / "block_equivalence.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        prev = json.loads(p.read_text()) if p.exists() else {"blocks": {}}
        prev["blocks"].update(_results)
        prev["what"] = ("each block's RTL (Icarus Verilog) against the Python integer model; early features at e_v, the late "
                        "feature FILL..FILL+3 clocks later; out_v exactly 1 clock after l_v for every sample; sets: the 87 test "
                        "split, 20,000 random packed vectors, every late value (0..255) x 40 random early vectors")
        p.write_text(json.dumps(prev, indent=1))
