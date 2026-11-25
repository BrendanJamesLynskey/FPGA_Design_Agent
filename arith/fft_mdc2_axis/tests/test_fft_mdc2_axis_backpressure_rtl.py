"""A sink that stalls for three frame times and one that is ready one clock in four, many frames with random idles and a sink that alternates ready and stalled, and frames so far apart that the store drains (arith brief 168; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite

@pytest.mark.parametrize("mode", ["backpressure", "stress", "drain"])
@pytest.mark.parametrize("variant,params", suite.point_params("fft_mdc2_axis", "exhaustive_points"))
def test_back_pressure(variant, params, mode):
    ac.run_point("fft_mdc2_axis", variant, params, mode, n=1500)
