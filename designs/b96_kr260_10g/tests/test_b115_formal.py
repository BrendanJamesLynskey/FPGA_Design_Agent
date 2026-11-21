"""SymbiYosys proofs of the gray-pointer rate matcher rtl/rate_match_gp.sv (brief 115): safety by k-induction (shipped AW = 4 and smaller), the bounded progress check, the covers, and one mutant per key property
that a named assertion must catch (verif/formal/run_formal.py; the properties are bound, the RTL is untouched). Skipped where sby is not installed (CI installs the pinned OSS CAD Suite)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

FORMAL = Path(__file__).resolve().parents[1] / "verif" / "formal"
spec = importlib.util.spec_from_file_location("run_formal", FORMAL / "run_formal.py")
rf = importlib.util.module_from_spec(spec)
sys.modules["run_formal"] = rf
spec.loader.exec_module(rf)

BINDIR = rf.oss_bin()
JOBS = [j for j in rf.plan("ci")]
pytestmark = pytest.mark.skipif(not BINDIR, reason="SymbiYosys (sby) from the OSS CAD Suite not installed")


@pytest.mark.parametrize("job", JOBS, ids=[j["name"] for j in JOBS])
def test_formal(job, tmp_path):
    j = dict(job)
    j.setdefault("defines", [])
    j.setdefault("mutate", None)
    j.setdefault("expect_fail_any", None)
    j.pop("why", None)
    res = rf.run_job(j["name"], j["task"], j["aw"], j["kb"], j["defines"], j["mutate"], j["bmc"], j["prove"], j["cover"], j["expect_fail_any"], tmp_path, BINDIR)
    assert res.get("verdict") in ("PASS", "CAUGHT"), res
    if j["task"] == "cover":
        assert not res.get("unreached_covers"), res
