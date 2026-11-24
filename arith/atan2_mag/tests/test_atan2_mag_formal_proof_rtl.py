"""Formal jobs of atan2_mag that are proved for all inputs (k-induction) (SymbiYosys, OSS CAD Suite; arith brief 139d; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("atan2_mag", "proof"))
def test_formal_job(name):
    suite.check_formal_job("atan2_mag", name)
