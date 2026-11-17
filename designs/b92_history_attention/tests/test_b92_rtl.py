"""Brief 92 stage 3 checks: the generated stateful arms equal their stream twin (Icarus), on every test event of the ten test
sessions (each run from the reset state) and on random and extreme input streams, with a fixed latency; the stream twin equals the
stage 2 scoring path; generated files are current; Verilator -Wall is clean.

    B92_RECORD=results/b92 pytest designs/b92_history_attention/tests/test_b92_rtl.py     # also writes results/b92/determinism.json
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from designs.b92_history_attention.hist import cli as C
from designs.b92_history_attention.hist import sim as SM
from designs.b92_history_attention.hist import stage2 as S2
from designs.b92_history_attention.hist import stream as S
from designs.b92_history_attention.hist import tokens as TK

pytestmark = pytest.mark.skipif(shutil.which("iverilog") is None or not (S2.RES / "stage2_frozen.json").exists(),
                                reason="needs iverilog and the stage 2 records")
ARMS = ["a1_decay", "a4_lut", "a2_win8", "a2_win16", "a3_top1", "a3_relu"]
WORK = C.ROOT / "build" / "b92" / "sim"


def test_session_streams():
    te = TK.Split("hawkes", "test")
    return [(s["X"], S.port_of_session(s["X"], s["T"])) for s in te.sess]


def extreme_streams():
    n = 3000
    hi = np.array([255, 255, 15, 7, 16, 255, 2]), np.array([2, 16, 62])
    lo = np.zeros(7, dtype=np.int64), np.zeros(3, dtype=np.int64)
    out = []
    for X0, P0 in (hi, lo):
        out.append((np.tile(X0, (n, 1)).astype(np.int64), np.tile(P0, (n, 1)).astype(np.int64)))
    alt = [(hi, lo)[(i // 7) % 2] for i in range(n)]
    out.append((np.stack([a[0] for a in alt]).astype(np.int64), np.stack([a[1] for a in alt]).astype(np.int64)))
    return out


def random_streams():
    return [S.random_stream(2000, 9000 + i) for i in range(10)]


def test_stream_twin_equals_the_scoring_path():
    te = S2.splits(("test",))["test"]
    for arm in ["a1_decay", "a2_win8", "a2_win16", "a3_top1", "a3_relu", "a4_lut"]:
        r = C.rec_of(arm)
        a = S2.predict(r, te)
        parts = []
        for s in te.sess:
            p = S.stream_predict(arm, r, s["X"], S.port_of_session(s["X"], s["T"]))
            parts.append(p[s["keep"]])
        assert np.array_equal(np.concatenate(parts), a), arm


def test_generated_files_current():
    assert C.main(["rtl", "--check"]) == 0


def _files(arm):
    GEN = C.GEN
    return [GEN / f"b92_{arm}_net.sv", GEN / f"b92_{arm}.sv"]


@pytest.mark.parametrize("arm", ARMS)
def test_rtl_equals_twin(arm):
    r = C.rec_of(arm)
    name = f"b92_{arm}"
    res = {}
    for label, streams in (("test_sessions", test_session_streams()), ("random", random_streams()), ("extreme", extreme_streams())):
        out = SM.run(arm, r, _files(arm), name, streams, WORK / arm / label)
        assert out["ok"], (arm, label, out)
        res[label] = out
    rec = os.environ.get("B92_RECORD")
    if rec:
        p = Path(rec) / "determinism.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        d[arm] = res
        p.write_text(json.dumps(d, indent=1))


@pytest.mark.skipif(shutil.which("verilator") is None, reason="no verilator (CI installs it)")
@pytest.mark.parametrize("arm", ["ref_current"] + ARMS)
def test_verilator_lint(arm):
    fs = _files(arm) if arm != "ref_current" else [C.GEN / "b92_ref_current.sv"]
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module", f"b92_{arm}"] + [str(f) for f in fs],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
