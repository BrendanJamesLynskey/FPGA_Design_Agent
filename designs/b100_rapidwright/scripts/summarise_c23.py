"""Collect the capability 2 and 3 runs of brief 100 (results/b100/c23/) into one table: per arm and per perturbation, Vivado's worst setup
slack (whole design, MAC to PCS, PCS to GT), hold slack, LUT/FF, the achieved period (target minus slack of the whole design), the
latency of the two-register chain in ns at that period, and run times. Usage: summarise_c23.py <c23 dir> <out.json>. No Vivado, no RapidWright."""
import glob
import json
import re
import statistics as st
import sys
from pathlib import Path

d = Path(sys.argv[1])
ARMS = {"base": "Vivado alone", "place": "RapidWright placement + Vivado route", "rwr": "Vivado placement + RWRoute (no Vivado routing)",
        "fixed": "Vivado placement + RWRoute on the worst-path nets (fixed) + Vivado route"}
rows = []
for arm in ARMS:
    for f in sorted(d.glob(f"{arm}_s*_run.json")):
        tag = re.search(r"_(s\d+)_run", f.name).group(1)
        run = json.loads(f.read_text())
        ch = json.loads((d / f"{arm}_{tag}_chain.json").read_text()) if (d / f"{arm}_{tag}_chain.json").exists() else {}
        target = ch.get("period_ns", run["period_ns"])
        wns = ch.get("wns_all_ns", run["wns_ns"])
        rw = {}
        for g in glob.glob(str(d / f"{arm}_{tag}.rw.log")):
            m = [l for l in open(g) if l.startswith("{")]
            if m:
                rw = json.loads(m[-1])
        achieved = round(target - wns, 3)
        rows.append({"arm": arm, "seed": tag, "target_ns": target, "wns_all_ns": wns, "wns_mac_to_pcs_ns": ch.get("wns_mac_to_pcs_ns"),
                     "wns_pcs_to_gt_ns": ch.get("wns_pcs_to_gt_ns"), "whs_ns": run["whs_ns"], "lut": run["lut"], "ff": run["ff"],
                     "achieved_period_ns": achieved, "chain_latency_ns_2clk": round(2 * achieved, 3), "vivado_times_s": run["times_s"],
                     "rapidwright": {k: rw[k] for k in ("route_s", "seconds", "moved", "nets_unrouted", "write_s") if k in rw}})
summary = {"arms": ARMS, "rows": rows, "by_arm": {}}
for arm in ARMS:
    r = [x for x in rows if x["arm"] == arm]
    if r:
        a = [x["achieved_period_ns"] for x in r]
        summary["by_arm"][arm] = {"n": len(r), "achieved_period_ns_mean": round(st.mean(a), 3), "min": min(a), "max": max(a),
                                  "stdev": round(st.pstdev(a), 3), "wns_closed": sum(1 for x in r if x["wns_all_ns"] >= 0)}
json.dump(summary, open(sys.argv[2], "w"), indent=1)
print(json.dumps(summary["by_arm"], indent=1))
