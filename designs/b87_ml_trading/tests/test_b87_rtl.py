"""Every hand-RTL arm against its Python integer model over the whole test split (Icarus Verilog), with the latency
of every sample. With B87_RECORD=<dir>, writes <dir>/determinism.json.

    B87_RECORD=results/b87 python -m pytest -q designs/b87_ml_trading/tests/test_b87_rtl.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import gen_rtl as G
from designs.b87_ml_trading.model import lobsim as L

HERE = Path(__file__).resolve().parents[1]
MODELS = G.MODELS
ARMS = {"imb_rule": "imbalance_rule", "gbt_comb": "gbt", "gbt_pipe": "gbt", "mlp_hand": "mlp", "lutnet": "lutnet",
        "mlp_hls4ml_wrap": "mlp"}
HLS_V = G.ROOT / "build" / "b87" / "hls4ml_rtl"     # Vitis HLS output (not committed; see rtl/mlp_hls4ml_wrap.sv)
PRED = {"imbalance_rule": A.imbalance_rule_predict, "gbt": A.gbt_predict_int, "mlp": A.mlp_predict_int, "lutnet": A.lut_predict_int}
_results: dict = {}


def pack(X: np.ndarray, y: np.ndarray) -> list[str]:
    w = np.zeros(len(X), dtype=object)
    for j in range(7):
        w = w + (X[:, j].astype(object) << G.FLO[j])
    w = w + (y.astype(object) << 38)
    return [f"{int(v):010x}" for v in w]


@pytest.fixture(scope="module")
def test_split():
    X, _, _ = L.split("test")
    return X


def test_generated_rtl_is_current():
    assert subprocess.run(["python3", "-m", "designs.b87_ml_trading.model.gen_rtl", "--check"],
                          cwd=G.ROOT).returncode == 0


@pytest.mark.parametrize("arm", list(ARMS))
def test_arm_matches_model_and_latency_is_fixed(arm, test_split, tmp_path):
    extra = []
    if arm == "mlp_hls4ml_wrap":
        if not HLS_V.exists():
            pytest.skip("no Vitis HLS output in build/b87/hls4ml_rtl (needs the hls4ml_arm --synth step)")
        extra = sorted(str(p) for p in HLS_V.glob("*.v"))
    q = json.loads((MODELS / f"{ARMS[arm]}.json").read_text())
    X = test_split
    exp = PRED[ARMS[arm]](q, X)
    (tmp_path / "v.hex").write_text("\n".join(pack(X, exp)) + "\n")
    src = HERE / "rtl" / ("mlp_hls4ml_wrap.sv" if extra else f"gen/{arm}.sv")
    lat = int(re.search(r"localparam int LATENCY = (\d+);", src.read_text()).group(1))
    subprocess.run(["iverilog", "-g2012", f"-DARM={arm}", "-o", str(tmp_path / "sim"), str(HERE / "tb" / "tb_arm.sv"),
                    str(src)] + extra, check=True)
    subprocess.run(["vvp", "-n", str(tmp_path / "sim"), f"+VEC={tmp_path / 'v.hex'}", f"+N={len(X)}",
                    f"+OUT={tmp_path / 's.txt'}"], check=True, capture_output=True)
    s = dict(zip(*[iter((tmp_path / "s.txt").read_text().split())] * 2))
    r = {k: int(v) for k, v in s.items()}
    r["latency_param"] = lat
    r["class_counts"] = np.bincount(exp, minlength=3).tolist()
    _results[arm] = r
    assert r["n"] == len(X) and r["out"] == len(X), r
    assert r["mismatches"] == 0, r
    assert r["latency_min"] == r["latency_max"] == lat, r


def teardown_module(_m):
    out = os.environ.get("B87_RECORD")
    if out and _results:
        p = Path(out) / "determinism.json"
        prev = json.loads(p.read_text()) if p.exists() else {"arms": {}}
        prev["arms"].update(_results)
        prev["what"] = ("each arm's RTL (Icarus Verilog) against its Python integer model over every test-split sample; "
                        "latency = clocks from in_v to out_v of each sample; first half back to back, second half with "
                        "pseudo-random gaps of 0-3 clocks")
        p.write_text(json.dumps(prev, indent=1))
