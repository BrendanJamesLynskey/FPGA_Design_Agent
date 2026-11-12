"""The recorded KR260 build: summary.json is generated from the build's own records (never by hand), and the design
README names every gate the build fails."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REC = ROOT / "results" / "b58a" / "build"


def test_summary_is_generated_from_the_records() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "results" / "b58a" / "build_summary.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_readme_names_every_failed_gate() -> None:
    gates = json.loads((REC / "gates.json").read_text())["gates"]
    failed = [k for k, v in gates.items() if v is False]
    summ = json.loads((REC / "summary.json").read_text())
    assert set(failed) <= set(summ["gates_failed"])
    readme = (ROOT / "designs" / "b58a_trigger" / "README.md").read_text()
    build = readme.split("## Build", 1)[1].split("\n## ", 1)[0]
    missing = [g for g in summ["gates_failed"] if f"`{g}`" not in build]
    assert not missing, f"README Build section does not name: {missing}"
