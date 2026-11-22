#!/usr/bin/env python3
"""Brief 136, scenario 4: the human sets E <= 16 clocks and tick-to-trade <= 20 clocks as TARGETS. Which recorded board runs, simulations and pre-registered predictions fail them.

Every number is read from a record in this repository (paths in the output). Quantities (docs/latency_definitions.md): E = echo, TX start to RX start of one probe frame; L = loop;
D = L - 2E; board tick-to-trade = L - E (minus the 0.83 ns fibre, ignored here: it is 0.13 clock); simulated tick-to-trade = clocks from the GT word holding the price to the GT word holding
the order's start block, with a zero-latency transceiver stand-in. They are different quantities, so each target is checked under each reading.

    python3 results/b136/latency_targets.py     # writes results/b136/latency_targets.json
"""
from __future__ import annotations

import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E_TARGET, T2T_TARGET = 16.0, 20.0
BOARD = {  # name -> record
    "control (default, RATE_MATCH 0), 96 first run": "b96/hw/20261117_101326/stage3.json",
    "control (default), 97C": "b97c/hw/20261118_194221/control/stage3.json",
    "lat_agent_both (97C)": "b97c/hw/20261118_194221/agent_both/stage3.json",
    "lat_all3 (97C)": "b97c/hw/20261118_194221/all3/stage3.json",
    "96C rate matcher, macro FIFO (control)": "b96c/hw/20261119_080724/control/stage3.json",
    "96C all3 + rate matcher": "b96c/hw/20261119_080724/all3/stage3.json",
    "rm_gp (96E, own buffer)": "b96e/hw/20261119_231251/rm_gp/stage3.json",
    "rm_gp_bypass (96F1b, GT buffers bypassed)": "b96f1/hw/20261120_215255/rm_gp_bypass/stage3.json",
    "rm_gp_ml (113)": "b113/hw/20261120_220813/rm_gp_ml/stage3.json",
}
CLK_NS = 6.2061


def board_row(name: str, rel: str) -> dict:
    d = json.loads((R / rel).read_text())
    r = d["restarts"]
    e_min, e_max, l_min = r["E_min_per_link"], r["E_max_per_link"], r["L_min_per_link"]
    h = {int(k): v for k, v in e_min["histogram"].items()}
    n = e_min["n"]
    within = sum(v for k, v in h.items() if k <= E_TARGET)
    row = dict(name=name, record=f"results/{rel}", restarts=n, E_median_of_minima=e_min["median"], E_best=e_min["min"], E_worst_of_maxima=e_max["max"],
               L_median_of_minima=l_min["median"], D=d["D_clocks_from_medians_of_minima"])
    row["T2T_board_L_minus_E"] = l_min["median"] - e_min["median"]
    row["restarts_with_E_min_le_16"] = within
    row["E_target_pass_median"] = e_min["median"] <= E_TARGET
    row["T2T_target_pass_board_reading"] = row["T2T_board_L_minus_E"] <= T2T_TARGET
    row["E_over_target_clocks"] = round(e_min["median"] - E_TARGET, 2)
    row["T2T_over_target_clocks"] = round(row["T2T_board_L_minus_E"] - T2T_TARGET, 2)
    return row


def main() -> None:
    rows = [board_row(n, p) for n, p in BOARD.items()]
    sim = {  # simulated tick-to-trade (digital, zero-latency GT stand-in), mean over four clock phases; records named
        "control": (10.7, "results/b126/README.md (core_sim)"),
        "lat_all3": (7.7, "results/b126/README.md (core_sim)"),
        "lat_all3_bypass": (7.6, "results/b126/README.md (core_sim)"),
        "rm_gp_bypass": (12.9, "results/b126/README.md (core_sim)"),
        "rm_gp_itch, GT port to GT port, speculative start (brief 127, PR 253, not merged)": (16.8, "b127-itch-phase2: results/b127/latency_sim.json (report 127)"),
        "rm_gp_itch, start at the verdict (brief 127)": (21.6, "b127-itch-phase2: results/b127/latency_sim.json (report 127)"),
    }
    sim_rows = [dict(name=k, sim_tick_to_trade_clocks=v[0], record=v[1], target_pass=v[0] <= T2T_TARGET) for k, v in sim.items()]
    pre = dict(name="lat_all3_bypass (brief 126, pre-registered, NOT run on a board)", record="results/b126/preregistration.md",
               E=16.0, E_band=[15.6, 16.6], T2T_board_L_minus_E=22.0, T2T_band=[21.6, 22.6], E_target_verdict="at the target: the band straddles it, a pass is not predicted with confidence",
               T2T_target_verdict="fails by 2 clocks (band 21.6 to 22.6)")
    loop = dict(name="lat_all3_bypass + loop-timed transmit (96F V1'/V2; prediction on a GTY figure, UNCONFIRMED for this GTH; not built)", record="results/b96f/latency_prediction.json, reports/96F2",
                note="96F predicted loop timing saves 3 to 4 clocks of the receive-to-transmit fabric crossing; applied to the 126 prediction (22 clocks) by arithmetic: 18 to 19 clocks, inside 20; E unchanged by loop timing (15.5 to 17.1 in 96F's table).",
                T2T_arithmetic=[18.0, 19.0])
    out = dict(schema="fda.b136.latency_targets/1", targets=dict(E_clocks=E_TARGET, tick_to_trade_clocks=T2T_TARGET, clock_ns=CLK_NS), board_runs=rows, simulation=sim_rows, preregistered=pre, arithmetic_only=loop,
               not_measured=["no board run of lat_all3_bypass", "no board run of loop timing", "the optical module's own delay is inside E and L - E and is not separable", "counter resolution is 1 clock (6.2 ns)"])
    (R / "b136" / "latency_targets.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        print(f"{r['name']:48s} E {r['E_median_of_minima']:5} (best {r['E_best']})  L-E {r['T2T_board_L_minus_E']:5}  E<=16 {r['E_target_pass_median']}  T2T<=20 {r['T2T_target_pass_board_reading']}  {r['restarts_with_E_min_le_16']}/{r['restarts']} restarts E<=16")


if __name__ == "__main__":
    main()
