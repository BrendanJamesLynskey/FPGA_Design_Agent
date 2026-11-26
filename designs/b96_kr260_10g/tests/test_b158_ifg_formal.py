"""SymbiYosys check of the two mac64_tx interframe-gap conditions that code coverage showed no simulation reaches (brief 158; verif/formal/mac64_tx_ifg.sby): the covers of
`n + 4 - 8 > 4` (RTL line 76) and `!(n + 4 > 4)` (line 79) are unreached, the same conditions as assertions are proved, the neighbouring arms are reachable, and, as a control, the
same properties on a copy of the RTL with n = s_nb1 + 2 find the first condition reachable and the proof fails (so the unreached result is not an artefact of the harness).
Skipped where sby is not installed (CI installs the pinned OSS CAD Suite)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).resolve().parents[1]
FORMAL = DESIGN / "verif" / "formal"


def _bindir() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    w = shutil.which("sby")
    return str(Path(w).parent) if w else ""


BINDIR = _bindir()
pytestmark = pytest.mark.skipif(not BINDIR, reason="SymbiYosys (sby) from the OSS CAD Suite not installed")


def sby(workdir: Path, task: str, src: Path = FORMAL) -> tuple[int, str]:
    env = dict(os.environ, PATH=BINDIR + os.pathsep + os.environ["PATH"])
    r = subprocess.run(["sby", "-f", "-d", str(workdir / task), str(src / "mac64_tx_ifg.sby"), task], capture_output=True, text=True, env=env, cwd=src)
    return r.returncode, r.stdout + r.stderr


def test_both_conditions_are_unreached(tmp_path):
    rc, out = sby(tmp_path, "unreach_cover")
    assert out.count("Unreached cover statement") == 2 and "UNREACH_A" in out and "UNREACH_B" in out, out[-2000:]
    assert "Reached cover statement" not in out


def test_both_conditions_are_proved_unreachable(tmp_path):
    rc, out = sby(tmp_path, "unreach_prove")
    assert rc == 0 and "DONE (PASS" in out, out[-2000:]


def test_neighbouring_arms_are_reachable(tmp_path):
    rc, out = sby(tmp_path, "reach_cover")
    assert rc == 0 and out.count("Reached cover statement") >= 6 and "Unreached" not in out, out[-2000:]


def test_control_a_wider_n_makes_the_first_condition_reachable(tmp_path):
    """RTL copy where n = s_nb1 + 2 (1 to 9 bytes): condition A is reachable (a trace), the range assertion and the proof fail."""
    src = tmp_path / "ctl"
    (src / "verif" / "formal").mkdir(parents=True)
    (src / "rtl").mkdir()
    for f in (DESIGN / "rtl").glob("*.sv"):
        shutil.copy(f, src / "rtl" / f.name)
    for f in list(FORMAL.glob("mac64_tx_*")):
        shutil.copy(f, src / "verif" / "formal" / f.name)
    text = (src / "rtl" / "mac64_tx.sv").read_text()
    assert text.count("int'(s_nb1) + 1") == 1
    (src / "rtl" / "mac64_tx.sv").write_text(text.replace("int'(s_nb1) + 1", "int'(s_nb1) + 2"))
    rc, out = sby(tmp_path, "unreach_cover", src / "verif" / "formal")
    assert "Reached cover statement" in out and "UNREACH_A" in out, out[-2000:]
    rc, out = sby(tmp_path, "unreach_prove", src / "verif" / "formal")
    assert rc != 0 and "Assert failed" in out, out[-2000:]
