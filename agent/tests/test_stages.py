"""The stage machine decides from the flow's gate output only (05b)."""

import copy
import json
from pathlib import Path

from agent.graph.stages import MACHINE, classify, exit_check, route_failure

GATES = {"stages": {
    "rtl": {"ran": True, "gates": {"rtl_methodology_no_critical": True}},
    "post_synth": {"ran": True, "gates": {"post_synth_no_unconstrained_endpoints": True,
                                          "post_synth_methodology_no_critical": True,
                                          "post_synth_drc_clean": True, "post_synth_qor_assessment": True}},
    "post_place": {"ran": True, "gates": {"post_place_hold": True}},
    "post_route": {"ran": True, "gates": {"setup": True, "hold": True, "pulse_width": True,
                                          "no_unconstrained_endpoints": True, "drc_clean": True,
                                          "methodology_no_critical": True, "cdc_no_critical": True,
                                          "power_junction_ok": True}},
    "bitstream": {"ran": True, "gates": {"bitstream_present": True}}}}


def test_machine_matches_methodology_order():
    assert [s.n for s in MACHINE] == list(range(10))


def test_timing_gate_and_route_back():
    g = copy.deepcopy(GATES)
    assert exit_check(MACHINE[6], {"gates_base": g})[0]
    g["stages"]["post_route"]["gates"]["setup"] = False
    ok, fails = exit_check(MACHINE[6], {"gates_base": g})
    assert not ok and fails == ["post_route:setup"]
    assert route_failure(MACHINE[6], classify(MACHINE[6], fails)) == 2


def test_model_opinion_is_never_an_input():
    # a stage passes only on tool evidence; "the model says it is done" is not a field exit_check reads
    assert not exit_check(MACHINE[2], {"model_says_done": True})[0]
    assert not exit_check(MACHINE[0], {"spec": {"ports": []}, "signed_off": False})[0]
    assert exit_check(MACHINE[0], {"spec": {"ports": []}, "signed_off": True})[0]


def test_route_only_to_allowed_stages():
    assert route_failure(MACHINE[4], "constraints") == 3
    assert route_failure(MACHINE[3], "timing") == 3        # 3 may not jump to 6: it retries


def test_real_t1_gates_pass_if_present():
    f = Path(__file__).resolve().parents[2] / "designs" / "t1_dimmer_counter" / "build" / "base" / "gates.json"
    if f.is_file():
        g = json.loads(f.read_text())
        for n in (4, 5, 6, 7, 8):
            assert exit_check(MACHINE[n], {"gates_base": g, "standards": {"rules": []}})[0], n


def test_bringup_harness_error_routes_to_tests_role():
    s9 = MACHINE[9]
    why = ["bring-up failed at 'uart_tests': E   ModuleNotFoundError: No module named 'model'"]
    assert classify(s9, why) == "bringup"
    assert route_failure(s9, classify(s9, why)) == 9
    for k in ("ImportError: x", "ERROR collecting tests/test_x_hw.py", "unrecognized arguments: --hw-port"):
        assert classify(s9, [f"bring-up failed at 'uart_tests': {k}"]) == "bringup"


def test_bringup_hardware_failure_still_routes_to_rtl():
    s9 = MACHINE[9]
    why = ["bring-up failed at 'uart_tests': assert 3 == 4"]
    assert classify(s9, why) == "rtl"
    assert route_failure(s9, "rtl") == 2
