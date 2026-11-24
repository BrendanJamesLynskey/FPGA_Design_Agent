"""Formal jobs of the multiplier that are refuted when one seeded fault is planted (a check that can fail) (SymbiYosys, OSS CAD Suite; arith brief 139a; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("multiplier", "refute"))
def test_formal_job(name):
    suite.check_formal_job("multiplier", name)
