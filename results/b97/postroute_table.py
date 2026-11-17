#!/usr/bin/env python3
"""The post-route table of the latency variants (brief 97), read from results/b97/builds/<variant>/{digest,slack}.json and the simulated clocks.
Writes results/b97/postroute.md and postroute.json. Sim clocks are the in-phase bench figures recorded by the loop and the hand runs."""
import json
from pathlib import Path

H = Path(__file__).resolve().parent
PERIOD = 6.2058
SIM = {"baseline": 11, "agent_cdc": 10, "hand_ref": 9, "agent_both": 9, "all3": 8}
BASE_ROW = None
CHANGES = {"baseline": "none (96 as built; stage 3 run of 2026-11-17)", "agent_cdc": "u_p_go REG_OUTPUT 1->0", "hand_ref": "REG_OUTPUT 1->0; order-only early MAC start",
           "agent_both": "REG_OUTPUT 1->0; trade64.fire combinational", "all3": "all three (the early start was found by both A0 runs in round 2)"}
rows, js = [], {}
for v in ["agent_cdc", "hand_ref", "agent_both", "all3"]:
    d = H / "builds" / v / "digest.json"
    if not d.is_file():
        rows.append(f"| {v} | {CHANGES[v]} | {SIM[v]} | {SIM[v]*PERIOD:.1f} | not built | | | |")
        continue
    g = json.loads(d.read_text())
    t, u = g["timing"], g["utilization"]
    sl = H / "builds" / v / "slack.json"
    s = json.loads(sl.read_text())["stages"] if sl.is_file() else {}
    crit = {k: x["setup_slack_ns"] for k, x in s.items() if x.get("setup_slack_ns") is not None}
    worst = min(crit.items(), key=lambda kv: kv[1]) if crit else ("", None)
    js[v] = {"sim_clocks": SIM[v], "wns_ns": t["wns_ns"], "whs_ns": t["whs_ns"], "timing_met": t["timing_met"], "lut": u["lut"], "ff": u["ff"],
             "power_w": g["power"].get("total_w"), "stage_slack_ns": crit}
    rows.append(f"| {v} | {CHANGES[v]} | {SIM[v]} | {SIM[v]*PERIOD:.1f} | {t['wns_ns']} / {t['whs_ns']} ({'met' if t['timing_met'] else 'FAILED'}) | {u['lut']} / {u['ff']} | "
                f"{g['power'].get('total_w')} | {worst[0]} {worst[1]} |")
hdr = ["| variant | change | sim clocks (tick-to-trade) | ns | WNS / WHS ns | LUT / FF | power W | worst stage slack |", "|---|---|---|---|---|---|---|---|"]
STAGES = ["rx_blk", "rx_descramble", "rx_mac", "decide", "cross_go", "fs_start", "mac_preamble", "tx_encode", "tx_spill"]
BASE = [0, 1, 1, 1, 4, 1, 1, 1, 1]
DELTA = {"agent_cdc": {"cross_go": 3}, "hand_ref": {"cross_go": 3, "fs_start": 0}, "agent_both": {"cross_go": 3, "decide": 0}, "all3": {"cross_go": 3, "decide": 0, "fs_start": 0}}
st = ["", "| stage (clocks, ns at 6.2058) | " + " | ".join(["baseline"] + list(DELTA)) + " |", "|---|" + "---|" * (1 + len(DELTA))]
for i, n in enumerate(STAGES):
    cells = [f"{BASE[i]} ({BASE[i]*PERIOD:.1f})"] + [f"{DELTA[v].get(n, BASE[i])} ({DELTA[v].get(n, BASE[i])*PERIOD:.1f})" for v in DELTA]
    st.append(f"| {n} | " + " | ".join(cells) + " |")
tot = [sum(BASE)] + [sum(DELTA[v].get(n, BASE[i]) for i, n in enumerate(STAGES)) for v in DELTA]
st.append("| total | " + " | ".join(f"{t} ({t*PERIOD:.1f})" for t in tot) + " |")
(H / "postroute.md").write_text("\n".join(hdr + rows + st) + "\n")
(H / "postroute.json").write_text(json.dumps(js, indent=1) + "\n")
print((H / "postroute.md").read_text())
