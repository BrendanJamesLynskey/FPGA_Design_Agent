"""flow/lowbit.py: emit and predict agree with the generator (the twin, the RTL on random inputs), and the width check
of --fbits."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

from designs.b91_lowbit.lowbit import cli as C
from designs.b91_lowbit.lowbit import sim as S

ROOT = Path(__file__).resolve().parents[2]


def _net():
    return next(n for n in C.frozen()["networks"] if n["id"] == "log4_h16x8_a4")


def _model_file():
    n = _net()
    return C.path_of(n["format"], n["shape"], n["act_bits"], n["built_seed"])


def test_emit_layer_pipe_equals_twin(tmp_path):
    sv = tmp_path / "net.sv"
    subprocess.run([sys.executable, "-m", "flow.lowbit", "emit", "--model", str(_model_file()), "--name", "net", "--fbits",
                    *map(str, S.FBITS), "--pipe", "layer", "--out", str(sv)], cwd=ROOT, check=True)
    assert "localparam int LATENCY = 4;" in sv.read_text()
    r = S.run(C.model_of(_net()), sv, "net", S.random_features(5000, 7), tmp_path / "sim")
    assert r["ok"], r


def test_predict_prints_the_twin_classes(tmp_path):
    X = S.random_features(50, 5)
    np.savez(tmp_path / "d.npz", X_val=X)
    out = subprocess.run([sys.executable, "-m", "flow.lowbit", "predict", "--model", str(_model_file()), "--data",
                          str(tmp_path / "d.npz")], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    from designs.b91_lowbit.lowbit import model as M
    assert [int(c) for c in out] == M.twin_predict(C.model_of(_net()), X).tolist()


def test_emit_refuses_wrong_feature_count(tmp_path):
    r = subprocess.run([sys.executable, "-m", "flow.lowbit", "emit", "--model", str(_model_file()), "--name", "n", "--fbits",
                        "8", "8", "--out", str(tmp_path / "n.sv")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "--fbits has 2 widths" in r.stderr
