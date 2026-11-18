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
CORE = json.loads((ROOT / "results" / "b96" / "core_sim.json").read_text())


def test_stage_file_reproduces_the_96_numbers() -> None:
    r = lm.latency_path(DESIGN, CORE)
    assert r["reconciled"], r["problems"]
    assert r["total_clocks"] == 11 and r["total_ns"] == pytest.approx(68.264, abs=0.01)
    by = {s["id"]: s for s in r["stages"]}
    assert by["cross_go"]["clocks"] == 4 and by["cross_go"]["domain"] == "rx->tx"
    # direction split: receive 3 stages (2 clocks to the MAC register), crossing 4, transmit 4 (preamble 2 + start block 2)
    assert sum(s["clocks"] for s in r["stages"] if s["domain"] == "rx") == 3
    assert sum(s["clocks"] for s in r["stages"] if s["domain"] == "tx") == 4
    e = lm.latency_path(DESIGN, CORE, path="echo")
    assert e["total_clocks"] == 12 and sum(s["clocks"] for s in e["stages"]) == 12


def test_a_stale_stage_file_is_reported_not_trusted() -> None:
    core = copy.deepcopy(CORE)
    core["tick_to_trade_digital_sim"]["fire_register_to_go_pulse_in_tx_domain_clocks"] = 3      # a design change the file does not know
    core["tick_to_trade_digital_sim"]["gt_rxdata_price_word_to_gt_txdata_order_start_clocks"] = 10
    r = lm.latency_path(DESIGN, core)
    assert not r["reconciled"] and any("fire_to_go" in p for p in r["problems"])


def test_unknown_path_and_missing_file_are_refused(tmp_path: Path) -> None:
    with pytest.raises(lm.LatencyError):
        lm.latency_path(DESIGN, CORE, path="nope")
    with pytest.raises(lm.LatencyError):
        lm.load_stages(tmp_path)


def test_budget_never_adds_board_and_simulation_into_one_number() -> None:
    b = lm.latency_budget(DESIGN, CORE, None, ROOT / "results" / "b96")
    bd = b["board"]
    assert bd["E_clocks"] == 20 and bd["L_clocks"] == 50
    assert bd["wire_to_wire_clocks"] == pytest.approx(29.9, abs=0.2)           # 50 - 20 - 0.13: the 96 report's "about 30 clocks"
    assert bd["gt_optics_clocks"] == 15                                        # E 20 minus the 5 digital clocks the 96 report counts
    # the residual is shown, and it is the difference of the two accountings
    assert bd["unattributed_clocks"] == pytest.approx(bd["wire_to_wire_clocks"] - 11 - 15, abs=0.2)
    assert b["rows"][-1]["needs_board"] and b["rows"][-1]["stage"] == "gt_tx_rx_optics"
    assert "cross_go" in b["ranking_by_removable_clocks"]
    assert b["total_removable_digital_clocks_upper_bound"] <= 7


def test_slack_joins_by_stage_and_marks_timing_critical() -> None:
    slack = {"source": "x.dcp", "stages": {"rx_descramble": {"cells": 72, "clock": "rxusr2", "setup_slack_ns": 0.12}, "cross_go": {"cells": 6, "clock": "txusr2", "setup_slack_ns": 3.0}}}
    r = lm.latency_path(DESIGN, CORE, slack)
    by = {s["id"]: s for s in r["stages"]}
    assert by["rx_descramble"]["timing_critical"] is True and by["cross_go"]["timing_critical"] is False
    assert by["rx_blk"]["timing_critical"] is None            # no netlist reading for that stage: unknown, not "fine"


def test_tcl_inputs_and_outputs_round_trip() -> None:
    st = lm.load_stages(DESIGN)
    tsv = netlist.stage_tsv(st)
    ids = [l.split("\t")[0] for l in tsv.splitlines()]
    assert "cross_go" in ids and "tx_spill" not in ids              # a stage with no registers is not sent to Vivado
    out = netlist.parse_out("cross_go\t6\ttxusr2\t2.5\t0.04\nrx_blk\t0\t-\t-\t-\n")
    assert out["cross_go"] == {"cells": 6, "clock": "txusr2", "setup_slack_ns": 2.5, "hold_slack_ns": 0.04}
    assert out["rx_blk"]["setup_slack_ns"] is None


def test_the_trace_entry_is_confined_to_designs() -> None:
    st = copy.deepcopy(lm.load_stages(DESIGN))
    st["trace"]["pytest"] = "../evil.py"
    with pytest.raises(lm.LatencyError):
        lm.run_trace(DESIGN, st)
