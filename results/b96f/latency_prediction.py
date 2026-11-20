#!/usr/bin/env python3
"""Predicted latency of the loop-timed, buffer-bypassed path against 97C and 96E (brief 96F). Paper arithmetic on recorded numbers only.

Inputs (each with its source):
- the clock period, 6.2058 ns (docs/design.md section 5);
- board medians of 97C (results/b96/hw, quoted in docs/design.md, "Board result"): control E 20, L 50; all3 E 20, L 46 clocks;
- 96E's prediction for rm_gp (report 96E): the receive-start path +1.4 clocks, so E 21.4 and L 54 to 55 for the control build;
- the fabric crossing that loop timing removes: the 97C go-pulse crossing, 4 clocks in the control build (results/b96c/core_sim_default.json,
  fire_register_to_go_pulse_in_tx_domain_clocks) and 3 in all3 (the same crossing without its output register, GO_REG = 0): removed completely
  in variant V1 (one shared user clock) and replaced by a one-clock crossing in variant V2 (two matched clocks);
- the GT buffers that bypass removes: 7.7 to 10.9 ns (TX) and 13.2 to 17.1 ns (RX) at the line rate in a GTY example, 18 to 25 ns saved in total
  (a third-party article citing AMD AR 69011; the GTH document AR 68177 was not retrieved): UNCONFIRMED for this device. The range used here is
  the article's total (18 ns) to the sum of its per-buffer maxima (28.0 ns).
"""
import json
import sys

T = 1e9 / 161.1328125e6
gt_ns = (18.0, 10.9 + 17.1)             # low: the article total; high: the sum of its per-buffer maxima
base = {"control": {"E": 20.0, "L": 50.0, "cross": 4}, "all3": {"E": 20.0, "L": 46.0, "cross": 3}}
out = {"clock_ns": round(T, 4), "gt_buffer_saving_ns_range_unconfirmed": gt_ns, "rows": {}}
for name, b in base.items():
    gt_clk = (gt_ns[0] / T, gt_ns[1] / T)
    for var, left in (("V1_shared_clock", 0), ("V2_matched_clocks", 1)):
        cross_saved = b["cross"] - left
        d_t2t = {"min_saving_clk": round(gt_clk[0] + cross_saved, 2), "max_saving_clk": round(gt_clk[1] + cross_saved, 2)}
        t2t97 = b["L"] - b["E"]                                   # tick-to-trade on the board: L minus E (one link pass + D)
        out["rows"][f"{name}_{var}"] = {
            "tick_to_trade_97C_clk": t2t97, "tick_to_trade_97C_ns": round(t2t97 * T, 1),
            "saving_clk": d_t2t,
            "tick_to_trade_loop_timed_clk": [round(t2t97 - d_t2t["max_saving_clk"], 1), round(t2t97 - d_t2t["min_saving_clk"], 1)],
            "tick_to_trade_loop_timed_ns": [round((t2t97 - d_t2t["max_saving_clk"]) * T, 0), round((t2t97 - d_t2t["min_saving_clk"]) * T, 0)],
            "echo_E_loop_timed_clk": [round(b["E"] - gt_clk[1], 1), round(b["E"] - gt_clk[0], 1)],
            "loop_L_loop_timed_clk": [round(b["L"] - 2 * gt_clk[1] - cross_saved, 1), round(b["L"] - 2 * gt_clk[0] - cross_saved, 1)]}
# against 96E rm_gp (control build): receive-start path +1.4 clocks => E 21.4; L 54 to 55; tick-to-trade L - E
rm_e, rm_l = 21.4, (54.0, 55.0)
rm_t2t = (rm_l[0] - rm_e, rm_l[1] - rm_e)
out["rm_gp_96E_control"] = {"E_clk": rm_e, "L_clk": list(rm_l), "tick_to_trade_clk": [round(x, 1) for x in rm_t2t],
                            "tick_to_trade_ns": [round(x * T, 0) for x in rm_t2t]}
c = out["rows"]["control_V1_shared_clock"]["tick_to_trade_loop_timed_clk"]
c2 = out["rows"]["control_V2_matched_clocks"]["tick_to_trade_loop_timed_clk"]
out["saving_against_rm_gp_control_clk"] = {"V1": [round(rm_t2t[0] - c[1], 1), round(rm_t2t[1] - c[0], 1)],
                                          "V2": [round(rm_t2t[0] - c2[1], 1), round(rm_t2t[1] - c2[0], 1)]}
out["saving_against_rm_gp_control_ns"] = {k: [round(v[0] * T, 0), round(v[1] * T, 0)] for k, v in out["saving_against_rm_gp_control_clk"].items()}
path = sys.argv[1] if len(sys.argv) > 1 else "latency_prediction.json"
json.dump(out, open(path, "w"), indent=1, sort_keys=True)
print(json.dumps(out, indent=1, sort_keys=True))
