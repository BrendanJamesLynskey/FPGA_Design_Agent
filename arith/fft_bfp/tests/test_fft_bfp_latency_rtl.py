"""The bench is sensitive to each variant's stated latency: with the right latency it passes, with two clocks more it fails (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft_bfp"))
def test_latency_is_exact(variant):
    suite.check_latency_is_exact("fft_bfp", variant, ac.load_spec("fft_bfp")["variants"][variant]["random_points"][0])
