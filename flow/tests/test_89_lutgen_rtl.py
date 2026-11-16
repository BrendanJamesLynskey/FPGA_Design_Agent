"""flow/lutgen.py emit: the pipelining options the brief 89 arms do not use (pipe = N, a registered encoder) against
the twin on random inputs, with a fixed latency; and the width check of --fbits."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from designs.b89_lutnet_gen.lutgen import cli as C
from designs.b89_lutnet_gen.lutgen import sim as S

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("arm,pipe,reg,latency", [("lg_b87", "2", False, 2), ("lg_b87", "1", True, 5),
                                                  ("lg_small", "comb", True, 2)])
def test_emit_options_equal_twin(arm, pipe, reg, latency, tmp_path):
    seed = C.built_seed(arm)
    model = C.RES / "models" / f"{arm}_seed{seed}.json"
    sv = tmp_path / "net.sv"
    subprocess.run([sys.executable, "-m", "flow.lutgen", "emit", "--model", str(model), "--name", "net", "--fbits",
                    *map(str, S.FBITS), "--pipe", pipe, "--out", str(sv)] + (["--reg-encoder"] if reg else []),
                   cwd=ROOT, check=True)
    assert f"localparam int LATENCY = {latency};" in sv.read_text()
    r = S.run(C.model_of(arm, seed), sv, "net", S.random_features(5000, 7), tmp_path / "sim")
    assert r["ok"], r


def test_emit_refuses_wrong_feature_count(tmp_path):
    model = C.RES / "models" / f"lg_small_seed{C.built_seed('lg_small')}.json"
    r = subprocess.run([sys.executable, "-m", "flow.lutgen", "emit", "--model", str(model), "--name", "n", "--fbits",
                        "8", "8", "--out", str(tmp_path / "n.sv")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "--fbits has 2 widths" in r.stderr
