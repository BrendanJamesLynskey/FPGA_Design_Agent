"""Every atan2_mag variant against its model, every input, at the small points of spec.yaml (arith brief 139d; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("atan2_mag", "exhaustive_points"))
def test_exhaustive_points(variant, params):
    ac.run_point("atan2_mag", variant, params, "exhaustive")
