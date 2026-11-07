"""Brief 07a2 fix 5, group F: a missing hidden-bench dependency is named, not scored 0/0 (benchmark/tools/scoring_env.py)."""

from __future__ import annotations

from benchmark.tools import scoring_env as se


def _task(tmp_path, model: str):
    (tmp_path / "hidden").mkdir()
    (tmp_path / "hidden" / "model.py").write_text(model)
    (tmp_path / "hidden" / "acceptance.py").write_text("import cocotb\nfrom model import X\n")
    return tmp_path


def test_missing_third_party_module_is_an_environment_error(tmp_path) -> None:
    t = _task(tmp_path, "import json\nimport numpy_not_installed_xyz as np\nimport acceptance\n")
    assert se.missing_modules(t) == ["numpy_not_installed_xyz"]
    msg = se.check(t)
    assert msg.startswith("environment:") and "numpy_not_installed_xyz" in msg and "Not an RTL failure" in msg
    assert se.main([str(t)]) == 3


def test_stdlib_local_and_installed_modules_are_not_flagged(tmp_path) -> None:
    t = _task(tmp_path, "import json, os\nimport yaml\nfrom acceptance import y\nfrom . import z\n")
    assert se.missing_modules(t) == [] and se.check(t) is None and se.main([str(t)]) == 0
