"""Brief 89: every generated network (and the TreeLUT reference) in Icarus Verilog against its twin, over the whole
brief 87 test split and over random packed inputs, with the latency of every sample; Verilator -Wall lint of the
generated modules; generated files current. With B89_RECORD=<dir>, writes <dir>/determinism.json.

    B89_RECORD=results/b89 python -m pytest -q designs/b89_lutnet_gen/tests/test_b89_rtl.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from designs.b89_lutnet_gen.lutgen import cli as C
from designs.b89_lutnet_gen.lutgen import data as Dm
from designs.b89_lutnet_gen.lutgen import model as M
from designs.b89_lutnet_gen.lutgen import sim as S

TL = C.GEN.parent / "treelut"
N_RANDOM = 20000
_results: dict = {}


def modules():
    m = [(arm, pipe) for arm, a in C.frozen()["arms"].items() for pipe in a["pipes"]]
    return m + [(f.name.replace("_seed0.json", ""), "comb") for f in sorted((C.RES / "models").glob("fanin*_seed0.json"))]


def model(arm):
    return C.model_of(arm) if arm in C.frozen()["arms"] else C.model_of(arm, 0)


@pytest.fixture(scope="module")
def test_split():
    return Dm.load(("test",))["test"][0]


def test_generated_rtl_is_current():
    assert C.rtl(check=True) == 0


def test_twin_tables_reproduce_recorded_validation_accuracy():
    """The committed tables give the validation accuracy recorded at training time (the model file is self-consistent)."""
    Xv, yv, _ = Dm.load(("val",))["val"]
    for arm in C.frozen()["arms"]:
        for s in C.SEEDS:
            m = C.model_of(arm, s)
            assert round(float((M.twin_predict(m, Xv) == yv).mean()), 4) == m["val_accuracy"], (arm, s)


@pytest.mark.parametrize("arm,pipe", modules())
@pytest.mark.parametrize("data", ["test_split", "random"])
def test_rtl_equals_twin_and_latency_is_fixed(arm, pipe, data, test_split, tmp_path):
    X = test_split if data == "test_split" else S.random_features(N_RANDOM, seed=89)
    name = f"{arm}_{pipe}"
    r = S.run(model(arm), C.GEN / f"{name}.sv", name, X, tmp_path)
    _results[f"{name}/{data}"] = r
    assert r["ok"], r


def test_treelut_rtl_equals_treelut_predictions(test_split, tmp_path):
    """TreeLUT's Verilog against TreeLUT's own integer predictions (seed 0) on the whole test split."""
    exp = np.load(C.RES / "treelut" / "test_predictions.npz")["seed0"].astype(np.int64)
    X = test_split
    (tmp_path / "v.hex").write_text("\n".join(S.pack(X, exp)) + "\n")
    src = sorted(str(p) for p in TL.glob("*.v")) + [str(TL / "treelut_arm.sv")]
    subprocess.run(["iverilog", "-g2012", "-DARM=treelut_arm", "-o", str(tmp_path / "sim"), str(S.TB)] + src, check=True)
    subprocess.run(["vvp", "-n", str(tmp_path / "sim"), f"+VEC={tmp_path / 'v.hex'}", f"+N={len(X)}",
                    f"+OUT={tmp_path / 's.txt'}"], check=True, capture_output=True)
    s = dict(zip(*[iter((tmp_path / "s.txt").read_text().split())] * 2))
    r = {k: int(v) for k, v in s.items()}
    _results["treelut_arm/test_split"] = r
    assert r["n"] == r["out"] == len(X) and r["mismatches"] == 0 and r["latency_min"] == r["latency_max"] == 3, r


@pytest.mark.skipif(shutil.which("verilator") is None, reason="no verilator (CI installs it)")
@pytest.mark.parametrize("arm,pipe", modules())
def test_generated_rtl_lint_clean(arm, pipe):
    name = f"{arm}_{pipe}"
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module", name, str(C.GEN / f"{name}.sv")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


def teardown_module(_m):
    out = os.environ.get("B89_RECORD")
    if out and _results:
        p = Path(out) / "determinism.json"
        prev = json.loads(p.read_text()) if p.exists() else {}
        prev.update(_results)
        p.write_text(json.dumps(dict(sorted(prev.items())), indent=1))
