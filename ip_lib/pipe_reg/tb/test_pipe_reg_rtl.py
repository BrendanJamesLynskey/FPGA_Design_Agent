"""ip_lib/pipe_reg under cocotb + Icarus against model.py, clock by clock, at every mode and a spread of N and W; the
declared latency, throughput and capacity checked against the measured ones; the elaboration guards. NET_RTL_PIPE_REG
points the tests at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim
from ip_lib.pipe_reg import model as M

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "pipe_reg" / "tb"
OUT = os.environ.get("PIPE_REG_RESULTS")      # a JSON-lines file the measure test appends to

# (W, N, MODE, TLAST_EN, TKEEP_EN, TUSER_W)
POINTS = [(16, n, m, 0, 0, 0) for m in range(5) for n in (0, 1, 2, 5)] + [(1, 2, 1, 0, 0, 0), (64, 2, 2, 0, 0, 0), (8, 16, 1, 0, 0, 0),
          (8, 16, 0, 0, 0, 0), (8, 8, 3, 0, 0, 0)] + [(32, 3, m, 1, 1, 4) for m in range(5)] + [(64, 2, 1, 1, 1, 0), (8, 1, 4, 1, 0, 3)]


def _run(w, n, mode, tl, tk, tu, tests, extra=None):
    env = {"PYTHONPATH": str(ROOT)}
    env.update(extra or {})
    srcs = sim.rtl("pipe_reg") + [TB / "pipe_reg_axis_tb.sv", ROOT / "axi_tx" / "rtl" / "axis_rules.sv"]
    cocotb_run.run(f"pipe_reg_w{w}_n{n}_m{mode}_{tl}{tk}{tu}", "pipe_reg_axis_tb", srcs, "pipe_reg_cocotb", TB,
                   parameters={"W": w, "N": n, "MODE": mode, "TLAST_EN": tl, "TKEEP_EN": tk, "TUSER_W": tu}, testcase=tests, extra_env=env)


@pytest.mark.parametrize("w,n,mode,tl,tk,tu", POINTS)
def test_random_traffic(w, n, mode, tl, tk, tu):
    _run(w, n, mode, tl, tk, tu, "random_traffic")


@pytest.mark.parametrize("w,n,mode,tl,tk,tu", POINTS)
def test_measure_declared(w, n, mode, tl, tk, tu, tmp_path):
    out = tmp_path / "m.jsonl"
    _run(w, n, mode, tl, tk, tu, "measure", {"PIPE_REG_OUT": str(out)})
    r = json.loads(out.read_text().splitlines()[-1])
    if OUT:
        with open(OUT, "a") as f:
            f.write(json.dumps(r) + "\n")
    assert r["latency"] == M.latency(n, mode)
    assert Fraction(r["throughput_accepted_per_clock"]).limit_denominator(1000) == M.throughput(n, mode)
    assert r["throughput_delivered_per_clock"] == r["throughput_accepted_per_clock"]
    assert r["capacity_beats"] == (M.capacity(n, mode) if n else r["capacity_beats"])
    assert r["ready_response_clocks"] == M.ready_response(n, mode)


@pytest.mark.parametrize("params", [{"W": 0}, {"W": 1025}, {"N": -1}, {"N": 17}, {"MODE": 5}, {"MODE": -1}, {"TLAST_EN": 2},
                                    {"TKEEP_EN": 1, "W": 12}, {"TUSER_W": 65}])
def test_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("pipe_reg"), "pipe_reg", params)
    assert bad, out
