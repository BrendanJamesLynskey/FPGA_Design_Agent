"""Brief 217 item 0: the R1 snapshot for a simulator stop. Brief 213's run 3 showed three firings that each said only "Simulator shut down prematurely"
(a bench that starts the clock inside its first test: cocotb cancels it when that test ends, the next test waits for an edge and the simulator ends).
The fixture ``bad_clock`` seeds that bug."""

from __future__ import annotations

import shutil

import pytest

from agent.tests.test_213_repair_feedback import DATA, make, run_local  # noqa: F401  (make is a fixture)
from flow import divergence

needs_sim = pytest.mark.skipif(shutil.which("iverilog") is None, reason="Icarus not installed")


@needs_sim
def test_a_simulator_stop_digest_names_the_clock(make):  # noqa: F811
    d = make("bad_clock", record=False)
    snap = divergence.diagnose(d, run_local)
    assert snap and divergence.is_sim_stop(snap) and snap["test"] == "second"
    txt = divergence.snapshot_digest(snap, sorted((d / "rtl").glob("*.sv")))
    assert "did not fail an assertion" in txt and "no rising edge was sampled after the test began" in txt
    assert "cancelled by cocotb when that test ends" in txt
    assert txt != "[first failing check] test second failed" and "Simulator shut down prematurely" in txt   # says the cocotb wording, once, and more
    msg = divergence.sim_stop_message(snap, sorted((d / "rtl").glob("*.sv")))
    assert "no rising edge of clk" in msg and "Simulator shut down" not in msg           # the ledger's one line carries the fact, not the cocotb phrase


def test_a_stop_with_a_running_clock_and_a_finish_in_the_rtl(tmp_path):
    rtl = tmp_path / "x.sv"
    rtl.write_text("module x;\n  always @(posedge clk) if (bad) $fatal(1, \"boom\");\nendmodule\n")
    snap = {"test": "t", "exception": "SimFailure", "message": "Simulator shut down prematurely", "sim_time_ns": 30.0, "test_start_ns": 100.0, "clock": "clk",
            "dut_ring": [{"t": 100.0 + 10 * i, "cycle": i, "sig": {}} for i in range(3)],
            "log_ring": [{"t": 125.0, "level": "ERROR", "logger": "dut", "msg": "assertion failed in x.sv"},
                         {"t": 126.0, "level": "WARNING", "logger": "py.warnings", "msg": "ResourceWarning: unclosed file"}]}
    txt = divergence.snapshot_digest(snap, [rtl])
    assert "3 rising edges were sampled during the test" in txt and "x.sv:2" in txt and "assertion failed in x.sv" in txt
    assert "ResourceWarning" not in txt                                                   # noise records are not shown
    assert "RTL has x.sv:2" in divergence.sim_stop_message(snap, [rtl])
    assert not divergence.is_sim_stop({"exception": "AssertionError", "message": "q: rtl 1 model 2"})
