"""Brief 16: the stronger CDC gate (no simulator needed; the injected simulations are in test_16_cdc_inject_rtl.py). Three layers, each against the rig's mutants (fixtures/cdc_mutants):

* structure: flow/cdc_structure.py on golden Vivado 2025.2 synthesis reports of every fixture (no Vivado needed here;
  regenerate with fixtures/cdc_mutants/run_all.sh under a heavy slot);
* simulation: each fixture's own cocotb test (Icarus) plain and with synchroniser-delay injection (flow/cdc_inject.py);
* wiring: gates.py (post_synth_cdc_structure_clean) and verif_gates.py (cdc_structure_clean, cdc_injection_clean).
The expected results below are the mutant table of reports/16_cdc_gate_report.md (results/16_cdc_gate/mutant_table.json)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from flow import cdc_inject, cdc_structure, gates, verif_gates

FX = Path(__file__).parent / "fixtures" / "cdc_mutants"
sys.path.insert(0, str(FX))
NAMES = sorted(p.stem for p in (FX / "rtl").glob("*.sv"))

#: structural rule that flags the fixture (None = the structure is clean)
STRUCTURE = {
    "cdcfx_c1": None, "cdcfx_c2": None, "cdcfx_c3": None, "cdcfx_c4": None, "cdcfx_c5": None, "cdcfx_c6": None,
    "cdcfx_c7": None, "cdcfx_c8": None, "cdcfx_c9": None, "cdcfx_c10": None, "cdcfx_c11": None, "cdcfx_c12": None,
    "cdcfx_m1": "U2", "cdcfx_m1b": "U2", "cdcfx_m2": "U2", "cdcfx_m3": "U5", "cdcfx_m4": "U3", "cdcfx_m5": None,
    "cdcfx_m6a": "U5", "cdcfx_m7": "U6", "cdcfx_m8": "U1", "cdcfx_m10": "U1",
}


def test_every_fixture_has_an_expectation() -> None:
    assert set(NAMES) == set(STRUCTURE)


@pytest.mark.parametrize("name", NAMES)
def test_structure_of_golden_reports(name: str) -> None:
    g = FX / "golden" / name
    rep = cdc_structure.evaluate(g / "cdc_paths_synth.rpt", g / "cdc_synth.rpt")
    want = STRUCTURE[name]
    assert rep["n_crossings"] > 0, "the fixture has a crossing"
    assert {u["rule"] for u in rep["unsafe"]} == ({want} if want else set()), rep["unsafe"]
    assert rep["pass"] is (want is None)


def test_cdc6_row_alone_is_not_safe() -> None:
    """A Gray bus through a plain ASYNC_REG chain with no exception is CDC-6 in report_cdc and unsafe here; with the exception safe."""
    m6, c6 = (cdc_structure.evaluate(FX / "golden" / n / "cdc_paths_synth.rpt", FX / "golden" / n / "cdc_synth.rpt")
              for n in ("cdcfx_m6a", "cdcfx_c6"))
    assert not m6["pass"] and c6["pass"]
    assert any("CDC-6" in "".join(c["report_cdc_rules"]) for c in m6["crossings"])
    assert all(c["exception"] == "Max Delay Datapath Only" for c in c6["crossings"] if c["class"] == "gray")


def test_report_cdc_alone_misses_the_bus_and_reconvergence() -> None:
    """The flow's existing gate (no Critical row in report_cdc) passes the mutants this check exists for."""
    def crit(n):
        return sum(r["count"] for r in gates.parse_cdc((FX / "golden" / n / "cdc_synth.rpt").read_text())["rules"]
                   if r["severity"] == "Critical")
    for missed in ("cdcfx_m3", "cdcfx_m6a", "cdcfx_m7", "cdcfx_m5"):
        assert crit(missed) == 0, missed
    for correct in NAMES:
        if correct.startswith("cdcfx_c"):
            assert crit(correct) == 0, correct


def test_waiver_needs_a_reason_and_names_the_cell() -> None:
    g = FX / "golden" / "cdcfx_m3"
    paths = cdc_structure.parse_paths((g / "cdc_paths_synth.rpt").read_text())
    rows = cdc_structure.parse_cdc_rows((g / "cdc_synth.rpt").read_text())
    assert not cdc_structure.classify(paths, rows, [{"cell": "s1_reg", "reason": ""}])["pass"]
    ok = cdc_structure.classify(paths, rows, [{"cell": "s1_reg", "reason": "static configuration word, changes only in reset"}])
    assert ok["pass"] and ok["summary"].get("waived")


def test_incomplete_or_failed_dump_fails() -> None:
    g = FX / "golden" / "cdcfx_c1" / "cdc_paths_synth.rpt"
    text = g.read_text()
    with pytest.raises(ValueError):
        cdc_structure.parse_paths(text.replace("# end", ""))
    rows = cdc_structure.parse_paths(text + "")
    rows["errors"] = ["sync_reg[0]|D|boom"]
    assert not cdc_structure.classify(rows, [])["pass"]


# ---- injection ----------------------------------------------------------------------------------------------------

def test_injection_rewrites_each_synchroniser_shape() -> None:
    shapes = {"cdcfx_c1": 1, "cdcfx_c4": 1, "cdcfx_c8": 2, "cdcfx_c10": 2, "cdcfx_m7": 2, "cdcfx_c6": 1}
    for n, sites in shapes.items():
        new, info = cdc_inject.inject_text((FX / "rtl" / f"{n}.sv").read_text())
        assert info["sites"] == sites and not info["unhandled"], (n, info)
        assert "cdc_inj_pkg::hold" in new
    # a later stage and a reset constant are not injected; an unrecognised shape is reported
    _, info = cdc_inject.inject_text((FX / "rtl" / "cdcfx_c12.sv").read_text())
    assert info["sites"] == 1
    _, info = cdc_inject.inject_text('(* ASYNC_REG = "TRUE" *) logic [1:0] q; always_ff @(posedge c) q <= {q[0], d} ^ x;')
    assert info["unhandled"]


def test_design_crosses(tmp_path: Path) -> None:
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "a.sv").write_text("module a(input clk); logic r; always_ff @(posedge clk) r <= 1; endmodule\n")
    assert not cdc_inject.design_crosses(tmp_path)
    (tmp_path / "rtl" / "a.sv").write_text('module a(input clk); (* ASYNC_REG = "TRUE" *) logic r; endmodule\n')
    assert cdc_inject.design_crosses(tmp_path)
    (tmp_path / "rtl" / "a.sv").write_text("module a(input clk); // ASYNC_REG in a comment\nendmodule\n")
    assert not cdc_inject.design_crosses(tmp_path)


# ---- wiring -------------------------------------------------------------------------------------------------------

def _gates_json(name: str) -> dict:
    g = FX / "golden" / name
    cs = cdc_structure.evaluate(g / "cdc_paths_synth.rpt", g / "cdc_synth.rpt")
    return {"stages": {"post_synth": {"ran": True, "gates": {"post_synth_cdc_structure_clean": cs["pass"]}, "cdc_structure": cs}}}


def _design(tmp_path: Path, rtl_name: str) -> Path:
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / f"{rtl_name}.sv").write_text((FX / "rtl" / f"{rtl_name}.sv").read_text())
    return d


def test_verif_gate_cdc_checks(tmp_path: Path) -> None:
    d = _design(tmp_path, "cdcfx_c1")
    good = verif_gates.cdc_checks(d, _gates_json("cdcfx_c1"), None)
    assert good["cdc_structure_clean"]["pass"] and not good["cdc_injection_clean"]["pass"]       # no injection report: fails
    assert "missing" in str(good["cdc_injection_clean"]["value"])
    ev = tmp_path / "cdc_inject.json"
    ev.write_text(json.dumps({"pass": True}))
    assert verif_gates.cdc_checks(d, _gates_json("cdcfx_c1"), ev)["cdc_injection_clean"]["pass"]
    ev.write_text(json.dumps({"pass": False, "why": "seeds [1] fail"}))
    r = verif_gates.cdc_checks(d, _gates_json("cdcfx_c1"), ev)["cdc_injection_clean"]
    assert not r["pass"] and "seeds" in r["why"]
    assert not verif_gates.cdc_checks(d, None, ev)["cdc_structure_clean"]["pass"]               # no gates.json: fails
    bad = verif_gates.cdc_checks(_design(tmp_path / "x", "cdcfx_m3"), _gates_json("cdcfx_m3"), ev)
    assert not bad["cdc_structure_clean"]["pass"] and "U5" in bad["cdc_structure_clean"]["why"]


def test_verif_gate_ignores_a_design_with_no_crossing(tmp_path: Path) -> None:
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "a.sv").write_text("module a(input clk); logic r; always_ff @(posedge clk) r <= 1; endmodule\n")
    assert verif_gates.cdc_checks(d, None, None) == {}


def test_flow_gate_structure_clean_in_gates_py(tmp_path: Path) -> None:
    """A strict build (run.json present) with no cdc_paths_synth.rpt fails the gate; with the golden report it follows the result."""
    import shutil
    data = Path(__file__).parent / "data"
    for dst, src in {"methodology_rtl.rpt": "good_methodology_rtl.rpt", "timing_summary_synth.rpt": "good_timing_summary_synth.rpt",
                     "check_timing_synth.rpt": "good_check_timing_synth.rpt", "methodology_synth.rpt": "good_methodology_synth.rpt",
                     "drc_synth.rpt": "good_drc_synth.rpt", "qor_assessment_synth.rpt": "good_qor_assessment_synth.rpt",
                     "utilization_synth.rpt": "good_utilization_synth.rpt"}.items():
        shutil.copy(data / src, tmp_path / dst)
    shutil.copy(FX / "golden" / "cdcfx_m3" / "cdc_synth.rpt", tmp_path / "cdc_synth.rpt")
    (tmp_path / "run.json").write_text("{}")
    assert gates.evaluate(tmp_path)["gates"]["post_synth_cdc_structure_clean"] is False        # strict: report missing
    shutil.copy(FX / "golden" / "cdcfx_m3" / "cdc_paths_synth.rpt", tmp_path / "cdc_paths_synth.rpt")
    r = gates.evaluate(tmp_path)
    assert r["gates"]["post_synth_cdc_no_critical"] is True               # report_cdc alone passes the bit-by-bit bus
    assert r["gates"]["post_synth_cdc_structure_clean"] is False          # the structural check does not
    shutil.copy(FX / "golden" / "cdcfx_c7" / "cdc_paths_synth.rpt", tmp_path / "cdc_paths_synth.rpt")
    shutil.copy(FX / "golden" / "cdcfx_c7" / "cdc_synth.rpt", tmp_path / "cdc_synth.rpt")
    assert gates.evaluate(tmp_path)["gates"]["post_synth_cdc_structure_clean"] is True
