"""The burst variant honours out_ready: with the sink stalling at random the frames are unchanged and the output is held while stalled (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac


@pytest.mark.parametrize("params", [{"LOGN": 5, "ORDER": 0}, {"LOGN": 6, "ORDER": 1, "CMUL": 3}])
def test_burst_under_a_stalling_sink(params):
    ac.run_point("fft_bfp", "burst", params, "stalled", n=1500)


@pytest.mark.parametrize("params", [{"LOGN": 4, "ORDER": 0}, {"LOGN": 5, "ORDER": 1, "CMUL": 3}])
def test_burst_with_a_sink_so_slow_that_both_banks_fill(params):
    ac.run_point("fft_bfp", "burst", params, "stalled_hard", n=1200)
