"""partition/rtl/part_sys.sv under cocotb + Icarus: latency, throughput and data of the synthetic system at every handshake type
and boundary depth, against the figures the pipe_reg and credit_chan models declare. PART_SIM_RESULTS names a JSON-lines file the
measurements are appended to."""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

import pytest

from flow import cocotb_run
from ip_lib.pipe_reg import model as PM

ROOT = Path(__file__).resolve().parents[2]
NM, W, D = 4, 64, 2
SRCS = sorted((ROOT / "partition" / "rtl").glob("*.sv")) + sorted((ROOT / "ip_lib" / "pipe_reg" / "rtl").glob("*.sv")) + [ROOT / "ip_lib" / "credit_chan" / "rtl" / "credit_chan.sv"]
HS_NAMES = {0: "FWD", 1: "SKID", 2: "FULL", 3: "HALF", 4: "COMB", 5: "PLAIN", 6: "CREDIT"}
POINTS = [(0, 0)] + [(hs, st) for hs in range(7) for st in (1, 2, 3)]


def run(hs, st, out):
    cocotb_run.run(f"part_hs{hs}_st{st}", "part_sys", SRCS, "part_cocotb", ROOT / "partition" / "tests",
                   parameters={"W": W, "NM": NM, "D": D, "HS": hs, "STAGES": st, "KEEP": 0}, testcase="measure",
                   extra_env={"PART_OUT": str(out), "PYTHONPATH": str(ROOT)})
    return json.loads(out.read_text().splitlines()[-1])


@pytest.mark.parametrize("hs,st", POINTS)
def test_point(hs, st, tmp_path):
    r = run(hs, st, tmp_path / "o.jsonl")
    if os.environ.get("PART_SIM_RESULTS"):
        with open(os.environ["PART_SIM_RESULTS"], "a") as f:
            f.write(json.dumps(r) + "\n")
    assert r["latency_data_ok"] and r["throughput_data_ok"] and r["bp_data_ok"], r
    assert r["bp_delivered"] == r["bp_accepted"] or r["bp_delivered"] <= r["bp_accepted"]
    nb = NM + 1                                          # boundaries
    if st == 0:
        exp_lat, exp_thr = 0, Fraction(1)
    elif hs <= 4:
        exp_lat, exp_thr = nb * PM.latency(st, hs), PM.throughput(st, hs)
    elif hs == 5:
        exp_lat, exp_thr = nb * st, Fraction(1)
    else:                                                # credit: LF + 1 per boundary; full rate by construction
        exp_lat, exp_thr = nb * (st + 1), Fraction(1)
    assert r["latency_clocks"] == exp_lat, r
    assert abs(r["throughput_beats_per_clock"] - float(exp_thr)) < 0.01, r
