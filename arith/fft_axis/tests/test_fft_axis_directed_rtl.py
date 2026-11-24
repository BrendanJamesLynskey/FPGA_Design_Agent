"""Every AXI4-Stream FFT wrapper variant against the model at the directed points of spec.yaml, with the protocol checkers (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_axis", "exhaustive_points"))
def test_directed_points(variant, params):
    ac.run_point("fft_axis", variant, params, "directed", n=3000)
