"""Brief 81: with FDA_REQUIRE_FORMAL=1 a formal test that skips for a missing tool fails (conftest.py)."""
import subprocess
import sys
import textwrap
from pathlib import Path

import conftest

ROOT = Path(__file__).resolve().parents[2]


def test_the_rule():
    on = {"FDA_REQUIRE_FORMAL": "1"}
    assert conftest.formal_skip_is_failure("needs sby, yosys and z3 on PATH", on)
    assert conftest.formal_skip_is_failure("boolector not installed", on)
    assert not conftest.formal_skip_is_failure("needs sby, yosys and z3 on PATH", {})
    assert not conftest.formal_skip_is_failure("hw test: needs the board (--hw-port)", on)


def test_a_skipped_formal_test_fails_only_when_required(tmp_path):
    t = tmp_path / "test_x.py"
    t.write_text(textwrap.dedent('''
        import pytest
        @pytest.mark.skip(reason="needs sby on PATH")
        def test_formal(): pass
        @pytest.mark.skip(reason="needs a board")
        def test_other(): pass
    '''))
    def run(env):
        import os
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(ROOT), "-c", str(ROOT / "pyproject.toml"),
                               "--confcutdir", str(ROOT), "-p", "conftest", str(t)], capture_output=True, text=True,
                              cwd=ROOT, env={**os.environ, **env, "PYTHONPATH": str(ROOT)})
    assert "error" not in run({}).stdout and "failed" not in run({}).stdout
    r = run({"FDA_REQUIRE_FORMAL": "1"})
    assert "1 error" in r.stdout or "1 failed" in r.stdout, r.stdout + r.stderr
