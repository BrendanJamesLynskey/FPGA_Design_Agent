"""A filter of gain 2**GB and a loud input: the outputs saturate exactly as the model says, STATUS.SAT is set and cleared by writing 1 (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_fastconv", "exhaustive_points")[:2])
def test_saturation(variant, params):
    ac.run_point("fft_fastconv", variant, params, "saturate")
