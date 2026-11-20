"""Brief 96F: the loop-timing tracker model and the latency prediction arithmetic (paper study; no RTL, no board)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from designs.b96_kr260_10g.model import loop_timing as lt

ROOT = Path(__file__).resolve().parents[3]
REC = ROOT / "results" / "b96f"


def test_sdm_resolution_is_below_a_thousandth_of_a_ppm() -> None:
    assert 0.0008 < lt.LSB_PPM < 0.001           # 2**-24 / 66 of the VCO, UG576 Equations 2-5 and 2-6


def test_fll_then_pi_tracks_a_static_offset() -> None:
    p = replace(lt.Params(), window="centred_ref", pd_res_ns=lt.T_CLK_NS / 4)
    r = lt.simulate(lambda t: 73.4, 1.0, p)
    assert abs(r["u_final_ppm"] - 73.4) < 0.05
    assert r["rms_phase_ns_second_half"] < 1.0


def test_one_clock_phase_detector_cannot_hold_the_half_range() -> None:
    # at 1 clock of resolution the phase sits anywhere in +-3.1 ns of the set point; at a quarter clock it is held to well under 1 ns
    base = replace(lt.Params(), window="centred_ref", fn_hz=30.0)
    q4 = lt.simulate(lambda t: 20.0, 2.0, replace(base, pd_res_ns=lt.T_CLK_NS / 4))
    assert q4["rms_phase_ns_second_half"] < 0.5


def test_fixed_reference_has_a_dead_zone_near_nominal_unless_txpi_biased() -> None:
    fixed = lt.simulate(lambda t: -1.0, 2.0, replace(lt.Params(), window="fixed_ref"))
    biased = lt.simulate(lambda t: -1.0, 2.0, replace(lt.Params(), window="fixed_ref_txpi"))
    assert fixed["window_hops"] > 3 and biased["window_hops"] == 0


def test_loopback_needs_a_holdover_guard() -> None:
    kick = ((1.0, 6.0),)
    p = replace(lt.Params(), window="centred_ref", seed=4)
    free = lt.simulate(lambda t: 0.0, 3.0, p, loopback=True, kicks=kick)
    held = lt.simulate(lambda t: 0.0, 3.0, replace(p, guard_ppm=5.0), loopback=True, kicks=kick)
    assert free["u_max_ppm"] > 150.0          # the integral runs away: the kick has no frequency cause the loop can remove
    assert held["u_max_ppm"] <= 5.01 and held["guard_hit_ticks"] > 0


def test_the_existing_frequency_counter_is_an_acquisition_detector_only() -> None:
    r = lt.counter_window_controller(lambda t: 50.0, 1.0)
    assert r["window_ms"] > 100 and r["peak_abs_phase_ns"] > 1000.0


def test_closed_loop_bandwidth_numbers() -> None:
    assert 245 < lt.closed_loop(100.0, 1.0)["f_minus3dB_hz"] < 252 and lt.closed_loop(100.0, 1.0)["peaking_db"] < 1.5


def test_committed_records_match_the_code(tmp_path) -> None:
    rec = json.loads((REC / "loop_timing_model.json").read_text())
    r = lt.simulate(lambda t: 50.0, 2.0, replace(lt.Params(), window="centred_ref"))
    r.pop("trace")
    assert rec["A_static_offsets"]["centred_ref"]["+50"] == r
    tmp = tmp_path / "pred.json"
    subprocess.run([sys.executable, str(REC / "latency_prediction.py"), str(tmp)], capture_output=True, text=True, check=True)
    assert json.loads(tmp.read_text()) == json.loads((REC / "latency_prediction.json").read_text())
