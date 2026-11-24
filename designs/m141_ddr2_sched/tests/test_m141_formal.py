"""SymbiYosys proofs of the DDR2 scheduler's timing rules, request order, refresh debt and bounded response, and one mutant per rule that a named assertion must catch (brief 141;
verif/formal/run_formal.py; the properties are bound, the RTL is untouched). Skipped where sby is not installed (CI installs the pinned OSS CAD Suite)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

FORMAL = Path(__file__).resolve().parents[1] / "verif" / "formal"
spec = importlib.util.spec_from_file_location("run_formal_m141", FORMAL / "run_formal.py")
rf = importlib.util.module_from_spec(spec)
sys.modules["run_formal_m141"] = rf
spec.loader.exec_module(rf)

BINDIR = rf.oss_bin()
JOBS = rf.plan("ci")
pytestmark = pytest.mark.skipif(not BINDIR, reason="SymbiYosys (sby) from the OSS CAD Suite not installed")


@pytest.mark.parametrize("job", JOBS, ids=[j["name"] for j in JOBS])
def test_formal(job, tmp_path):
    j = dict(job)
    j.pop("why", None)
    res = rf.run_job(j["name"], j["cfg"], j["task"], j["depth"], j["engine"], j.get("mutate"), j.get("expect_fail_any"), tmp_path, BINDIR, j.get("skip", ""), only=j.get("only"))
    assert res.get("verdict") in ("PASS", "CAUGHT"), res
    if j["task"] == "cover":
        assert not res.get("unreached_covers"), res
