"""Every window multiplier variant against the model at the exhaustive points of spec.yaml (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_window", "exhaustive_points"))
def test_directed_points(variant, params):
    ac.run_point("fft_window", variant, params, "exhaustive")
