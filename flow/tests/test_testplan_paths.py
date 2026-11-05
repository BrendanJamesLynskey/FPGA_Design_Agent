"""Testplan paths: repo-relative (documented), absolute, or relative to the design directory as a fallback
(live run 20261105-001259-e811: ``model: model.py`` made V0 report a model that existed as missing)."""
from pathlib import Path

from flow.verif_gates import ROOT, plan_file


def test_design_relative_fallback(tmp_path):
    design = tmp_path / "d"
    design.mkdir()
    (design / "model.py").write_text("class Model: pass\n")
    assert plan_file(design, "model.py") == design / "model.py"


def test_repo_relative_wins_when_it_exists(tmp_path):
    design = tmp_path / "d"
    design.mkdir()
    assert plan_file(design, "flow/verif_gates.py") == ROOT / "flow/verif_gates.py"


def test_missing_stays_repo_relative(tmp_path):
    design = tmp_path / "d"
    design.mkdir()
    assert plan_file(design, "nowhere/model.py") == ROOT / "nowhere/model.py"


def test_absolute(tmp_path):
    p = tmp_path / "x.py"
    assert plan_file(tmp_path, str(p)) == p
