"""Formal jobs of sincos that are refuted when one seeded fault is planted (a check that can fail) (SymbiYosys, OSS CAD Suite; arith brief 139d; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("sincos", "refute"))
def test_formal_job(name):
    suite.check_formal_job("sincos", name)
