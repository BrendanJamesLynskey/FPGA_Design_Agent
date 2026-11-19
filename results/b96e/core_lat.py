"""Brief 96E: reduce the ORD lines of results/b96e/core_lat_sim.sh (xsim, real XPM macros) to clocks per receive path and phase -> core_lat_sim.json.

usage: python3 results/b96e/core_lat.py <work dir with ord_<rate_match>_<own>_<phase>.log> <out.json>
Quantities (clocks of 6.2058 ns; times are the clock edges that LOAD each signal, see sim/tb_lat_core.sv):
  tick_to_trade   = sop_mac - (x_price - 1) + 2   price word on the receive GT port -> the order's start block on the transmit GT port (as tests/core_cocotb.py)
  rx_start_strobe = rxsop - x_start               PCS output register loads the feed frame's start block -> tx_path's rx_sop_p (what the board's E and L stamp)
  d_strobe_to_order = sop_mac - rxsop             the board's D (RX start stamp of the feed -> order TX start), up to the same constant on every build
Board: E = T_tx + fibre + (rx start strobe path), L = 2E + D (docs/design.md section 6), so  dE = d(rx_start_strobe),  dL = 2 dE + dD.
"""
import glob, json, re, statistics as st, sys
T = 6.2058
rows = {}
for f in sorted(glob.glob(sys.argv[1] + "/ord_*.log")):
    m = re.search(r"ord_(\d)_(\d)_(\d+)\.log", f)
    rm, own, ph = int(m[1]), int(m[2]), int(m[3])
    orders = []
    for ln in open(f):
        if ln.startswith("ORD"):
            t = ln.split(); d = {t[i]: float(t[i + 1]) for i in range(2, len(t), 2)}
            orders.append(d)
    if not orders:
        continue
    def stat(fn):
        v = [fn(o) for o in orders]
        return {"mean": round(st.mean(v), 2), "min": round(min(v), 2), "max": round(max(v), 2)}
    rec = {"orders": len(orders),
           "tick_to_trade": stat(lambda o: (o["sop_mac"] - (o["x_price"] - T)) / T + 2),
           "rx_start_strobe": stat(lambda o: (o["rxsop"] - o["x_start"]) / T),
           "d_strobe_to_order": stat(lambda o: (o["sop_mac"] - o["rxsop"]) / T),
           "pcs_out_to_mac_word7": stat(lambda o: (o["w7_mac"] - o["x_price"]) / T),
           "mac_word7_to_fire": stat(lambda o: (o["fire"] - o["w7_mac"]) / T),
           "fire_to_go": stat(lambda o: (o["go"] - o["fire"]) / T),
           "go_to_order_preamble": stat(lambda o: (o["sop_mac"] - o["go"]) / T)}
    if rm == 1:
        rec["pcs_out_to_buffer_out"] = stat(lambda o: (o["y_price"] - o["x_price"]) / T)
        rec["buffer_out_to_mac_word7"] = stat(lambda o: (o["w7_mac"] - o["y_price"]) / T)
    rows.setdefault(f"rate_match_{rm}_rm_own_{own}", {})[str(ph)] = rec
import statistics
means = {k: {q: round(statistics.mean(v[ph][q]["mean"] for ph in v), 1) for q in ("tick_to_trade", "rx_start_strobe", "d_strobe_to_order")} for k, v in rows.items()}
base = means.get("rate_match_0_rm_own_0", {}).get("tick_to_trade")
changes = {k: round(m["tick_to_trade"] - base, 1) for k, m in means.items()} if base is not None else {}
json.dump({"means_over_phases_clocks": means, "tick_to_trade_change_vs_97c_clocks": changes, "what": "Whole-core tick-to-trade in xsim 2026.1 with AMD's real XPM macros (sim/tb_lat_core.sv, 8 orders per point, 301 clocks apart), by receive path and by the phase between the receive and transmit user clocks (ps the receive clock lags). rate_match_0 = the 97C path (RATE_MATCH = 0); rate_match_1_rm_own_0 = 96C's buffer on xpm_fifo_async; rate_match_1_rm_own_1 = 96E's own gray-pointer buffer. Clocks of 6.2058 ns.",
           "units": "clocks", "results": rows}, open(sys.argv[2], "w"), indent=1)
for k, v in rows.items():
    for ph, r in v.items():
        print(k, ph, "T2T", r["tick_to_trade"], "S", r["rx_start_strobe"], "D", r["d_strobe_to_order"])
