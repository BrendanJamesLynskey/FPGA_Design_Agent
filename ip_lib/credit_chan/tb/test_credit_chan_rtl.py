"""ip_lib/credit_chan under cocotb + Icarus against model.py clock by clock; the declared latency, round trip, throughput
and capacity against the measured ones; the elaboration guards. NET_RTL_CREDIT_CHAN points the tests at a seeded-fault copy."""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim
from ip_lib.credit_chan import model as M

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "credit_chan" / "tb"
OUT = os.environ.get("CREDIT_RESULTS")

# (W, CREDITS, LF, LB): below, at and above the round trip LF + LB + 2, with every zero-stage corner
POINTS = [(16, 1, 0, 0), (16, 2, 0, 0), (16, 1, 1, 1), (16, 2, 1, 1), (16, 3, 1, 1), (16, 4, 1, 1), (16, 8, 1, 1),
          (16, 3, 2, 2), (16, 6, 2, 2), (16, 9, 2, 2), (8, 5, 3, 0), (8, 5, 0, 3), (8, 12, 4, 4), (8, 16, 4, 4),
          (1, 4, 1, 1), (64, 5, 2, 1), (8, 7, 1, 2), (8, 1, 8, 8), (8, 18, 8, 8)]


def _run(p, tests, extra=None, sb=(0, 0, 0)):
    w, c, lf, lb = p
    env = {"PYTHONPATH": str(ROOT)}
    env.update(extra or {})
    tl, tk, tu = sb
    srcs = sim.rtl("credit_chan") + [TB / "credit_axis_tb.sv", ROOT / "axi_tx" / "rtl" / "axis_rules.sv"]
    cocotb_run.run(f"credit_w{w}_c{c}_f{lf}_b{lb}_{tl}{tk}{tu}", "credit_axis_tb", srcs, "credit_cocotb", TB,
                   parameters={"W": w, "CREDITS": c, "LF": lf, "LB": lb, "TLAST_EN": tl, "TKEEP_EN": tk, "TUSER_W": tu},
                   testcase=tests, extra_env=env)


SIDEBAND = [(32, 6, 2, 2), (16, 3, 1, 1), (8, 5, 0, 0)]                # points rerun with tlast, tkeep (where W is a byte multiple) and tuser


@pytest.mark.parametrize("p", POINTS)
def test_random_traffic(p):
    _run(p, "random_traffic")


@pytest.mark.parametrize("p", SIDEBAND)
def test_random_traffic_sideband(p):
    _run(p, "random_traffic", sb=(1, 1, 5))


@pytest.mark.parametrize("p", POINTS)
def test_measure_declared(p, tmp_path):
    out = tmp_path / "m.jsonl"
    _run(p, "measure", {"CREDIT_OUT": str(out)})
    r = json.loads(out.read_text().splitlines()[-1])
    if OUT:
        with open(OUT, "a") as f:
            f.write(json.dumps(r) + "\n")
    _, c, lf, lb = p
    assert r["latency"] == M.latency(c, lf, lb)
    sends, window = r["throughput_accepted_per_clock"] * r["window_clocks"], r["window_clocks"]
    assert abs(sends - float(M.throughput(c, lf, lb)) * window) <= 1.0     # a whole number of beats in a window that need not hold a whole number of periods
    assert r["send_gap_after_credits"] == max(M.rtt(c, lf, lb), c)
    assert r["capacity_beats"] == M.capacity(c, lf, lb)


@pytest.mark.parametrize("params", [{"W": 0}, {"W": 1025}, {"CREDITS": 0}, {"CREDITS": 1025}, {"LF": -1}, {"LF": 9},
                                    {"LB": -1}, {"LB": 9}, {"TLAST_EN": 2}, {"TKEEP_EN": 1, "W": 12}, {"TUSER_W": 65}])
def test_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("credit_chan"), "credit_chan", params)
    assert bad, out
