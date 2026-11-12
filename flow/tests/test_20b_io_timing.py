"""Brief 20 part B: the I/O-timing check (flow/io_check.py) on the measured fixtures (Vivado 2025.2 reports in
flow/tests/fixtures/io_timing/golden), the forwarded-clock exemption, the margin record, and the agent checker's
FDA-CON-11/-12/-13 on the same XDCs and on the part A agent runs' XDC history."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent.core import constraints as con
from flow import exceptions_check, gates, io_check

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "flow" / "tests" / "fixtures" / "io_timing"
IFS = yaml.safe_load((FX / "interfaces.yaml").read_text())["fixtures"]
BOARD = yaml.safe_load((ROOT / "boards" / "nexys_a7_100t" / "board.yaml").read_text())

# fixture -> the rules flow/io_check.py must raise (empty: clean). Every one was measured (results/20_timing_exceptions/io_table.md)
EXPECT = {
    "io_i1": set(), "io_i2": {"IO-MISSING-MINMAX", "IO-NO-PATH"}, "io_i3": {"IO-MIN-GT-MAX", "IO-VALUE"},
    "io_i3b": {"IO-VALUE"}, "io_i8": {"IO-PLACEHOLDER", "IO-VALUE"}, "io_i9": set(), "io_i10": {"IO-INVENTED"},
    "io_v6": {"IO-ASYNC-CLOCK"}, "io_i4": set(), "io_i4b": {"IO-VALUE"}, "io_v1": set(), "io_v3": set(),
    "io_v4": {"IO-NO-PATH"}, "io_v5": {"IO-CLOCK"}, "io_i7": set(), "io_i7c": set(), "io_i7b": {"IO-CLOCK"},
    "io_i5": set(), "io_i5b": {"IO-REPLACED", "IO-MISSING-MINMAX"}, "io_i6": set(), "io_i6b": set(), "io_v2": set(), "io_v2a": {"IO-CLOCK"},
}


def _eval(name: str) -> dict:
    g = FX / "golden" / name
    return io_check.evaluate(g, "route", [FX / "xdc" / f"{name}.xdc"], IFS[name], None, BOARD["slow_ports"],
                             dump=g / "io_paths.txt")


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_fixture_gives_the_expected_io_rules(name: str) -> None:
    if not (FX / "golden" / name / "io_paths.txt").exists():
        pytest.skip(f"{name} not measured")
    r = _eval(name)
    assert {f["rule"] for f in r["failures"]} == EXPECT[name], r["failures"]


def test_every_fixture_was_measured() -> None:
    missing = [n for n in EXPECT if not (FX / "golden" / n / "io_paths.txt").exists()]
    assert not missing, missing


def test_failures_name_the_xdc_line() -> None:
    r = _eval("io_i3")
    f = next(x for x in r["failures"] if x["rule"] == "IO-MIN-GT-MAX")
    lines = (FX / "xdc" / "io_i3.xdc").read_text().splitlines()
    assert f["file"] == "io_i3.xdc" and "-min 5.500" in lines[f["line"] - 1]


def test_measured_numbers_behind_the_rules() -> None:
    """The facts the KB and course quote: I2 has no hold path; I3 shows 4 ns more setup slack than I1; I8's placeholder
    passes timing; V5's 12 ns virtual clock gives a 2 ns requirement; V2a's board-clock reference gives 2 ns, V2 8 ns."""
    def port(name: str, p: str) -> dict:
        return io_check.parse_io_dump((FX / "golden" / name / "io_paths.txt").read_text())["ports"][p]["paths"]
    assert port("io_i2", "adc_d[0]")["min"] is None
    assert port("io_i3", "adc_d[0]")["max"]["slack"] - port("io_i1", "adc_d[0]")["max"]["slack"] == pytest.approx(4.0, abs=0.01)
    assert port("io_i8", "adc_d[0]")["max"]["slack"] > 0 and port("io_i8", "adc_d[0]")["min"]["slack"] > 0
    assert port("io_v5", "dac_d[0]")["max"]["requirement"] == pytest.approx(2.0)
    assert port("io_v2a", "din[0]")["max"]["requirement"] == pytest.approx(2.0)
    assert port("io_v2", "din[0]")["max"]["requirement"] == pytest.approx(8.0)
    i7, i7c = port("io_i7", "dac_d[0]"), port("io_i7c", "dac_d[0]")
    # I5b: without -add_delay only falling-edge launches are timed (the edge-pair report of every input path)
    reqs = lambda n: set(__import__("re").findall(r"Requirement:.*\((rx_clk \w+)@[\d.]+ns - (rx_clk \w+)@", (FX / "golden" / n / "timing_inputs_edges.rpt").read_text()))
    assert ("rx_clk rise", "rx_clk rise") in reqs("io_i5") and not any(b == "rx_clk rise" for _, b in reqs("io_i5b"))
    assert i7["max"]["slack"] == i7c["max"]["slack"] and i7["max"]["requirement"] == pytest.approx(5.0)


def test_virtual_clock_after_its_delay_is_a_critical_warning_the_exception_gate_fails() -> None:
    msgs = exceptions_check.xdc_messages((FX / "golden" / "io_v4" / "vivado.log").read_text())
    assert {m["id"] for m in msgs} == {"Vivado 12-4739"} and all(m["file"] == "io_v4.xdc" for m in msgs)
    ct = gates.parse_check_timing((FX / "golden" / "io_v4" / "check_timing.rpt").read_text())
    assert ct["no_output_delay"] == 8


def test_max_only_is_partial_input_delay() -> None:
    ct = gates.parse_check_timing((FX / "golden" / "io_i2" / "check_timing.rpt").read_text())
    assert ct["partial_input_delay"] == 8


def test_forwarded_clock_port_is_not_an_unconstrained_output() -> None:
    g = FX / "golden" / "io_i7"
    text = (g / "check_timing.rpt").read_text()
    counts, ports = gates.parse_check_timing(text), gates.parse_check_timing_ports(text)
    assert counts["no_output_delay"] == 1 and ports["no_output_delay"] == ["dac_clk"]
    # the golden keeps the dump as io_paths.txt; the gate reads io_paths_<stage>.txt from a build directory
    fwd = gates.forwarded_clock_ports_text((g / "io_paths.txt").read_text())
    assert fwd == {"dac_clk"}
    assert gates.unconstrained_ok(counts, ports, fwd)
    assert not gates.unconstrained_ok(counts, ports, set())


def test_agent_checker_rules_on_the_fixture_xdcs() -> None:
    got = {}
    for f in sorted((FX / "xdc").glob("io_*.xdc")):
        if f.name.endswith(".pins.xdc") or f.stem == "io_u":
            continue
        got[f.stem] = sorted({x["rule"] for x in con.io_delay_findings(f.read_text(), BOARD)})
    assert got["io_i10"] == ["FDA-CON-11"]
    assert got["io_i3"] == ["FDA-CON-12"]
    assert got["io_v4"] == ["FDA-CON-13"]
    assert got["io_i5b"] == ["FDA-CON-12"]
    assert all(v == [] for k, v in got.items() if k not in ("io_i10", "io_i3", "io_v4", "io_i5b")), got


def test_part_a_agent_runs_invented_delays_are_caught() -> None:
    """Brief 20 part A: every design.xdc version with made-up delays on the slow ports is flagged FDA-CON-11; the versions
    with the 0 ns placeholder plus false path are not."""
    flagged = clean = 0
    for n in (1, 2, 3):
        h = json.loads((ROOT / "results" / "20_timing_exceptions" / "drills" / f"run_{n}.xdc_history.json").read_text())
        for v in list(h.values())[1]:
            text = "\n".join(v["timing_lines"])
            invented = any(("set_input_delay" in l or "set_output_delay" in l) and " 0.000 " not in l for l in v["timing_lines"])
            found = {x["rule"] for x in con.io_delay_findings(text, BOARD)}
            if invented:
                assert "FDA-CON-11" in found, (n, v["stage"])
                flagged += 1
            else:
                assert not found, (n, v["stage"], found)
                clean += 1
    assert flagged == 10 and clean == 3


def test_repo_designs_have_no_io_findings() -> None:
    for f in list((ROOT / "designs").glob("[!_]*/design.xdc")) + list((ROOT / "benchmark").rglob("ref/design.xdc")):
        found = [x for x in con.check_xdc(f.read_text(), ROOT / "boards" / "nexys_a7_100t")
                 if x["rule"] in ("FDA-CON-11", "FDA-CON-12", "FDA-CON-13")]
        assert not found, (f, found)


def test_expected_delays_formulas() -> None:
    e = io_check.expected_delays
    assert e({"direction": "in", "data_sheet": {"tco_min_ns": 1.0, "tco_max_ns": 5.0, "trace_ns": 0.5}}) == {"max": 5.5, "min": 1.5}
    assert e({"direction": "out", "data_sheet": {"tsu_ns": 1.5, "th_ns": 0.5, "trace_ns": 0.4}}) == pytest.approx({"max": 1.9, "min": -0.1})
    assert e({"direction": "in", "clock_period_ns": 10.0, "data_sheet": {"dv_before_ns": 2.0, "dv_after_ns": 2.0}}) == {"max": 3.0, "min": 2.0}
    assert e({"direction": "in", "data_sheet": {"skew_before_ns": 0.5, "skew_after_ns": 0.5}}) == {"max": 0.5, "min": -0.5}
    # edge-aligned DDR output with a forwarded clock: -min is +skew_before (the b58a TX hold sign, review B3)
    assert e({"direction": "out", "clock_period_ns": 8.0, "data_sheet": {"skew_before_ns": 0.5, "skew_after_ns": 0.5}}) \
        == {"max": 3.5, "min": 0.5}
    # with a board clock-to-data skew allowance: both sides of the window narrow by it (b58a TX, 88E1111 20.1 = 1)
    assert e({"direction": "out", "clock_period_ns": 8.0,
              "data_sheet": {"skew_before_ns": 1.3, "skew_after_ns": 0.9, "board_skew_ns": 0.1}}) == {"max": 3.2, "min": 1.2}


def test_uncertainty_breakdown_parse() -> None:
    u = io_check.parse_uncertainty((FX / "golden" / "io_v2" / "timing_worst_setup.rpt").read_text())
    assert u is not None and u["total_ns"] > 0 and {"tsj_ns", "dj_ns", "pe_ns"} <= set(u)


def test_every_fault_is_flagged_by_a_flow_gate() -> None:
    rows = json.loads((ROOT / "results" / "20_timing_exceptions" / "io_table.json").read_text())["rows"]
    faults = [r for r in rows if r["fault"]]
    assert len(faults) == 13 and all(r["flow_flags"] for r in faults), [r["fixture"] for r in faults if not r["flow_flags"]]
    assert sorted(r["fixture"] for r in faults if r["vivado_flags"]) == ["io_i2", "io_v4"]


def test_committed_table_matches_the_goldens() -> None:
    r = subprocess.run([sys.executable, str(FX / "make_table.py"), "--check"], cwd=ROOT)
    assert r.returncode == 0, "results/20_timing_exceptions/io_table.md is stale: run make_table.py"


def test_gates_wire_the_io_check(tmp_path: Path) -> None:
    """A strict build (run.json) with the exception reports but no io dump fails io_timing_clean."""
    g: dict = {}
    (tmp_path / "exceptions_route.rpt").write_text("x")
    (tmp_path / "run.json").write_text("{}")
    r = gates._io(tmp_path, "route", True, g, "io_timing_clean")
    assert g == {"io_timing_clean": False} and r["missing_report"] == "io_paths_route.txt"
