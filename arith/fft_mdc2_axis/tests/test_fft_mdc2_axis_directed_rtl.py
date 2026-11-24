"""The AXI4-Stream 2-parallel FFT against the model at the directed points of spec.yaml (frames of every kind, saturation frames, forward and inverse), with the protocol checkers and the exact latency (arith brief 168; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite

@pytest.mark.parametrize("variant,params", suite.point_params("fft_mdc2_axis", "exhaustive_points"))
def test_directed_points(variant, params):
    ac.run_point("fft_mdc2_axis", variant, params, "directed", n=3000)
