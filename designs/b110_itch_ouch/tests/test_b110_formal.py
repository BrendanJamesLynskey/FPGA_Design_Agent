"""SymbiYosys proof of book_core's quantity invariants: verif/formal/book.sby (properties bound from book_props.sv; book_core.sv carries formal-only views under `ifdef FORMAL_BOOK`, defined only here).
Brief 188: BMC from reset to depth 12 and the cover that the saturation is reachable. Brief 191: `prove`, k-induction (depth 4 asked, depth 1 suffices) with two strengthening invariants.
Skipped where sby is not installed (OSS CAD Suite 2026-11-12, found as in designs/b96_kr260_10g/tests/test_b115_formal.py). The ablations and seeded faults are run by verif/formal/run_book_formal.py (a record, not a test)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FORMAL = Path(__file__).resolve().parents[1] / "verif" / "formal"


def _bin() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    w = shutil.which("sby")
    return str(Path(w).parent) if w else ""


BIN = _bin()
pytestmark = pytest.mark.skipif(not BIN, reason="SymbiYosys (sby) from the OSS CAD Suite not installed")


@pytest.mark.parametrize("task", ["bmc", "prove", "cover"])
def test_book_invariants(task, tmp_path) -> None:
    env = dict(os.environ, PATH=BIN + os.pathsep + os.environ["PATH"])
    r = subprocess.run(["sby", "-f", "-d", str(tmp_path / task), str(FORMAL / "book.sby"), task], cwd=FORMAL, env=env, capture_output=True, text=True, timeout=1500)
    assert r.returncode == 0, r.stdout[-1500:]
