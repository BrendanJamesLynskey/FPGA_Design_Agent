"""Formal jobs of the mac that are checked to a bounded depth from reset (BMC: nothing is claimed past the depth) (SymbiYosys, OSS CAD Suite; arith brief 139a; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("mac", "bounded"))
def test_formal_job(name):
    suite.check_formal_job("mac", name)
