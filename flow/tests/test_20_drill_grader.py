"""Brief 20: the drill's constraint grader (benchmark/drills/lib/grade_constraints.py) on real routed builds of the reference
design and its two constraint mutants (results/20_timing_exceptions/drills/golden: the reports the grader reads, from
flow/run_vivado.sh, Vivado 2025.2). No Vivado needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.drills.lib import grade_constraints as gc

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "benchmark" / "drills" / "d20_slow_fsm_ramp"
GOLD = ROOT / "results" / "20_timing_exceptions" / "drills" / "golden"


def test_reference_passes_every_check() -> None:
    r = gc.grade(TASK, GOLD / "ref")
    assert r["pass"] and r["choice"] == "multicycle", {k: v for k, v in r["checks"].items() if not v["pass"]}
    m = r["checks"]["multicycle"]
    assert m["setup_n"] == [8] and m["hold_n"] == [7] and m["registers"] > 0 and not m["enable_problems"]


@pytest.mark.parametrize("variant,check", [("e10b", "multicycle"), ("e10c", "multicycle")])
def test_constraint_mutants_fail(variant: str, check: str) -> None:
    r = gc.grade(TASK, GOLD / variant)
    assert not r["pass"] and not r["checks"][check]["pass"]
    assert not r["checks"]["exceptions_gate"]["pass"]          # the flow's own gate fails them too (EXC-MCP-ENABLE)


def test_e10c_is_also_a_broad_multicycle() -> None:
    assert gc.grade(TASK, GOLD / "e10c")["checks"]["multicycle"]["broad_lines"]


def test_xdc_rules_and_waivers_on_text(tmp_path: Path) -> None:
    d = tmp_path / "d"
    (d / "build" / "base").mkdir(parents=True)
    (d / "design.xdc").write_text("set_clock_groups -asynchronous -group [get_clocks a] -group [get_clocks b]\n"
                                  "set_multicycle_path 8 -setup -from [get_cells x] -to [get_cells y]\n")
    r = gc.grade(TASK, d)
    assert not r["checks"]["no_broad_waivers"]["pass"]
    assert {f["rule"] for f in r["checks"]["xdc_rules"]["findings"]} == {"FDA-CON-5", "FDA-CON-10"}
    assert not r["pass"]
