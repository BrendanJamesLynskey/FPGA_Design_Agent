"""Brief 162: the committed results are consistent (no Vivado, no AMD file, no ngspice needed)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

R = Path(__file__).resolve().parents[2] / "results/162_kr260_si"


def _rows(name):
    return list(csv.DictReader((R / name).open()))


def test_sweep_is_complete_and_names_its_source():
    rows = _rows("drive_slew_sweep.csv")
    assert len(rows) == 868
    assert {r["length_in"] for r in rows} == {"1", "3", "6", "10"}
    assert {r["series_ohm"] for r in rows} == {"0", "10", "15", "22", "27", "33", "47"}
    assert all(r["model"] and r["ibis_file"] and r["file_rev"] for r in rows)


def test_22_ohm_is_not_a_3v3_answer_on_long_lines():
    rows = _rows("drive_slew_sweep.csv")
    long33 = [r for r in rows if r["standard"] == "LVCMOS33" and r["length_in"] in ("6", "10") and r["series_ohm"] == "22"]
    assert long33 and not any(r["pass"] == "True" for r in long33)
    hp18 = [r for r in rows if r["standard"] == "LVCMOS18" and r["length_in"] in ("3", "6", "10") and r["series_ohm"] == "22"]
    assert sum(r["pass"] == "True" for r in hp18) >= 24      # 8 to 9 of 15 combinations at each length


def test_ngspice_agrees_with_a_series_resistor():
    rows = [r for r in _rows("ngspice_check.csv") if float(r["series_ohm"]) > 0]
    assert len(rows) == 24
    assert max(float(r["waveform_max_abs_diff_v"]) for r in rows) < 0.05
    assert max(abs(float(r["dpeak_v"])) for r in rows) < 0.01


def test_ibis_revision_check_found_no_difference():
    rows = _rows("ibis_revision_check.csv")
    assert len(rows) == 45
    for r in rows:
        assert r["r_pu_zynquplus_ohm"] == r["r_pu_kintexuplus_ohm"] and r["r_pd_zynquplus_ohm"] == r["r_pd_kintexuplus_ohm"]


def test_net_lengths_groups_and_rgmii_clusters():
    rows = _rows("kr260_net_lengths.csv")
    groups = {r["group"] for r in rows}
    assert {"rgmii_phy2_hpa", "rgmii_phy3_hpb", "pmod_connector_side", "pmod_som_side"} <= groups
    a = sorted(float(r["total_in"]) for r in rows if r["group"] == "rgmii_phy2_hpa")
    b = sorted(float(r["total_in"]) for r in rows if r["group"] == "rgmii_phy3_hpb")
    assert sum(1 for x in a if 7.0 < x < 7.4) >= 12          # length-matched RGMII group on port A
    assert sum(1 for x in b if 2.3 < x < 2.9) >= 12          # and on port B


def test_z0_calibration_records_both_solvers():
    z = json.loads((R / "z0.json").read_text())
    assert 3.0 < z["calibrated_laminate_dk"] < 3.5 and 4.5 < z["calibrated_with_fdm2d"]["laminate_dk"] < 5.5
    assert abs(z["microstrip_top"]["agreement_pct"]) > 10        # the disagreement is recorded, not hidden
    for v in z["stripline_from_chart_gaps"].values():
        assert 3.0 < v["dk"] < 4.5


def test_carrier_run_proposals():
    d = json.loads((R / "kr260_b58a_trigger_carrier_data.check.json").read_text())
    best = {p["group"]: p["best"] for p in d["proposals"] if p["group"].startswith("rgmii")}
    assert best["rgmii_a_tx"]["rs_ohm"] == 27.0 and best["rgmii_b_tx"]["rs_ohm"] == 22.0
