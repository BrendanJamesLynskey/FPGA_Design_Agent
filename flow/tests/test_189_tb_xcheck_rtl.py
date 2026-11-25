"""Brief 189 item 11: testbench compares that cannot fail on X or Z. A seeded defect (an encoder output stuck at X for one input), a blind
bench that passes it, a strict bench that fails it, and the advisory source check that tells them apart."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from flow import tb_xcheck as T

FX = Path(__file__).parent / "fixtures" / "xcompare"


def _run(tmp: Path, tb: str) -> str:
    vvp = tmp / f"{tb}.vvp"
    r = subprocess.run(["iverilog", "-g2012", "-s", tb, "-o", str(vvp), str(FX / "enc.sv"), str(FX / f"{tb}.sv")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run(["vvp", str(vvp)], capture_output=True, text=True, timeout=60).stdout


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs Icarus Verilog")
def test_seeded_defect_passes_the_blind_bench_and_fails_the_strict_one(tmp_path: Path) -> None:
    assert "XCMP_PASS" in _run(tmp_path, "tb_blind")            # the false green
    assert "XCMP_FAIL" in _run(tmp_path, "tb_strict")


def test_source_check_flags_the_blind_bench_only() -> None:
    blind = T.scan_file(FX / "tb_blind.sv")
    assert [f["code"] for f in blind] == ["TB-X-01"] and "p != ^d" in blind[0]["condition"]
    assert T.scan_file(FX / "tb_strict.sv") == []


@pytest.mark.parametrize("src,flagged", [
    ("if (a != b) $error(\"x\");", True),
    ("if (!(a == b)) fail(\"x\");", True),
    ("if (a != b) errors++;", True),
    ("if (a != b) $display(\"FAIL %0d\", a);", True),
    ("if (a !== b) $error(\"x\");", False),
    ("if (!$isunknown(a) && a != b) $error(\"x\");", False),
    ("if (a != b) count = 1;", False),                          # not an error action
    ("if (a == b) ok++; else $error(\"x\");", False),           # an X compare takes the else branch: fails loudly
    ("assert (a == b) else $error(\"x\");", False),
    ("if (q.size() != 0) $error(\"left over\");", False),       # two-state
    ("// if (a != b) $error(\"x\");", False),
    ("if (a != b) $error(\"x\"); // x-ok: a is two-state here", False),
])
def test_patterns(src: str, flagged: bool) -> None:
    assert bool(T.scan_text(src)) is flagged, src


def test_cli_is_advisory(tmp_path: Path) -> None:
    import json
    out = tmp_path / "o.json"
    assert T.main([str(FX / "tb_blind.sv"), "--json", str(out)]) == 0
    assert json.loads(out.read_text())["enforced"] is False
