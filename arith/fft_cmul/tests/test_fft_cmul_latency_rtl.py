"""The bench is sensitive to each variant's stated latency: with the right latency it passes, with two clocks more it fails (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft_cmul"))
def test_latency_is_exact(variant):
    suite.check_latency_is_exact("fft_cmul", variant, ac.load_spec("fft_cmul")["variants"][variant]["random_points"][0])
