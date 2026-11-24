"""The bench is sensitive to each variant's stated latency (first beat in to first beat out): right latency passes, two clocks more fails (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft_axis"))
def test_latency_is_exact(variant):
    spec = ac.load_spec("fft_axis")
    params = spec["variants"][variant]["exhaustive_points"][1]
    p = ac.merged_params(spec, variant, params)
    good = ac.latency_of(spec, variant, p)
    ac.run_point("fft_axis", variant, params, "directed", lat=good)
    with pytest.raises(AssertionError):
        ac.run_point("fft_axis", variant, params, "directed", lat=good + 2)
