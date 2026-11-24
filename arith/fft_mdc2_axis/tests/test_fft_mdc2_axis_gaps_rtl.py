"""The idle clocks between frames, whatever the source does: 0 or at least N/8, and max(source idle, N/8) for a source idle of 1 or more (arith brief 168; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite

@pytest.mark.parametrize("variant,params", suite.point_params("fft_mdc2_axis", "exhaustive_points"))
def test_gaps(variant, params):
    ac.run_point("fft_mdc2_axis", variant, params, "gaps")
