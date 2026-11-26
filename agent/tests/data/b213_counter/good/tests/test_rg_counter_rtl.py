"""The design's own bench (an agent-style bench): directed sequences, step(inputs) once per clock, checked against model.py."""
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))

from flow import cocotb_run  # noqa: E402


def test_rg_counter_rtl():
    cocotb_run.run("rg_counter", "rg_counter", sorted((DESIGN / "rtl").glob("*.sv")), "bench_rg_counter", DESIGN / "tests", seed=1)
