"""Brief 126: build lat_all3_bypass. Structure (nothing is copied: each source is one of the two parent builds' files), the board driver's pre-registered verdict against a fake result
(results/b126/preregistration.md), and the reference numbers against the two recorded board runs the prediction is made from. Nothing here touches a board or says anything about what the GT does."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from designs.b96_kr260_10g.host import b126_all3_bypass as f126

DESIGN = Path(__file__).resolve().parents[1]
ROOT = DESIGN.parents[1]


def _y(name: str) -> dict:
    return yaml.safe_load((DESIGN / name / "build.yaml").read_text())


def test_build_is_lat_all3_cuts_plus_rm_gp_bypass_core() -> None:
    new, a3, byp = _y("lat_all3_bypass"), _y("lat_all3"), _y("rm_gp_bypass")
    p = "designs/b96_kr260_10g/"
    assert new["top"] == a3["top"] == byp["top"] and new["part"] == a3["part"] and new["constraints"] == a3["constraints"] == byp["constraints"]
    assert new["ip_tcl"] == byp["ip_tcl"] == [p + "ip/amd_ip_bypass.tcl"]                       # both GT buffers bypassed
    # the generics are lat_all3's (default receive path, go-pulse register removed), not rm_gp_bypass's (rate matcher)
    assert new["generics"] == a3["generics"] and new["generics"]["RATE_MATCH"] == "1'b0" and new["generics"]["GO_REG"] == "1'b0"
    assert "RM_OWN" not in new["generics"]
    srcs = new["sources"]
    # the two logic cuts are lat_all3's files, the bypass wrapper files are rm_gp_bypass's, and nothing is a copy under lat_all3_bypass/
    assert p + "lat_all3/rtl/trade64.sv" in srcs and p + "lat_all3/rtl/tx_path.sv" in srcs
    assert all(p + "rm_gp_bypass/rtl/" + n in srcs for n in ("b96_core.sv", "gt_bp_gate.sv", "gt_bp_ctl.sv"))
    assert not any("lat_all3_bypass/" in s for s in srcs) and not (DESIGN / "lat_all3_bypass" / "rtl").exists()
    # every other source is the base's, listed in at least one parent (rate_match_gp.sv only in rm_gp_bypass: b96_core.sv names it in a generate branch this build does not take), and every source exists
    base = [s for s in srcs if "/lat_all3/" not in s and "/rm_gp_bypass/" not in s]
    assert all(s in a3["sources"] or s in byp["sources"] for s in base)
    assert all((ROOT / s).is_file() for s in srcs)
    # the union of both parents' sources and nothing else
    assert set(srcs) == (set(a3["sources"]) - {p + "rtl/b96_core.sv", p + "rtl/trade64.sv", p + "rtl/tx_path.sv"}) | {p + "lat_all3/rtl/trade64.sv", p + "lat_all3/rtl/tx_path.sv"} | \
        {p + "rm_gp_bypass/rtl/" + n for n in ("b96_core.sv", "gt_bp_gate.sv", "gt_bp_ctl.sv")} | {p + "rtl/rate_match_gp.sv"}


def test_architecture_names_every_build_block() -> None:
    a = yaml.safe_load((DESIGN / "lat_all3_bypass" / "architecture.yaml").read_text())
    names = {b["name"] for b in a["blocks"]}
    assert {"gth_wiz", "gt_bp_gate", "gt_bp_ctl", "rx_path_legacy", "trade64", "tx_path", "b96_core"} <= names
    assert "u_rs" in a["reset"]["synchronisers"]


def _stage3(e=16.0, l=38.0, ok=True, failed=0, link=True, fibre=None):
    d = {"link_up": link, "restarts": {"restarts": 100, "failed_to_lock": failed, "E_min_per_link": {"median": e}, "L_min_per_link": {"median": l}},
         "safety": {"ok": ok, "failing_counters": [] if ok else ["late"]}}
    if fibre is not None:
        d["fibre_one_way_ns"] = fibre
    return d


GOOD = {"n": 20, "failed_to_lock": 0, "controllers_done_at_link_up": True, "controller_error_seen": False, "gave_up_seen": False}
FEAT = {"gt_bypass": 1, "rate_match": 0}


def test_verdict_pass_warn_fail_abort() -> None:
    v = f126.verdict(_stage3(), GOOD, True, FEAT)
    assert v["result"] == "PASS" and v["E_drop_clocks"] == pytest.approx(4.0) and v["L_drop_clocks"] == pytest.approx(8.0) and v["D_from_medians"] == pytest.approx(6.0)
    assert v["T2T_clocks_L_minus_E"] == pytest.approx(22.0) and v["T2T_ns_L_minus_E_minus_fibre"] == pytest.approx(22 * 6.2061 - 0.8324425559765083)
    assert f126.verdict(_stage3(e=16.5, l=39.0), GOOD, True, FEAT)["result"] == "PASS"             # drop 3.5, D 6, inside the bands
    w = f126.verdict(_stage3(e=17.5, l=41.0), GOOD, True, FEAT)                                    # drop 2.5 (short of 3.4), D 6
    assert w["result"] == "WARN" and "outside the predicted" in w["reasons"][0]
    w = f126.verdict(_stage3(e=16.0, l=41.0), GOOD, True, FEAT)                                    # D 9 outside 5 to 7
    assert w["result"] == "WARN" and "D = L - 2E" in w["reasons"][0]
    assert f126.verdict(_stage3(e=19.0, l=44.0), GOOD, True, FEAT)["result"] == "FAIL"             # fall 1.0 < 1.5
    f = f126.verdict(_stage3(e=17.0, l=44.0), GOOD, True, FEAT)                                    # fall 3.0 but L - E = 27 is not below lat_all3's 26
    assert f["result"] == "FAIL" and any("not below" in r for r in f["reasons"])
    assert f126.verdict(_stage3(ok=False), GOOD, True, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(failed=1), GOOD, True, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(), GOOD, False, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(), dict(GOOD, controller_error_seen=True), True, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(), dict(GOOD, failed_to_lock=2), True, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(), dict(GOOD, controllers_done_at_link_up=False), True, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(), dict(GOOD, gave_up_seen=True), True, FEAT)["result"] == "FAIL"
    assert f126.verdict(_stage3(), GOOD, True, FEAT, {"tx_gave_up": 1})["result"] == "FAIL"
    assert f126.verdict(_stage3(), GOOD, True, {"gt_bypass": 0, "rate_match": 0})["result"] == "ABORT"      # buffers on
    assert f126.verdict(_stage3(), GOOD, True, {"gt_bypass": 1, "rate_match": 1})["result"] == "ABORT"      # a rate-matched build
    assert f126.verdict(_stage3(link=False), GOOD, True, FEAT)["result"] == "ABORT"


def test_longer_lead_moves_the_reference() -> None:
    """A lead 1.24 ns longer (one clock) raises E by 1 and L by 2: the same build reads E 17, L 40 and still passes."""
    v = f126.verdict(_stage3(e=17.0, l=40.0, fibre=0.8324425559765083 + 6.2061), GOOD, True, FEAT)
    assert v["result"] == "PASS" and v["E_drop_clocks"] == pytest.approx(4.0) and v["L_drop_clocks"] == pytest.approx(8.0)


def test_reference_numbers_are_the_97c_board_run_and_the_prediction_is_the_96f1b_effect() -> None:
    a = json.loads((ROOT / "results" / "b97c" / "hw" / "20261118_194221" / "all3" / "stage3.json").read_text())
    r = a["restarts"]
    assert (f126.REF_E, f126.REF_L, f126.REF_D) == (r["E_min_per_link"]["median"], r["L_min_per_link"]["median"], a["D_clocks_from_medians_of_minima"])
    assert f126.REF_FIBRE_NS == pytest.approx(a["fibre_one_way_ns"])
    b0 = json.loads((ROOT / "results" / "b96e" / "hw" / "20261119_231251" / "rm_gp" / "stage3.json").read_text())["restarts"]
    b1 = json.loads((ROOT / "results" / "b96f1" / "hw" / "20261120_215255" / "rm_gp_bypass" / "stage3.json").read_text())["restarts"]
    drop = b0["E_min_per_link"]["median"] - b1["E_min_per_link"]["median"]
    assert drop == f126.MEASURED_E_DROP == 4.0 and f126.PRED_DROP[0] <= drop <= f126.PRED_DROP[1]
    assert b0["L_min_per_link"]["median"] - b1["L_min_per_link"]["median"] == 2 * drop      # L moves by twice E: the loop crosses the transceiver twice
    # the prediction written in the pre-registration: E 16.0, L 38.0, D 6.0, L - E 22
    e = f126.REF_E - drop
    assert (e, 2 * e + f126.REF_D, (2 * e + f126.REF_D) - e) == (16.0, 38.0, 22.0)
    assert "22 clocks" in (ROOT / "results" / "b126" / "preregistration.md").read_text()


def test_lock_prefix_96f_is_what_the_bench_and_the_reservation_accept(tmp_path) -> None:
    import re
    sh = (ROOT.parent.parent / "_handoff" / "fpga_agent" / "run_126_stage1.sh")
    if not sh.exists():
        pytest.skip("board script lives outside the repo")
    txt = sh.read_text()
    assert 'TEXT="96F: ' in txt and "b126_all3_bypass" in txt and "lat_all3_bypass" in txt
    assert re.search(r"^EXPECT_STAMP=[0-9a-f]{8}$", txt, re.M)
