"""The AXI4-Stream 2-parallel FFT against the model at the random points of spec.yaml: random frames, random idle clocks before each frame, random tready (arith brief 168; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite

@pytest.mark.parametrize("variant,params", suite.point_params("fft_mdc2_axis", "random_points"))
def test_random_points(variant, params):
    ac.run_point("fft_mdc2_axis", variant, params, "randomised", n=3000)
