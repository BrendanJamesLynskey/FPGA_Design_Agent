"""Brief 91: every generated network in Icarus Verilog against its twin over the whole brief 87 test split and over
random packed inputs, with the latency of every sample; Verilator -Wall lint; generated files current; the exported
integers reproduce the recorded validation accuracy; the binary networks' XNOR form equals the integer form; every
accumulator stays inside its computed bound on the test split. With B91_RECORD=<dir>, writes <dir>/determinism.json.

    B91_RECORD=results/b91 python -m pytest -q designs/b91_lowbit/tests/test_b91_rtl.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from designs.b89_lutnet_gen.lutgen import data as Dm
from designs.b91_lowbit.lowbit import cli as C
from designs.b91_lowbit.lowbit import model as M
from designs.b91_lowbit.lowbit import sim as S

N_RANDOM = 20000
_results: dict = {}


def modules():
    return [(n["id"], p) for n in C.frozen()["networks"] for p in n["pipes"]]


def net(i):
    return next(n for n in C.frozen()["networks"] if n["id"] == i)


@pytest.fixture(scope="module")
def test_split():
    return Dm.load(("test",))["test"][0]


def test_generated_rtl_is_current():
    assert C.rtl(check=True) == 0


def test_exported_integers_reproduce_recorded_validation_accuracy():
    Xv, yv, _ = Dm.load(("val",))["val"]
    for n in C.frozen()["networks"]:
        for s in C.SEEDS:
            m = C.model_of(n, s)
            assert round(float((M.twin_predict(m, Xv) == yv).mean()), 4) == m["val_accuracy"], (n["id"], s)


@pytest.mark.parametrize("nid,pipe", modules())
@pytest.mark.parametrize("data", ["test_split", "random"])
def test_rtl_equals_twin_and_latency_is_fixed(nid, pipe, data, test_split, tmp_path):
    X = test_split if data == "test_split" else S.random_features(N_RANDOM, seed=91)
    name = C.module_name(net(nid), pipe)
    r = S.run(C.model_of(net(nid)), C.GEN / f"{name}.sv", name, X, tmp_path)
    _results[f"{name}/{data}"] = r
    assert r["ok"], r


@pytest.mark.parametrize("nid", [n["id"] for n in C.frozen()["networks"]])
def test_accumulators_stay_inside_computed_bounds(nid, test_split):
    """The interval-arithmetic widths in the RTL are never exceeded by real inputs (also on random inputs)."""
    m = C.model_of(net(nid))
    bnd = M.bounds(m)
    for X in (test_split, S.random_features(5000, seed=3)):
        x = M.encode_input(m["input"], X)
        for L, b in zip(m["layers"], bnd):
            W = np.asarray(L["W"], dtype=np.int64).reshape(L["n"], L["n_in"])
            z = (x @ W.T) * (1 if L["kind"] == "hidden" else (1 << np.asarray(L["k"]))) + np.asarray(L["B"])
            lo = np.array([a for a, _ in b["acc"]])
            hi = np.array([c for _, c in b["acc"]])
            assert (z >= lo).all() and (z <= hi).all()
            x = np.clip(z >> np.asarray(L["sh"]), 0, L["amax"]) if L["kind"] == "hidden" else z


@pytest.mark.parametrize("nid", [n["id"] for n in C.frozen()["networks"] if n["format"].startswith("binary")])
def test_binary_xnor_popcount_form_equals_integer_form(nid, test_split):
    m = C.model_of(net(nid))
    assert (M.twin_predict_xnor(m, test_split) == M.twin_predict(m, test_split)).all()


@pytest.mark.skipif(shutil.which("verilator") is None, reason="no verilator (CI installs it)")
@pytest.mark.parametrize("nid,pipe", modules())
def test_generated_rtl_lint_clean(nid, pipe):
    name = C.module_name(net(nid), pipe)
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module", name, str(C.GEN / f"{name}.sv")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


def teardown_module(_m):
    out = os.environ.get("B91_RECORD")
    if out and _results:
        p = Path(out) / "determinism.json"
        old = json.loads(p.read_text()) if p.exists() else {}
        p.write_text(json.dumps(old | _results, indent=1, sort_keys=True))
