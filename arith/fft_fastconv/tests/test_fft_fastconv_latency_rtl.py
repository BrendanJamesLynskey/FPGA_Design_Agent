"""The bench is sensitive to the stated latency: with the right latency it passes, with two clocks more it fails (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft_fastconv"))
def test_latency_is_exact(variant):
    spec = ac.load_spec("fft_fastconv")
    params = spec["variants"][variant]["exhaustive_points"][1]
    p = ac.merged_params(spec, variant, params)
    good = ac.latency_of(spec, variant, p)
    ac.run_point("fft_fastconv", variant, params, "directed", lat=good)
    with pytest.raises(AssertionError):
        ac.run_point("fft_fastconv", variant, params, "directed", lat=good + 2)
