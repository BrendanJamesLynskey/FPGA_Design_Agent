"""Brief 113: reduce the ORD lines of results/b113/lat_all.sh (whole core, xsim 2026.1, real XPM macros, synthetic feed injected) to clocks per configuration and phase -> latency.json.

usage: python3 results/b113/lat_summary.py <dir with <build>_v<veto>_h<hold>_p<phase>.log> <out.json>
Quantities (clocks of 6.2058 ns; the times are the clock edges that LOAD each signal, see sim/tb_ml_core.sv; same definitions as results/b96e/core_lat.py):
  tick_to_trade   = sop_mac - (x_price - 1 clock) + 2    the price word on the receive GT port -> the order's start block on the transmit GT port
  rx_start_strobe = rxsop - x_start                       what the board's E and L stamp
  d_strobe_to_order = sop_mac - rxsop                     the board's D
  pcs_out_to_mac_word7, mac_word7_to_fire, fire_to_go, go_to_order_preamble: the stages of the chain
"""
import glob
import json
import re
import statistics as st
import sys

T = 6.2058


def main() -> None:
    rows = {}
    for f in sorted(glob.glob(sys.argv[1] + "/*.log")):
        m = re.search(r"([a-z]+)_v(\d)_h(\d)_p(\d+)\.log", f)
        if not m:
            continue
        build, veto, hold, ph = m[1], int(m[2]), int(m[3]), int(m[4])
        orders = []
        for ln in open(f):
            if ln.startswith("ORD"):
                t = ln.split()
                orders.append({t[i]: float(t[i + 1]) for i in range(2, len(t), 2)})
        if not orders:
            continue

        def stat(fn):
            v = [fn(o) for o in orders]
            return {"mean": round(st.mean(v), 2), "min": round(min(v), 2), "max": round(max(v), 2)}
        rec = {"orders": len(orders),
               "tick_to_trade": stat(lambda o: (o["sop_mac"] - (o["x_price"] - T)) / T + 2),
               "rx_start_strobe": stat(lambda o: (o["rxsop"] - o["x_start"]) / T),
               "d_strobe_to_order": stat(lambda o: (o["sop_mac"] - o["rxsop"]) / T),
               "pcs_out_to_buffer_out": stat(lambda o: (o["y_price"] - o["x_price"]) / T),
               "buffer_out_to_mac_word7": stat(lambda o: (o["w7_mac"] - o["y_price"]) / T),
               "mac_word7_to_fire": stat(lambda o: (o["fire"] - o["w7_mac"]) / T),
               "fire_to_go": stat(lambda o: (o["go"] - o["fire"]) / T),
               "go_to_order_preamble": stat(lambda o: (o["sop_mac"] - o["go"]) / T)}
        name = {"base": "base_rm_gp_no_ml"}.get(build, f"ml_{'veto' if veto else 'shadow'}" + (f"_hold{hold}" if hold else ""))
        rows.setdefault(name, {})[str(ph)] = rec
    means = {k: {q: round(st.mean(v[ph][q]["mean"] for ph in v), 2) for q in ("tick_to_trade", "rx_start_strobe", "d_strobe_to_order")} for k, v in rows.items()}
    # the change against the control is paired: per phase, then the mean over the phases both runs have
    def paired(q):
        b = rows.get("base_rm_gp_no_ml", {})
        return {k: round(st.mean(v[ph][q]["mean"] - b[ph][q]["mean"] for ph in v if ph in b), 2) for k, v in rows.items() if any(ph in b for ph in v)} if b else {}
    chg, chg_e, chg_d = paired("tick_to_trade"), paired("rx_start_strobe"), paired("d_strobe_to_order")
    base = bool(chg)
    json.dump({"means_over_phases_clocks": means, "tick_to_trade_change_vs_base_clocks": chg, "rx_start_strobe_change_vs_base_clocks": chg_e, "d_change_vs_base_clocks": chg_d,
               "what": "Whole-core tick-to-trade in xsim 2026.1 with AMD's real XPM macros, a synthetic feed injected on the receive words (10 orders per point, 300 idle words apart), build rm_gp without the ML stage "
                       "(base_rm_gp_no_ml) and rm_gp_ml in shadow and veto mode; ml_*_holdN is the simulation-only counterfactual in which the order is released N clocks after the decision (what the stage would cost if its class "
                       "were made after the message arrived). Phases: ps the receive clock lags the transmit clock. Clocks of 6.2058 ns.",
               "units": "clocks", "results": rows}, open(sys.argv[2], "w"), indent=1)
    for k, v in means.items():
        print(k, v, "dT2T vs base", chg.get(k))


if __name__ == "__main__":
    main()
