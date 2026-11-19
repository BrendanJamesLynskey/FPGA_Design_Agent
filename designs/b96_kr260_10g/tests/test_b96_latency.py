"""The latency tooling of brief 97 on the recorded 96 results: the stage file reconciles with the benches, a stale or wrong stage
file is detected, the budget shows the board's share and the residual, and the loop's keep rule is the flow's, not a model's."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from flow.latency import model as lm
from flow.latency import netlist

DESIGN = Path(__file__).resolve().parents[1]
ROOT = DESIGN.parents[1]
CORE = json.loads((ROOT / "results" / "b96c" / "core_sim.json").read_text())


def test_stage_file_reproduces_the_96c_numbers() -> None:
    r = lm.latency_path(DESIGN, CORE)
    assert r["reconciled"], r["problems"]
    # brief 96C: the simulated worst case (`max` keys) is 13 clocks; the old go-pulse crossing is gone and the rate matcher is the crossing
    assert r["total_clocks"] == 13 and r["total_ns"] == pytest.approx(80.675, abs=0.01)
    by = {s["id"]: s for s in r["stages"]}
    assert "cross_go" not in by
    assert by["rx_ratematch"]["clocks"] == 6 and by["rx_ratematch"]["domain"] == "rx->tx"
    # direction split: receive PCS 1 clock, crossing (rate matcher) 6, transmit clock 6 (MAC, decision, frame source, MAC register, encode, spill)
    assert sum(s["clocks"] for s in r["stages"] if s["domain"] == "rx") == 1
    assert sum(s["clocks"] for s in r["stages"] if s["domain"] == "tx") == 6
    e = lm.latency_path(DESIGN, CORE, path="echo")
    assert e["total_clocks"] == 13 and sum(s["clocks"] for s in e["stages"]) == 13


def test_a_stale_stage_file_is_reported_not_trusted() -> None:
    core = copy.deepcopy(CORE)
    core["tick_to_trade_digital_sim"]["go_to_order_preamble_in_mac_register_clocks"]["max"] = 3      # a design change the file does not know
    core["tick_to_trade_digital_sim"]["gt_rxdata_price_word_to_gt_txdata_order_start_clocks"]["max"] = 14
    r = lm.latency_path(DESIGN, core)
    assert not r["reconciled"] and any("go_to_preamble" in p for p in r["problems"])


def test_unknown_path_and_missing_file_are_refused(tmp_path: Path) -> None:
    with pytest.raises(lm.LatencyError):
        lm.latency_path(DESIGN, CORE, path="nope")
    with pytest.raises(lm.LatencyError):
        lm.load_stages(tmp_path)


def test_budget_never_adds_board_and_simulation_into_one_number() -> None:
    b = lm.latency_budget(DESIGN, CORE, None, ROOT / "results" / "b96")
    bd = b["board"]      # the board record is the pre-96C run (E, L as 97 accepted them); only the digital part is the 96C chain
    assert bd["E_clocks"] == 20 and bd["L_clocks"] == 50
    assert bd["wire_to_wire_clocks"] == pytest.approx(29.9, abs=0.2)           # 50 - 20 - 0.13: the 96 report's "about 30 clocks"
    assert bd["gt_optics_clocks"] == 15                                        # E 20 minus the 5 digital clocks the 96 report counts
    # the residual is shown, and it is the difference of the two accountings
    assert bd["unattributed_clocks"] == pytest.approx(bd["wire_to_wire_clocks"] - 13 - 15, abs=0.2)
    assert b["rows"][-1]["needs_board"] and b["rows"][-1]["stage"] == "gt_tx_rx_optics"
    assert "fs_start" in b["ranking_by_removable_clocks"] and "rx_ratematch" not in b["ranking_by_removable_clocks"]
    assert b["total_removable_digital_clocks_upper_bound"] <= 7


def test_slack_joins_by_stage_and_marks_timing_critical() -> None:
    slack = {"source": "x.dcp", "stages": {"rx_descramble": {"cells": 72, "clock": "rxusr2", "setup_slack_ns": 0.12}, "rx_mac": {"cells": 6, "clock": "txusr2", "setup_slack_ns": 3.0}}}
    r = lm.latency_path(DESIGN, CORE, slack)
    by = {s["id"]: s for s in r["stages"]}
    assert by["rx_descramble"]["timing_critical"] is True and by["rx_mac"]["timing_critical"] is False
    assert by["rx_blk"]["timing_critical"] is None            # no netlist reading for that stage: unknown, not "fine"


def test_tcl_inputs_and_outputs_round_trip() -> None:
    st = lm.load_stages(DESIGN)
    tsv = netlist.stage_tsv(st)
    ids = [l.split("\t")[0] for l in tsv.splitlines()]
    assert "rx_ratematch" in ids and "tx_spill" not in ids              # a stage with no registers is not sent to Vivado
    out = netlist.parse_out("rx_ratematch\t6\ttxusr2\t2.5\t0.04\nrx_blk\t0\t-\t-\t-\n")
    assert out["rx_ratematch"] == {"cells": 6, "clock": "txusr2", "setup_slack_ns": 2.5, "hold_slack_ns": 0.04}
    assert out["rx_blk"]["setup_slack_ns"] is None


def test_the_trace_entry_is_confined_to_designs() -> None:
    st = copy.deepcopy(lm.load_stages(DESIGN))
    st["trace"]["pytest"] = "../evil.py"
    with pytest.raises(lm.LatencyError):
        lm.run_trace(DESIGN, st)
