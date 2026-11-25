"""Brief 164: the off-chip check reads the spec's family, gives two answers per port, and the committed data behind the signal-integrity figures is consistent."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from flow import offchip_check as C

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results/164_si_expertise"
XDC = "set_property -dict {IOSTANDARD LVCMOS18 DRIVE 12 SLEW FAST} [get_ports {d[*]}]\n"


def _spec(**over):
    g = {"name": "link", "ports": ["d[*]"], "direction": "output", "iostandard": "LVCMOS18", "vcco": 1.8, "bank_type": "HP",
         "line": {"z0_ohm": 50, "length_in": 3.0}, "load": {"c_pf": 5.0, "receiver_std": "LVCMOS18"}, "priority": "edge_rate", "ui_ns": 4.0}
    g.update(over)
    return {"family": "zynquplus", "part": "xck26-sfvc784-2LV-c", "bank_type": "HP", "off_chip": [g]}


def test_resolve_target_spec_then_cli_then_default():
    s = _spec()
    assert C.resolve_target(s, None, None, None) == ("zynquplus", "xck26-sfvc784-2LV-c", "HP")
    assert C.resolve_target(s, "artix7", "", "HR") == ("artix7", "xck26-sfvc784-2LV-c", "HR")      # the command line wins where given
    assert C.resolve_target({}, None, None, None) == ("artix7", "", "HR")                           # the old defaults


def test_main_without_flags_equals_main_with_flags(tmp_path):
    spec = tmp_path / "s.yaml"
    spec.write_text(yaml.safe_dump(_spec(line="short", load={"c_pf": 5.0}, ui_ns=1000.0)))
    xdc = tmp_path / "d.xdc"
    xdc.write_text(XDC)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert C.main(["--spec", str(spec), "--xdc", str(xdc), "--json", str(a)]) == 0
    assert C.main(["--spec", str(spec), "--xdc", str(xdc), "--family", "zynquplus", "--part", "xck26-sfvc784-2LV-c", "--bank-type", "HP", "--json", str(b)]) == 0
    ja, jb = json.loads(a.read_text()), json.loads(b.read_text())
    assert ja == jb
    assert ja["target"]["family_class"] == "ultrascale_plus"
    assert ja["check"]["findings"] == [] or all("zynquplus" in f["numbers"].get("source", {}).get("file", "zynquplus") for f in ja["check"]["findings"])
    # the ignored key used to give Zynq-7000 models: the proposals name the UltraScale+ file
    src = ja["proposals"][0]["optimal"]["best"]["source"]
    assert src["file"].startswith("zynquplus/")


def test_board_fixed_validated():
    assert C.off_chip_errors(_spec(board_fixed=True)["off_chip"]) == []
    assert any("board_fixed" in e for e in C.off_chip_errors(_spec(board_fixed="yes")["off_chip"]))


def test_as_built_keeps_the_board_resistor_and_optimal_may_change_it():
    g = _spec(board_fixed=True, line={"z0_ohm": 50, "length_in": 6.0}, external={"series_ohm": 22})["off_chip"][0]
    t = C.propose_two(g, "ultrascale_plus", "HP")
    assert t["applies"] == "as_built" and t["board_fixed"] and t["board_series_ohm"] == 22.0
    assert t["as_built"]["simulated"] and all(r["rs_ohm"] == 22.0 for r in t["as_built"]["simulated"])
    assert len({(r["drive"], r["slew"]) for r in t["as_built"]["simulated"]}) == 15          # every allowed DRIVE x SLEW (5 drives, 3 slews)
    assert any(r["rs_ohm"] != 22.0 for r in t["optimal"]["simulated"])                        # the optimal search is free to change it
    txt = "\n".join(C.proposal_text(t))
    assert "board is fixed" in txt and "as built" in txt and "optimal" in txt


def test_as_built_with_no_resistor_is_zero_ohm_and_says_when_nothing_passes():
    g = _spec(line={"z0_ohm": 50, "length_in": 7.2})["off_chip"][0]
    t = C.propose_two(g, "ultrascale_plus", "HP")
    assert t["applies"] == "both" and t["board_series_ohm"] == 0.0
    asb = t["as_built"]
    assert all(r["rs_ohm"] == 0.0 for r in asb["simulated"])
    assert asb["best"] is None and asb["least_bad"] is not None                               # nothing passes without a resistor on 7.2 in
    assert asb["least_bad"]["fails"] and "margin_to_limit_v" in asb["least_bad"]
    assert "NO setting meets every limit" in "\n".join(C.proposal_text(t))
    assert t["optimal"]["best"] is not None and t["optimal"]["best"]["rs_ohm"] > 0           # a resistor fixes it, as brief 162 found
    assert "DCI" in t["dci"]


# ---- committed results ------------------------------------------------------------------------------------------------------------------

def test_series_r_waveforms_have_limits_and_four_resistors():
    rows = list(csv.DictReader((R / "waveforms_series_r.csv").open()))
    assert {r["series_ohm"] for r in rows} == {"0", "22", "33", "47"}
    assert {r["standard"] for r in rows} == {"LVCMOS33", "LVCMOS18"}
    assert all(r["model"] and r["ibis_file"] and r["file_rev"] for r in rows)
    r33 = [float(r["v_rx_v"]) for r in rows if r["standard"] == "LVCMOS33" and r["series_ohm"] == "0" and r["edge"] == "rise"]
    r33_47 = [float(r["v_rx_v"]) for r in rows if r["standard"] == "LVCMOS33" and r["series_ohm"] == "47" and r["edge"] == "rise"]
    lim = float(next(r["limit_over_v"] for r in rows if r["standard"] == "LVCMOS33"))
    assert max(r33) > lim > max(r33_47)                 # no resistor breaks the data sheet limit on 6 in; 47 ohm stays inside


def test_kr260_two_answers_agree_with_the_committed_162_check():
    d = json.loads((R / "kr260_two_answers.json").read_text())
    chk = json.loads((ROOT / "results/162_kr260_si/kr260_b58a_trigger_carrier_data.check.json").read_text())
    want = {f["group"]: f["numbers"]["worst_over_v"] for f in chk["check"]["findings"] if f["code"] == "OFFCHIP-OVERSHOOT"}
    meas = [p for p in d["ports"] if p["assumption"] == "measured"]
    assert {p["group"] for p in meas} == {"rgmii_a_tx", "rgmii_b_tx"}
    for p in meas:
        assert abs(p["answers"]["xdc"]["worst_over_v"] - want[p["group"]]) < 0.002
        assert p["answers"]["optimal"]["all_limits_met"] and p["answers"]["optimal"]["series_ohm"] > 0
        assert p["answers"]["as_built"]["series_ohm"] == p["board_series_ohm"] == 0
        assert p["answers"]["optimal"]["worst_over_v"] <= d["limit_v"]
    assert {p["assumption"] for p in d["ports"]} == {"assumed", "measured"}


def test_162_carrier_check_without_flags_gives_the_same_findings():
    """The committed run of `offchip_check.py --spec ... --xdc ...` with no --family/--part/--bank-type (the spec's own keys) equals brief 162's run that needed the flags."""
    new = json.loads((R / "kr260_carrier_data_no_flags.check.json").read_text())
    old = json.loads((ROOT / "results/162_kr260_si/kr260_b58a_trigger_carrier_data.check.json").read_text())
    assert new["target"] == {"family": "zynquplus", "part": "xck26-sfvc784-2LV-c", "bank_type": "HP", "family_class": "ultrascale_plus"}
    assert new["check"] == old["check"] and len(new["check"]["findings"]) == 8
    txt = (R / "kr260_carrier_data_no_flags.check.txt").read_text()
    assert txt.count("OFFCHIP-PROPOSAL") == 9 and "NO setting meets every limit" in txt                     # three groups x (as built, optimal, which applies)
