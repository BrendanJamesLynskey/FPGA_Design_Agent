"""The burst variant honours out_ready: with the sink stalling at random the frames are unchanged and the output is held while stalled (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac


@pytest.mark.parametrize("params", [{"LOGN": 5, "ORDER": 0}, {"LOGN": 6, "ORDER": 1, "SCALE": 0, "CMUL": 3}])
def test_burst_under_a_stalling_sink(params):
    ac.run_point("fft", "burst", params, "stalled", n=1500)
