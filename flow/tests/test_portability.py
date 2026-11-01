"""flow/portability.py: the T1 checkers compile everywhere they should; a covergroup does not."""

from pathlib import Path

import pytest

from flow import portability as P

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "flow" / "tests" / "fixtures" / "nonportable_covergroup.sv"


def test_covergroup_fixture_fails_in_icarus():
    import shutil
    if not shutil.which("iverilog"):
        pytest.skip("iverilog not installed")
    r = P.check_icarus([str(FIXTURE)], "nonportable_covergroup", [])
    assert r["status"] == "fail" and r["message"]


def test_covergroup_fixture_fails_in_verilator_5_020():
    rows = [r for r in P.check_verilator([str(FIXTURE)], "nonportable_covergroup", []) if r["status"] != "skipped"]
    old = [r for r in rows if r["version"].startswith("Verilator 5.020")]
    if not old:
        pytest.skip("Verilator 5.020 not the installed version (5.048 parses and ignores covergroups)")
    assert old[0]["status"] == "fail" and "Unsupported: covergroup" in old[0]["message"]


def test_t1_checkers_set_passes_where_a_tool_is_installed():
    import yaml
    cfg = yaml.safe_load((ROOT / "designs/t1_dimmer_counter/verif/portability.yaml").read_text())
    rows = P.check_set(cfg["sets"]["t1_checkers_standalone"], ROOT)
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]
    if all(r["status"] == "skipped" for r in rows):
        pytest.skip("no simulator installed")
    assert any(r["status"] == "pass" for r in rows)
