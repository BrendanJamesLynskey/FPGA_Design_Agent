#!/usr/bin/env python3
"""Brief 126: results/b126/summary.json, every figure the README compares, computed from the recorded files (the parents' build digests, this build's digest and run.json, the simulation reductions
and logs). Run from the repo root: python3 results/b126/summary.py"""
import json, re
from pathlib import Path

R = Path("results")
def dig(p):
    d = json.loads((R / p / "digest.json").read_text())
    return {"wns_ns": d["timing"]["wns_ns"], "whs_ns": d["timing"]["whs_ns"], "lut": d["utilization"]["lut"], "ff": d["utilization"]["ff"], "power_w": d["power"]["total_w"]}
builds = {"lat_all3_97c": dig("b97c/builds/all3"), "rm_gp_bypass_96f1b": dig("b96f1b/builds/rm_gp_bypass"), "lat_all3_bypass": dig("b126/builds/lat_all3_bypass")}
a, b = builds["lat_all3_97c"], builds["lat_all3_bypass"]
out = {"builds": builds, "lat_all3_bypass_minus_lat_all3": {"lut": b["lut"] - a["lut"], "ff": b["ff"] - a["ff"], "wns_ns": round(a["wns_ns"] - b["wns_ns"], 3), "note": "wns_ns here is lat_all3's WNS minus lat_all3_bypass's"},
       "lat_all3_bypass_wall_s": round(json.loads((R / "b126/builds/lat_all3_bypass/run.json").read_text())["wall_s"])}
sim = {}
for c in ("control", "all3", "all3_bypass", "rm_gp_bypass"):
    d = json.loads((R / f"b126/core_sim/{c}.json").read_text()); k = next(iter(d["results"]))
    ph = d["results"][k]; means = [v["tick_to_trade"]["mean"] for v in ph.values()]
    sim[c] = {"tick_to_trade_mean_over_phases": d["means_over_phases_clocks"][k]["tick_to_trade"], "phase_mean_min": min(means), "phase_mean_max": max(means),
              "rx_start_strobe": d["means_over_phases_clocks"][k]["rx_start_strobe"], "d_strobe_to_order": d["means_over_phases_clocks"][k]["d_strobe_to_order"]}
out["simulation_clocks"] = sim
out["simulation_delta_all3_vs_all3_bypass_clocks"] = round(abs(sim["all3_bypass"]["tick_to_trade_mean_over_phases"] - sim["all3"]["tick_to_trade_mean_over_phases"]), 1)   # absolute difference of the two means
bl = {}
for sc in ("retry", "giveup", "normal"):
    f = R / ("b126/core_sim/all3_bypass/" + ("ord_0_0_0.log" if sc == "normal" else f"bypass_{sc}.log")); t = f.read_text()
    m = re.search(r"(?:UP|NOLINK) GT_BUF ([0-9a-f]{8})", t); u = re.search(r"LINK UP at (\d+)", t)
    bl[sc] = {"gt_buf": "0x" + m.group(1) if m else None, "link_up_us": round(int(u.group(1)) / 1e9, 2) if u else None}
    fe = re.search(r"FEATURES ([0-9a-f]{8})", t); bl[sc]["features"] = "0x" + fe.group(1)[-2:] if fe else None
out["bypass_scenarios_all3_bypass"] = bl
Path("results/b126/summary.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
