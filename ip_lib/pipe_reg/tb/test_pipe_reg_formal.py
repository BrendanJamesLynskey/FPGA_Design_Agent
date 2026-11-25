"""SymbiYosys jobs of ip_lib/pipe_reg/formal (formal/run_formal.py): every proof by k-induction, the stream rules as SVA, and the
planted faults each refuted. Skipped where sby is not installed (CI: the formal job installs the OSS CAD Suite)."""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("pipe_reg_run_formal", ROOT / "ip_lib" / "pipe_reg" / "formal" / "run_formal.py")
RF = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = RF
spec.loader.exec_module(RF)
HAVE = bool(RF.oss_bin()) or shutil.which("sby") is not None


@pytest.mark.skipif(not HAVE, reason="SymbiYosys not installed")
@pytest.mark.parametrize("task", RF.TASKS + RF.SVA_TASKS)
def test_proof(task):
    with tempfile.TemporaryDirectory() as t:
        sbyfile = "pipe_sva.sby" if task.startswith("sva_") else "pipe.sby"
        st, _ = RF.run_sby(RF.ENTRY, task, Path(t) / "o", sbyfile)
    assert st == "PASS", st


@pytest.mark.skipif(not HAVE, reason="SymbiYosys not installed")
def test_planted_faults_are_refuted():
    assert RF.main_for_test() == 0
