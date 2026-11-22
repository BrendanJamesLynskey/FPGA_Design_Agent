"""Every mac variant against the model at the large widths of spec.yaml: edge values, carry-chain runs and random operands (arith brief 139a; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("mac", "random_points"))
def test_random_points(variant, params):
    ac.run_point("mac", variant, params, "randomised")
