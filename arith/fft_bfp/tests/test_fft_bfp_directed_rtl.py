"""Every block-floating-point FFT variant against the model at the directed points of spec.yaml (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_bfp", "exhaustive_points"))
def test_directed_points(variant, params):
    ac.run_point("fft_bfp", variant, params, "directed")
