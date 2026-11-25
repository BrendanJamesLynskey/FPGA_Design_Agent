"""Every floating-point adder variant against the model, every input, at the small widths of spec.yaml (arith brief 139e; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fp_add", "exhaustive_points"))
def test_exhaustive_points(variant, params):
    ac.run_point("fp_add", variant, params, "exhaustive")
