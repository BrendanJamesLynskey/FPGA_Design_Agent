"""Brief 155: the off-chip I/O model (flow/offchip_model.py), its IBIS-derived data and the advisory check (flow/offchip_check.py).

The solver is checked against the analytic lattice (bounce) diagram, and against the owner's Signal Integrity ``tline.bounce`` when
that folder is present. The driver data is checked against the IBIS 20-80 % times it was calibrated to and against what AMD's
documents say (DCI outputs hold 40/48/60 ohm; LVCMOS output resistance falls as DRIVE rises).
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest
import yaml

from flow import offchip_check as C, offchip_model as M
from agent.graph import spec_schema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import ibis_extract as X  # noqa: E402

SI_TLINE = Path("/home/brendan/Claude_sandbox/Matrix_Articles/si_models/tline.py")


# --- the IBIS reader ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tok,val", [("28.6700mA", 0.02867), ("0.25nS", 0.25e-9), ("0.0S", 0.0), ("1.84p", 1.84e-12), ("-3.3000V", -3.3),
                                     ("10.8970uA", 10.897e-6), ("1.0000M", 1e6), ("5.23pF", 5.23e-12), ("3.3", 3.3), ("553.13f", 553.13e-15),
                                     ("187.5000ps", 187.5e-12), ("0.0V", 0.0)])
def test_ibis_numbers(tok, val):
    assert X.num(tok) == pytest.approx(val, rel=1e-9, abs=1e-18)


def test_library_has_the_models_and_their_sources():
    lib = M.library()
    assert {"artix7", "zynq", "zynquplus"} == set(lib["_source"])
    assert lib["_source"]["artix7"]["File Rev"] == "2.8" and lib["_source"]["zynquplus"]["IBIS ver"] == "5.1"
    assert M.model_key("artix7", "LVCMOS33", 8, "SLOW") == "artix7:LVCMOS33_S_8_HR"
    assert M.model_key("zynquplus", "LVCMOS33", 12, "FAST", "HD") == "zynquplus:HD_LVCMOS33_F_12"
    assert M.model_key("zynquplus", "LVCMOS33", 12, "FAST", "HP") is None        # no 3.3 V in a HP bank
    assert M.model_key("zynq", "LVCMOS18", 6, "MEDIUM", "HP") is None             # 7-series HP has no MEDIUM
    assert M.source_for("artix7:LVCMOS33_S_8_HR")["model"] == "LVCMOS33_S_8_HR"


# --- the solver against the lattice diagram ---------------------------------------------------------------------------------------

def _at(res, t):
    i = min(range(len(res.t)), key=lambda k: abs(res.t[k] - t))
    return res.v_rx[i]


@pytest.mark.parametrize("rout,rl", [(20.0, None), (20.0, 100.0), (80.0, None), (50.0, None), (30.0, 25.0), (10.0, 200.0)])
def test_solver_reproduces_the_bounce_diagram(rout, rl):
    vcc = 3.3
    drv = M.LinearDriver(vcc, rout, t_ramp=40e-12)
    line = M.Line(50.0, 6.0)
    res = M.simulate(drv, line, M.Load(c_pf=0.001, r_gnd=rl), 0.0, "r", dt_target=10e-12)
    zl = math.inf if rl is None else rl
    ref = M.bounce(rout, 50.0, zl, n=6)
    T = line.delay_s
    for k, step in enumerate(ref["steps"][:4]):
        # after the k-th arrival and its reflection, before the next one (the middle of the plateau)
        got = _at(res, (2 * k + 1) * T + 0.9 * T)
        assert got == pytest.approx(vcc * step["v_load"], abs=0.01 * vcc), (k, got, vcc * step["v_load"])
    assert res.v_rx[-1] == pytest.approx(vcc * ref["v_final"], abs=0.01)


def test_series_resistor_is_a_source_impedance_change():
    """A linear 20 ohm driver plus 30 ohm series resistor behaves as a 50 ohm driver: one clean step, no reflections."""
    drv = M.LinearDriver(3.3, 20.0, t_ramp=40e-12)
    res = M.simulate(drv, M.Line(50.0, 6.0), M.Load(c_pf=0.001), 30.0, "r", dt_target=10e-12)
    T = M.Line(50.0, 6.0).delay_s
    assert _at(res, 1.9 * T) == pytest.approx(3.3, abs=0.03)
    assert res.metrics["over_vcco_v"] < 0.03


@pytest.mark.skipif(not SI_TLINE.is_file(), reason="the owner's si_models folder is not on this machine")
def test_bounce_matches_the_owners_tline():
    spec = importlib.util.spec_from_file_location("si_tline", SI_TLINE)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SI_TLINE.parent.parent))
    try:
        spec.loader.exec_module(mod)
    except Exception as e:                                  # pragma: no cover - the owner's module needs its package context
        pytest.skip(f"cannot import tline: {e}")
    for zs, zl in [(20, 1e12), (80, 1e12), (30, 25), (50, 50)]:
        a, b = M.bounce(zs, 50, zl, 8), mod.bounce(zs, 50, zl, 8)
        assert [s["v_load"] for s in a["steps"]] == pytest.approx([s["v_load"] for s in b["steps"]], rel=1e-9)


def test_critical_length_follows_the_sixth_rule():
    # 1 ns rise on FR-4 (er_eff 3.2, 167.6 mm/ns... v = c/sqrt(3.2)): v*tr/12
    v = M.C0 / math.sqrt(3.2)
    assert M.critical_length_in(1e-9) == pytest.approx(v * 1e-9 / 12 / M.INCH, rel=1e-9)
    assert M.electrically_short(1e-9, 0.01, v)["lumped_by_sixth_rule"] is True
    assert M.electrically_short(1e-9, 0.1, v)["lumped_by_sixth_rule"] is False


# --- the IBIS-derived driver ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["artix7:LVCMOS33_S_8_HR", "artix7:LVCMOS33_F_16_HR", "artix7:LVCMOS18_S_12_HR", "zynquplus:HD_LVCMOS33_S_12",
                                 "zynquplus:HP_LVCMOS18_M_8"])
@pytest.mark.parametrize("corner", M.CORNERS)
def test_calibrated_ramp_reproduces_the_ibis_edge_time(key, corner):
    d = M.get_driver(key, corner)
    for edge, target in (("r", d.t2080_r), ("f", d.t2080_f)):
        assert M._fixture_2080(d, edge, d.ramp(edge)) == pytest.approx(target, rel=0.03)


def test_output_resistance_falls_with_drive_and_spreads_over_corners():
    r = {}
    for drive in (4, 8, 12, 16):
        for c in M.CORNERS:
            d = M.get_driver(M.model_key("artix7", "LVCMOS33", drive, "FAST"), c)
            r[drive, c] = M.r_launch(d, 50.0)
    for c in M.CORNERS:
        assert r[4, c]["r_pu"] > r[8, c]["r_pu"] > r[12, c]["r_pu"] > r[16, c]["r_pu"]
        assert r[4, c]["r_pd"] > r[8, c]["r_pd"] > r[12, c]["r_pd"] > r[16, c]["r_pd"]
    for drive in (4, 8, 12, 16):
        assert r[drive, "min"]["r_pu"] > r[drive, "typ"]["r_pu"] > r[drive, "max"]["r_pu"]      # weak > typical > strong
    # pull-up and pull-down are not the same resistance: that asymmetry is why a match is only approximate
    assert abs(r[12, "typ"]["r_pu"] - r[12, "typ"]["r_pd"]) > 2.0
    # no LVCMOS33 DRIVE gives 50 ohm: the closest (8 mA) is about 40 ohm typical, 25-60 ohm over corners
    assert 30 < r[8, "typ"]["r_pu"] < 50 and r[8, "max"]["r_pd"] < 35 and r[8, "min"]["r_pd"] > 55


def test_dci_outputs_hold_their_nominal_impedance_over_corners():
    """Impedance-controlled outputs (HP SSTL15 DCI, UltraScale+ RDRV_40/48/60) stay within 5 % of 40/48/60 ohm at every corner."""
    for nominal in (40, 48, 60):
        for c in M.CORNERS:
            r = M.r_mid(M.get_driver(f"zynquplus:HP_SSTL15_DCI_F_OUT{nominal}", c))
            assert r["r_pu"] == pytest.approx(nominal, rel=0.05) and r["r_pd"] == pytest.approx(nominal, rel=0.05)


def test_lvcmos_open_line_overshoots_and_a_series_resistor_cures_it():
    """The textbook case on real data: DRIVE 16 FAST into an open 50 ohm line rings far past the rail; with 33 ohm in series it does not."""
    mf = "artix7"
    bad = C.evaluate(mf, "HR", "LVCMOS33", 16, "FAST", 0.0, "none", 50.0, 10.0, 5.0)
    fixed = C.evaluate(mf, "HR", "LVCMOS33", 16, "FAST", 47.0, "none", 50.0, 10.0, 5.0)
    assert bad["worst_over_vcco_v"] > 1.0                      # unclamped receiver, strong corner
    assert fixed["worst_over_vcco_v"] < 0.1
    assert fixed["min_first_incident_margin_v"] is not None and fixed["min_first_incident_margin_v"] > 0.2
    assert bad["min_ringback_margin_v"] < 0


def test_weak_drive_fails_the_first_incident_wave():
    """DRIVE 4 launches under half the swing into 50 ohm: the open receiver waits for the reflection (first-incident margin < 0)."""
    ev = C.evaluate("artix7", "HR", "LVCMOS33", 4, "FAST", 0.0, "none", 50.0, 10.0, 5.0)
    assert ev["min_first_incident_margin_v"] < 0 and not ev["lumped"]
    # the same driver on a short stub is fine: the edge is slower than the round trip, the receiver just follows it
    short = C.evaluate("artix7", "HR", "LVCMOS33", 4, "SLOW", 0.0, "none", 50.0, 0.5, 5.0)
    assert short["lumped"] and short["min_first_incident_margin_v"] is None


def test_first_incident_matches_the_analytic_launch_divider():
    """For a linear driver the first-incident level is 2*Z0/(Z0+R)*VCC on an open line (lattice step 0)."""
    d = M.LinearDriver(3.3, 80.0, t_ramp=100e-12)
    fi = M.first_incident(d, M.Line(50.0, 6.0), M.Load(c_pf=0.001), 0.0, "r")
    assert fi["v_first_incident"] == pytest.approx(3.3 * 2 * 50 / 130, abs=0.03)
    assert fi["margin_v"] == pytest.approx(fi["v_first_incident"] - 2.0, abs=1e-9)


# --- the spec section and the check --------------------------------------------------------------------------------------------------

GOOD = {"name": "dac", "ports": ["dac_d[*]"], "direction": "output", "iostandard": "LVCMOS33", "line": {"z0_ohm": 50, "length_in": 10},
        "load": {"c_pf": 5.0, "receiver_std": "LVCMOS33"}, "priority": "balanced"}


def test_spec_schema_accepts_and_rejects():
    assert C.off_chip_errors([GOOD]) == []
    assert C.off_chip_errors(None) == []
    bad = dict(GOOD, line={"length_in": -1}, priority="speed", colour="red")
    errs = C.off_chip_errors([bad, dict(GOOD)])
    joined = " ".join(errs)
    assert "unknown key 'colour'" in joined and "priority" in joined and "positive length_in" in joined and "duplicate" in joined
    assert any("load.c_pf" in e for e in C.off_chip_errors([{"name": "x", "ports": ["a"], "direction": "output"}]))
    assert C.off_chip_errors([]) != []


def test_spec_validate_calls_the_off_chip_rules():
    spec = {"name": "x", "off_chip": [dict(GOOD, priority="nope")]}
    assert any("off_chip" in e and "priority" in e for e in spec_schema.validate(spec, need_proof=False))


def test_xdc_parser_reads_dict_and_plain_forms():
    t = ("set_property -dict {PACKAGE_PIN A1 IOSTANDARD LVCMOS33 DRIVE 16 SLEW FAST} [get_ports {dac_d[0]}]\n"
         "set_property DRIVE 8 [get_ports sclk]\n# set_property DRIVE 4 [get_ports ignored]\n")
    p = C.parse_xdc(t)
    assert p["dac_d[0]"] == {"PACKAGE_PIN": "A1", "IOSTANDARD": "LVCMOS33", "DRIVE": "16", "SLEW": "FAST"}
    assert p["sclk"] == {"DRIVE": "8"} and "ignored" not in p


XDC_FAST16 = "".join(f"set_property -dict {{PACKAGE_PIN A{i} IOSTANDARD LVCMOS33 DRIVE 16 SLEW FAST}} [get_ports {{dac_d[{i}]}}]\n" for i in range(2))


def test_check_flags_an_xdc_value_the_model_contradicts():
    res = C.check({"off_chip": [GOOD]}, XDC_FAST16, "7series", "HR")
    codes = {(f["code"], f["severity"]) for f in res["findings"]}
    assert ("OFFCHIP-OVERSHOOT", "contradicts-model") in codes
    assert ("OFFCHIP-RINGBACK", "contradicts-model") in codes
    f = next(f for f in res["findings"] if f["code"] == "OFFCHIP-OVERSHOOT")
    assert f["numbers"]["source"]["model"] == "LVCMOS33_F_16_HR" and f["numbers"]["worst_over_v"] > 1.0 and "DS181" in f["text"]
    assert res["advisory"] is True and all(x["severity"] in ("advisory", "contradicts-model") for x in res["findings"])


def test_check_is_quiet_for_a_matched_choice():
    g = dict(GOOD, external={"series_ohm": 47})
    xdc = "set_property -dict {PACKAGE_PIN A1 IOSTANDARD LVCMOS33 DRIVE 16 SLEW FAST} [get_ports {dac_d[0]}]\n"
    res = C.check({"off_chip": [g]}, xdc, "7series", "HR")
    assert res["findings"] == [], res["findings"]


def test_check_default_drive_and_slew_are_the_tool_defaults():
    """No DRIVE or SLEW in the XDC: 12 mA and SLOW (UG471), and the finding says the ports were defaulted."""
    xdc = "set_property -dict {PACKAGE_PIN A1 IOSTANDARD LVCMOS33} [get_ports {dac_d[0]}]\n"
    res = C.check({"off_chip": [dict(GOOD, line={"z0_ohm": 50, "length_in": 14})]}, xdc, "7series", "HR")
    texts = " ".join(f["text"] for f in res["findings"])
    assert "DRIVE 12 SLEW SLOW" in texts or res["findings"] == []


def test_check_illegal_drive_vcco_and_missing_data():
    xdc = ("set_property -dict {PACKAGE_PIN A1 IOSTANDARD LVCMOS33 DRIVE 24 SLEW FAST} [get_ports {dac_d[0]}]\n"
           "set_property -dict {PACKAGE_PIN B1 IOSTANDARD LVCMOS18 DRIVE 8 SLEW SLOW} [get_ports other]\n")
    g = dict(GOOD, line="short", vcco=1.8)
    res = C.check({"off_chip": [g]}, xdc, "7series", "HR")
    codes = [f["code"] for f in res["findings"]]
    assert "OFFCHIP-DRIVE-ILLEGAL" in codes            # 24 mA does not exist for LVCMOS33
    assert "OFFCHIP-VCCO" in codes                      # LVCMOS33 on a bank the group says is 1.8 V
    assert "OFFCHIP-NO-LOAD-DATA" in codes              # `other` sets DRIVE/SLEW and no group names it
    # LVCMOS33 outputs do not exist in a HP bank
    res2 = C.check({"off_chip": [dict(GOOD, line="short", bank_type="HP")]}, "set_property -dict {IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {dac_d[0]}]\n",
                   "ultrascale_plus", "HP")
    assert any(f["code"] == "OFFCHIP-VCCO" and "do not exist" in f["text"] for f in res2["findings"])


def test_check_bank_vcco_conflict_and_translator():
    g1 = dict(GOOD, name="a", ports=["pa"], bank=14, line="short", vcco=3.3)
    g2 = dict(GOOD, name="b", ports=["pb"], bank=14, line="short", iostandard="LVCMOS18", vcco=1.8, load={"c_pf": 5, "receiver_std": "LVCMOS18"})
    xdc = ("set_property -dict {IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports pa]\nset_property -dict {IOSTANDARD LVCMOS18 DRIVE 8 SLEW SLOW} [get_ports pb]\n")
    res = C.check({"off_chip": [g1, g2]}, xdc, "7series", "HR")
    assert any("one VCCO per bank" in f["text"] for f in res["findings"])
    g3 = dict(GOOD, name="c", ports=["pa"], line="short", load={"c_pf": 5, "receiver_std": "LVCMOS18"})
    res3 = C.check({"off_chip": [g3]}, xdc.split("\n")[0] + "\n", "7series", "HR")
    assert any(f["code"] == "OFFCHIP-VCCO" and f["severity"] == "contradicts-model" and "level translator" in f["text"] for f in res3["findings"])


def test_check_differential_input_termination_by_family():
    g = {"name": "lvds_in", "ports": ["d_p", "d_n"], "direction": "input", "iostandard": "LVDS_25"}
    seven = "set_property -dict {IOSTANDARD LVDS_25} [get_ports {d_p d_n}]\n"
    res = C.check({"off_chip": [g]}, seven, "7series", "HR")
    assert any(f["code"] == "OFFCHIP-DIFF-TERM" and "DIFF_TERM " in f["text"] + " " for f in res["findings"])
    ok = "set_property -dict {IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {d_p d_n}]\n"
    assert C.check({"off_chip": [g]}, ok, "7series", "HR")["findings"] == []
    us = C.check({"off_chip": [dict(g, iostandard="LVDS")]}, "set_property -dict {IOSTANDARD LVDS DIFF_TERM TRUE} [get_ports {d_p d_n}]\n", "ultrascale_plus", "HP")
    assert any("DIFF_TERM_ADV" in f["text"] for f in us["findings"])      # the 7-series name is the wrong property on UltraScale+


def test_proposal_for_50_ohm_with_a_22_ohm_series_resistor():
    """With a fixed 22 ohm external series resistor on LVCMOS18 (HP) the proposal picks a DRIVE whose R_out + 22 is near Z0, and it passes."""
    g = {"name": "p", "ports": ["x"], "iostandard": "LVCMOS18", "line": {"z0_ohm": 50, "length_in": 8}, "load": {"c_pf": 5}, "external": {"series_ohm": 22},
         "priority": "emi"}
    p = C.propose(g, "ultrascale_plus", "HP", max_sims=6)
    assert p["best"] is not None and p["best"]["rs_ohm"] == 22.0 and p["best"]["pass"]
    assert p["best"]["static_mismatch"] < 0.3 and p["best"]["first_incident_margin_v"] > 0


# --- the independent check against the waveforms inside the IBIS files ----------------------------------------------------------------

def test_committed_fixture_check_bounds():
    """results/155_offchip/ibis_fixture_check.json (tools/ibis_fixture_check.py): the driver into IBIS's 50 ohm fixture reproduces the final level to 1 %
    and the waveform to 20 % rms of the swing at every corner of the eight models checked (the calibration only used the 20-80 % time)."""
    import json
    d = json.loads((ROOT / "results/155_offchip/ibis_fixture_check.json").read_text())
    assert len(d["models"]) == 8
    for key, corners in d["models"].items():
        for c, r in corners.items():
            assert abs(r["final_error_pct"]) < 1.0, (key, c, r)
            assert r["rms_error_pct_of_final"] < 20.0, (key, c, r)


IBIS_A7 = Path("/opt/Xilinx/2025.2/data/parts/xilinx/artix7/public/ibis/artix7.ibs")


@pytest.mark.skipif(not IBIS_A7.is_file(), reason="Vivado's IBIS files are not on this machine")
def test_fixture_waveform_live_for_one_model():
    sys.path.insert(0, str(ROOT / "tools"))
    import ibis_fixture_check as F
    lines = X.split_models(IBIS_A7.read_text(errors="replace"))["LVCMOS33_F_8_HR"]
    w = F.waveform(lines, 50.0, 0.0, "Rising")
    assert len(w) > 50
    d = M.get_driver("artix7:LVCMOS33_F_8_HR", "typ")
    sim = M._fixture_wave(d, "r", d.ramp("r"), 5e-12, 3000, 50.0)
    assert sim[-1] == pytest.approx(w[-1][1], rel=0.01)
