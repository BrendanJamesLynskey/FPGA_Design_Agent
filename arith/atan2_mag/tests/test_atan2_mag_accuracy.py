"""The stated error bounds of atan2_mag (spec.yaml 'accuracy_points') are true and not loose: each is the maximum of the model's error over every input of its point,
rounded up to 0.01 (arith brief 139d)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("variant,params,bound", suite.accuracy_points("atan2_mag"))
def test_stated_bound_is_the_measured_maximum(variant, params, bound):
    suite.check_accuracy("atan2_mag", variant, params, bound)
