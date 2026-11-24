"""Formal jobs of log2 that are proved for all inputs (k-induction) (SymbiYosys, OSS CAD Suite; arith brief 139d; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("log2", "proof"))
def test_formal_job(name):
    suite.check_formal_job("log2", name)
