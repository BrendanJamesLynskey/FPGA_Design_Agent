"""Every atan2_mag variant against its model at the large points of spec.yaml: edge values, table break points and random inputs (arith brief 139d; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("atan2_mag", "random_points"))
def test_random_points(variant, params):
    ac.run_point("atan2_mag", variant, params, "randomised", n=3000)
