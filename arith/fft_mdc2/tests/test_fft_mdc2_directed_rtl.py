"""The 2-parallel FFT against the model at the directed points of spec.yaml (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_mdc2", "exhaustive_points"))
def test_directed_points(variant, params):
    ac.run_point("fft_mdc2", variant, params, "directed")
