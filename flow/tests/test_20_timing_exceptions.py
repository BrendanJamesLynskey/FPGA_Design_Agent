"""Brief 20: the exception gate (flow/exceptions_check.py, wired into flow/gates.py) on the Vivado 2025.2 reports of the
timing-exception fixtures (flow/tests/fixtures/timing_exceptions/golden), and its parsers. No Vivado needed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from flow import exceptions_check as ec
from flow import gates
from flow.tests.fixtures.timing_exceptions import make_table as mt

FX = Path(__file__).parent / "fixtures" / "timing_exceptions"
GOLD = FX / "golden"
NAMES = [n for n in mt.DESCR if (GOLD / n).is_dir()]


def xdcs(name: str) -> list[Path]:
    return [FX / "xdc" / f"{name}.clocks.xdc", FX / "xdc" / f"{name}.xdc"]


def test_every_fixture_has_golden_reports() -> None:
    assert NAMES == list(mt.DESCR)


@pytest.mark.parametrize("name", [n for n in NAMES if mt.EXPECT[n] is not None])
def test_the_flow_flags_exactly_the_faulty_fixtures(name: str) -> None:
    r = mt.fixture(name)
    assert r["flow_flags"] == mt.EXPECT[name], (name, r["exceptions_gate"], r["cdc_structure"], r["xdc_rules"], r["timing_ok"])


def test_which_check_catches_which_fault() -> None:
    rows = {n: mt.fixture(n) for n in NAMES}
    rule = lambda n: set(rows[n]["exceptions_gate"]["rules"])
    assert "XDCH-1" in rule("tex_e2") and rows["tex_e2"]["xdc_rules"] == ["FDA-CON-10"]
    assert "TIMING-47" in rule("tex_e4")
    assert rows["tex_e5"]["exceptions_gate"]["pass"] and not rows["tex_e5"]["cdc_structure"]["pass"]   # brief 16's gate
    assert rule("tex_e6") == {"EXC-XDC-MSG"}
    assert rule("tex_e6b") == {"EXC-IGNORED"}            # Non-existent path; coverage 0 is the same exception
    assert {"EXC-IGNORED", "TIMING-24"} <= rule("tex_e7")
    for ok in ("tex_e1", "tex_e8", "tex_e9", "tex_e10"):
        assert rows[ok]["exceptions_gate"]["pass"] and rows[ok]["cdc_structure"]["pass"] and not rows[ok]["xdc_rules"], ok


def test_failures_name_the_xdc_line() -> None:
    r = ec.evaluate(GOLD / "tex_e4", "synth", xdcs("tex_e4"))
    f = next(x for x in r["failures"] if x["rule"] == "TIMING-47")
    assert (f["file"], f["line"]) == ("tex_e4.xdc", 2) and f["text"].startswith("set_false_path")
    r = ec.evaluate(GOLD / "tex_e6", "synth", xdcs("tex_e6"))
    assert sorted((x["file"], x["line"]) for x in r["failures"]) == [("tex_e6.xdc", 2), ("tex_e6.xdc", 3)]
    r = ec.evaluate(GOLD / "tex_e7", "synth", xdcs("tex_e7"))
    f = next(x for x in r["failures"] if x["rule"] == "EXC-IGNORED")
    assert (f["file"], f["line"], f["position"]) == ("tex_e7.xdc", 2, 3)


def test_positions_count_clocks_and_exceptions_in_read_order(tmp_path: Path) -> None:
    a = tmp_path / "a.xdc"
    a.write_text("set_property PACKAGE_PIN E3 [get_ports clk]\ncreate_clock -period 10 [get_ports clk]\n"
                 "# why\nset_false_path -from [get_ports x]; set_max_delay 3 -to [get_ports y]\n")
    b = tmp_path / "b.xdc"
    b.write_text("set_multicycle_path 2 -setup -from [get_cells a] -to [get_cells b]\n")
    p = ec.xdc_positions([a, b])
    assert [(v["file"], v["line"]) for v in p.values()] == [("a.xdc", 2), ("a.xdc", 4), ("a.xdc", 4), ("b.xdc", 1)]


def test_wired_into_the_post_synth_gate(tmp_path: Path) -> None:
    """A strict build (run.json) without the exception reports fails post_synth_exceptions_clean; with a fixture's reports
    the gate follows exceptions_check."""
    d = tmp_path / "build"
    shutil.copytree(GOLD / "tex_e4", d)
    (d / "check_timing_synth.rpt").write_text("1. checking no_clock (0)\n")
    (d / "drc_synth.rpt").write_text("REPORT SUMMARY\nChecks found: 0\n")
    ex = {}
    assert gates._exceptions(d, "synth", True, ex, "post_synth_exceptions_clean")["pass"] is False
    assert ex == {"post_synth_exceptions_clean": False}
    for f in d.glob("exceptions_*"):
        f.unlink()
    ex = {}
    assert gates._exceptions(d, "synth", True, ex, "post_synth_exceptions_clean")["missing_report"] == "exceptions_synth.rpt"
    assert gates._exceptions(d, "synth", False, {}, "x") is None


def test_stage_messages_name_the_exception() -> None:
    from agent.graph.stages import _stage_pass
    exc = ec.evaluate(GOLD / "tex_e4", "synth", xdcs("tex_e4"))
    g = {"stages": {"post_synth": {"ran": True, "gates": {"post_synth_exceptions_clean": False}, "exceptions": exc}}}
    ok, why = _stage_pass(g, "post_synth")
    assert not ok and "TIMING-47 tex_e4.xdc:2 set_false_path" in why[0]


def test_committed_table_matches_the_golden_reports() -> None:
    table = json.loads((Path(__file__).parents[2] / "results" / "20_timing_exceptions" / "exceptions_table.json").read_text())
    assert [r["fixture"] for r in table["rows"]] == NAMES
    for row in table["rows"]:
        assert row == json.loads(json.dumps(mt.fixture(row["fixture"]))), row["fixture"]
