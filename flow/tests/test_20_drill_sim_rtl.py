"""Brief 20: the drill's simulation enable check (benchmark/drills/lib/sim_enable_check.py) under Icarus (CI: RTL job)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "benchmark" / "drills" / "d20_slow_fsm_ramp"
GOLD = ROOT / "results" / "20_timing_exceptions" / "drills" / "golden"


@pytest.mark.skipif(__import__("shutil").which("iverilog") is None, reason="needs Icarus")
def test_simulation_enable_check_on_reference_and_e10b(tmp_path: Path) -> None:
    """The phase check (lib/sim_enable_check.py) passes the reference and fails the E10b mutant, whose copy of the level
    follows it one clock later, off the tick's phase."""
    import shutil
    import yaml
    from benchmark.drills.lib import sim_enable_check as se
    ok = se.check(TASK, TASK / "ref" / "rtl", GOLD / "ref" / "build" / "base" / "mcp_paths_route.txt")
    assert ok["pass"] and not ok["off_phase"], ok
    m = next(x for x in yaml.safe_load((TASK / "hidden" / "mutants.yaml").read_text())["constraint_mutants"]
             if x["name"] == "copy_every_clock")
    rtl = tmp_path / "rtl"
    shutil.copytree(TASK / "ref" / "rtl", rtl)
    f = rtl / m["file"]
    f.write_text(f.read_text().replace(m["find"], m["replace"]))
    bad = se.check(TASK, rtl, GOLD / "e10b" / "build" / "base" / "mcp_paths_route.txt")
    assert not bad["pass"] and "u_core.level_q" in bad["off_phase"], bad
