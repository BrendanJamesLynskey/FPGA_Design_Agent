"""Frames of very different levels (zero, one LSB, quiet and loud noise, a loud and a quiet tone, the most negative value) visit every exponent range, bit exact against the model (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_bfp", "exhaustive_points"))
def test_level_frames(variant, params):
    ac.run_point("fft_bfp", variant, params, "levels")
