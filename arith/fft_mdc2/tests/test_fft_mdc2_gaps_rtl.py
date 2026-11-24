"""The gap rule is measured: N/8 clocks between frames is legal, N/8 - 1 corrupts a frame (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac


@pytest.mark.parametrize("params", [{"LOGN": 5, "W": 8, "TW": 10}, {"LOGN": 6, "ORDER": 1}, {"LOGN": 7, "W": 12, "TW": 14, "SCALE": 0}, {"LOGN": 8}])
def test_gap_rule(params):
    ac.run_point("fft_mdc2", "par2", params, "gaps")
