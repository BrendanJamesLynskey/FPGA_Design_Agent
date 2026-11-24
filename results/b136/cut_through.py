#!/usr/bin/env python3
"""Brief 136, scenario 2: cut-through (an order may leave before its packet's frame check is known) as the default instead of STRICT.

Inputs are brief 127's records (PR #253, branch b127-itch-phase2 at 6f603bb3, copied into results/b136/inputs_b127/ because the PR is not merged):
  fcs_window_unit_sim.json   a bad frame with one candidate message and n bytes of other messages after it: from which tail on the order escapes unpoisoned (Icarus, real MACs)
  fcs_window_share.json      the share of candidates (the seeded generator, 20 seeds of 400 messages) whose tail is longer than that window, at 1, 3 and 6 messages a packet
  latency_sim.json           clocks from the last byte of the message (X) / the adapter's last word (T) to the order frame's start strobe, speculative start against start-at-verdict
The step this script adds is arithmetic only: the expected number of orders that leave for a frame that later fails its check is  candidates x share_outside_window x P(frame bad).
P(frame bad) was NOT measured (the generator's frames are all good except the planted ones): the table is a grid of assumed values, not a prediction.

    python3 results/b136/cut_through.py     # writes results/b136/cut_through.json
"""
from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parent
share = json.loads((D / "inputs_b127" / "fcs_window_share.json").read_text())
unit = json.loads((D / "inputs_b127" / "fcs_window_unit_sim.json").read_text())
lat = json.loads((D / "inputs_b127" / "latency_sim.json").read_text())

P_BAD = [1e-9, 1e-6, 1e-3, 1e-2]          # assumed frame-check failure rates (a grid, not a measurement)
CLK_NS = 6.2058
rows = []
for n, v in share["by_messages_per_packet"].items():
    spec, verd = v["share_outside_speculative"], v["share_outside_at_verdict"]
    row = dict(messages_per_packet=int(n), candidates=v["candidates"],
               cut_through_speculative=dict(orders_unverified_share=spec, orders_leaving_on_a_bad_frame_per_million_orders_if_p_bad={f"{p:g}": round(1e6 * spec * p, 4) for p in P_BAD}),
               start_at_verdict=dict(orders_unverified_share=verd, orders_leaving_on_a_bad_frame_per_million_orders_if_p_bad={f"{p:g}": round(1e6 * verd * p, 4) for p in P_BAD}),
               strict_with_speculative_start=dict(good_orders_poisoned_share=spec, orders_leaving_on_a_bad_frame=0,
                                                  note="STRICT (IT_CTRL bit 5) poisons every order whose packet's verdict is not yet known and good: nothing unverified leaves; the share lost is the same share"),
               mean_tail_bytes_after_the_message=v["mean_tail_bytes"])
    rows.append(row)

u = lat["itch_unit"]
gain_T = (u["at_verdict"]["sop_minus_T"]["min"] - u["speculative"]["sop_minus_T"]["max"], u["at_verdict"]["sop_minus_T"]["max"] - u["speculative"]["sop_minus_T"]["min"])
out = dict(schema="fda.b136.cut_through/1",
           source=dict(branch="b127-itch-phase2", commit="6f603bb3", records=["results/b127/fcs_window_share.json", "results/b127/fcs_window_unit_sim.json", "results/b127/latency_sim.json", "results/b127/core_lat_sim.json (whole-core numbers quoted from the 127 report)"],
                       copied_to="results/b136/inputs_b127/"),
           window_bytes=dict(speculative=dict(largest_poisoned_tail=unit["speculative_largest_poisoned_tail_bytes"], smallest_escaping_tail=unit["speculative_smallest_escaping_tail_bytes"]),
                             at_verdict=dict(largest_poisoned_tail=unit["at_verdict_largest_poisoned_tail_bytes"], smallest_escaping_tail=unit["at_verdict_smallest_escaping_tail_bytes"])),
           per_messages_per_packet=rows,
           latency=dict(unit_sim_T_to_start_strobe_clocks=dict(speculative=[u["speculative"]["sop_minus_T"]["min"], u["speculative"]["sop_minus_T"]["max"]], at_verdict=[u["at_verdict"]["sop_minus_T"]["min"], u["at_verdict"]["sop_minus_T"]["max"]]),
                        unit_sim_X_to_start_strobe_clocks=dict(speculative=[u["speculative"]["sop_minus_X"]["min"], u["speculative"]["sop_minus_X"]["max"]], at_verdict=[u["at_verdict"]["sop_minus_X"]["min"], u["at_verdict"]["sop_minus_X"]["max"]]),
                        gained_by_speculative_start_clocks_range=list(gain_T), gained_ns_range=[round(g * CLK_NS, 1) for g in gain_T],
                        whole_core_gt_port_to_gt_port_mean_clocks=dict(speculative=16.8, at_verdict=21.6, gained=round(21.6 - 16.8, 1), gained_ns=round((21.6 - 16.8) * CLK_NS, 1), source="report 127 item 6 (xsim 2026.1, four phases, 32 orders a mode)")),
           p_bad_grid_is_assumed=P_BAD,
           not_measured=["the rate of frames that fail their check on a real link (P(frame bad)); the grid is assumed", "the real feed's packet lengths (the generator's distribution is used)", "any risk-logic behaviour after an unverified order: that is design reasoning, nothing was built or simulated in brief 136",
                         "board: nothing here ran on hardware"])
(D / "cut_through.json").write_text(json.dumps(out, indent=1) + "\n")
for r in rows:
    print(r["messages_per_packet"], r["cut_through_speculative"]["orders_unverified_share"], r["start_at_verdict"]["orders_unverified_share"], r["cut_through_speculative"]["orders_leaving_on_a_bad_frame_per_million_orders_if_p_bad"])
print(out["latency"])
