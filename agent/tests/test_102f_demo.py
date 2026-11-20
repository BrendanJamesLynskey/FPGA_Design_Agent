"""Brief 102F: the scripted session on the third-party-block project (designs/b102_managed_ext/scripts/demo_gaps_session.py) runs and its
assertions hold. ``FDA_102F_DEMO_OUT=<file>`` records the session there (the committed record under results/102f_managed_gaps/)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_scripted_session_holds(tmp_path):
    spec = importlib.util.spec_from_file_location("demo_gaps_session", ROOT / "designs" / "b102_managed_ext" / "scripts" / "demo_gaps_session.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    out = Path(os.environ.get("FDA_102F_DEMO_OUT") or tmp_path / "demo.json")
    assert m.main(["--work", str(tmp_path / "designs" / "b102_managed_ext"), "--out", str(out)]) == 0
    assert out.is_file()
