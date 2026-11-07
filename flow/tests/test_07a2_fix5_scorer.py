"""Brief 07a2 fix 5, group F: run_task.py names a missing hidden-bench dependency instead of scoring 0/0."""

from __future__ import annotations

from benchmark.tools import run_task as rt


def test_missing_third_party_module_is_an_environment_error(tmp_path) -> None:
    (tmp_path / "hidden").mkdir()
    (tmp_path / "hidden" / "bench.yaml").write_text("toplevel: t\nmodule: acceptance\n")
    (tmp_path / "hidden" / "model.py").write_text("import json\nimport numpy_not_installed_xyz as np\nimport acceptance\n")
    (tmp_path / "hidden" / "acceptance.py").write_text("import cocotb\nfrom model import X\n")
    assert rt.missing_modules(tmp_path) == ["numpy_not_installed_xyz"]
    r = rt.run(tmp_path)
    assert r["pass"] is False and r["tests"] == {} and r["error"].startswith("environment:")
    assert "numpy_not_installed_xyz" in r["error"]


def test_stdlib_local_and_installed_modules_are_not_flagged(tmp_path) -> None:
    (tmp_path / "hidden").mkdir()
    (tmp_path / "hidden" / "model.py").write_text("import json, os\nimport yaml\nfrom acceptance import y\nfrom . import z\n")
    (tmp_path / "hidden" / "acceptance.py").write_text("import cocotb\n")
    assert rt.missing_modules(tmp_path) == []
