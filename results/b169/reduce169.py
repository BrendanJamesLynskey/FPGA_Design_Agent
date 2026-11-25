#!/usr/bin/env python3
"""Brief 169: reduce the ORD and RET lines of results/b169/core_sim.sh to clocks (6.2058 ns) per phase, with the definitions of results/b96e/core_lat.py:
  tick_to_trade = (sop_mac - (x_price - T)) / T + 2    price word on the receive GT port -> the order's start block (last bit) on the transmit GT port
  rx_start_strobe = (rxsop - x_start) / T ; d_strobe_to_order = (sop_mac - rxsop) / T (the board's D up to a constant)
  go_to_return = (RET - go) / T                         the go pulse in the transmit clock -> the order's start block at the receive PCS output after the loopback: a physical measure of the transmit side
  order_loop = (RET - sop_mac) / T                      order start stamp -> its start block at the receive PCS output after the loopback (transmit side + stand-in + receive PCS)
usage: reduce169.py <dir with ord_<phase>.log> <out.json>"""
import glob, json, re, statistics as st, sys
T = 6.2058
rows = {}
for f in sorted(glob.glob(sys.argv[1] + "/ord_*.log"), key=lambda p: int(re.search(r"ord_(\d+)", p)[1])):
    ph = int(re.search(r"ord_(\d+)\.log", f)[1])
    orders, rets = [], {}
    for ln in open(f):
        t = ln.split()
        if ln.startswith("ORD"):
            orders.append({t[i]: float(t[i + 1]) for i in range(2, len(t), 2)} | {"n": int(t[1])})
        elif ln.startswith("RET"):
            rets[int(t[1])] = float(t[3])
    if not orders:
        continue
    def stat(fn):
        v = [fn(o) for o in orders if fn(o) is not None]
        return {"mean": round(st.mean(v), 2), "min": round(min(v), 2), "max": round(max(v), 2)} if v else None
    rows[str(ph)] = {"orders": len(orders), "returned": len(rets),
        "tick_to_trade": stat(lambda o: (o["sop_mac"] - (o["x_price"] - T)) / T + 2),
        "rx_start_strobe": stat(lambda o: (o["rxsop"] - o["x_start"]) / T),
        "d_strobe_to_order": stat(lambda o: (o["sop_mac"] - o["rxsop"]) / T),
        "x_price_to_fire": stat(lambda o: (o["fire"] - o["x_price"]) / T),
        "fire_to_go": stat(lambda o: (o["go"] - o["fire"]) / T),
        "go_to_sop": stat(lambda o: (o["sop_mac"] - o["go"]) / T),
        "go_to_return": stat(lambda o: (rets[o["n"]] - o["go"]) / T if o["n"] in rets else None),
        "order_loop": stat(lambda o: (rets[o["n"]] - o["sop_mac"]) / T if o["n"] in rets else None)}
means = {q: round(st.mean(v[q]["mean"] for v in rows.values() if v[q]), 2) for q in ("tick_to_trade", "rx_start_strobe", "d_strobe_to_order", "x_price_to_fire", "fire_to_go", "go_to_sop", "go_to_return", "order_loop")}
json.dump({"mean_over_phases_clocks": means, "units": "clocks of 6.2058 ns", "phases_ps": sorted(map(int, rows)), "results": rows}, open(sys.argv[2], "w"), indent=1)
print("means", means)
for ph, r in rows.items():
    print(ph, "T2T", r["tick_to_trade"]["mean"], "S", r["rx_start_strobe"]["mean"], "D", r["d_strobe_to_order"]["mean"], "go->return", r["go_to_return"] and r["go_to_return"]["mean"], "orders", r["orders"], "returned", r["returned"])
