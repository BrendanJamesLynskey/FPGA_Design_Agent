"""Brief 30, ILA in batch: the captures committed from the board (results/b30/ila_t1/captures, made by flow/bringup.py
through hw_server and ila_capture.tcl) pass T1's own comparison rules, and every seeded fault in the capture or in the
expectation makes the same rules fail. No board or Vivado needed: this checks the checker."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from designs.t1_dimmer_counter import hw_checks as hc
from flow import ila

CAP = Path(__file__).resolve().parents[2] / "results" / "b30" / "ila_t1" / "captures"
PMAP, HWP = CAP / "t1_dimmer_counter_probe_map.txt", CAP / "t1_dimmer_counter_hw_probes.txt"
BY_NAME = {c.name: c for c in hc.CAPTURES}


def load(name: str) -> dict[str, list[int]]:
    return ila.load_capture(CAP / f"t1_dimmer_counter_{name}.csv", PMAP, HWP)


@pytest.mark.parametrize("name", list(BY_NAME))
def test_board_capture_passes(name):
    r = BY_NAME[name].check(load(name))
    assert r["pass"], r["errors"]
    assert len(load(name)["count"]) == 1024            # the ILA depth of the build


def test_seeded_led_glitch_is_caught():
    s = load("pwm_40")
    s["led"][500] ^= 0x0001                            # one LED bit wrong for one clock
    assert not BY_NAME["pwm_40"].check(s)["pass"]


def test_seeded_count_one_clock_early_is_caught():
    s = load("count_write")
    t = s["win_wr"].index(1)
    s["count"][t] = hc.COUNT_WRITTEN                   # the register would have taken the write one clock early
    assert not BY_NAME["count_write"].check(s)["pass"]


def test_seeded_phase_jump_is_caught():
    s = load("pwm_08")
    s["phase"][300] = (s["phase"][300] + 5) % 256
    assert not BY_NAME["pwm_08"].check(s)["pass"]


def test_wrong_expectation_is_caught():
    """The same capture against a model with the wrong duty fails: the duty-0x08 capture is not a duty-0x40 one."""
    r = hc.make_pwm_check(0x40)(load("pwm_08"))
    assert not r["pass"]


def test_truncated_capture_is_caught():
    s = copy.deepcopy(load("pwm_a0"))
    s = {k: v[:900] for k, v in s.items()}
    assert not BY_NAME["pwm_a0"].check(s)["pass"]
