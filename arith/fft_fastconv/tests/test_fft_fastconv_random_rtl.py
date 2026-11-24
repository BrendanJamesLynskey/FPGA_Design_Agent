"""The fast-convolution block against the model at the random points of spec.yaml, with the three protocol checkers (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_fastconv", "random_points"))
def test_random_points(variant, params):
    ac.run_point("fft_fastconv", variant, params, "randomised", n=3000)
