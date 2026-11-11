#!/usr/bin/env python3
"""results/24_fsm/summary.json: the numbers the site's FSM drawer quotes, from the tables and files in this folder."""
import json
from pathlib import Path

R = Path(__file__).parent
s = json.loads((R / "synth_table.json").read_text())["variants"]
i = json.loads((R / "impl_table.json").read_text())["variants"]
cov = json.loads((R / "coverage" / "summary.json").read_text())
f = lambda t, n, k: float(t[n][k])
out = {
    "separation": {"sep_states": 11, "mono_states": 23, "sep_transitions": 13, "mono_transitions": 39,
                   "sep_lut": int(f(i, "sep_base", "LUT_route")), "mono_lut": int(f(i, "mono_base", "LUT_route")),
                   "sep_ff": int(f(i, "sep_base", "FF_route")), "mono_ff": int(f(i, "mono_base", "FF_route"))},
    "outputs": {"comb_slack_ns": f(i, "sep_base", "WNS_r2out_route"), "registered_slack_ns": f(i, "sep_out1", "WNS_r2out_route"),
                "lookahead_slack_ns": f(i, "sep_out2", "WNS_r2out_route"), "registered_latency_extra_clocks": 1, "lookahead_latency_extra_clocks": 0},
    "ratio": {"none": f(i, "ratio_n4_nomc", "WNS_fsm_route"), "n2": f(i, "ratio_n2_mc", "WNS_fsm_route"),
              "n4": f(i, "ratio_n4_mc", "WNS_fsm_route"), "n8": f(i, "ratio_n8_mc", "WNS_fsm_route"), "clock_period_ns": 2.5},
    "coverage": {"designs": len(cov), "designs_passing": sum(1 for r in cov if r["pass"]), "mutants": sum(len(r["mutants"]) for r in cov),
                 "mutants_caught": sum(1 for r in cov for m in r["mutants"] if not m["pass"])},
    "formal": {"sep_induction_depth": 6, "mono_induction_depth": 5},
}
(R / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out))
