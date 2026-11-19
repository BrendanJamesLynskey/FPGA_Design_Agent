import json,sys
V=["control","rm_ctl","rm_all3","ppm_ctl","ppm_all3"]
D={v:json.load(open(f"builds/{v}/digest.json")) for v in V}
R={v:json.load(open(f"builds/{v}/run.json")) for v in V}
o=["# 96C build gates (generated from builds/*/digest.json and run.json)","",
"rm_ctl, rm_all3, ppm_ctl, ppm_all3 (RATE_MATCH = 1): built 2026-11-19 from git f47986f4 (Vivado 2026.1, xck26-sfvc784-2LV-c, 6G scope, 1 thread); these are the bitstreams the board measured (rm_ctl and rm_all3 were called control and all3 then). `control` is the DEFAULT build, RATE_MATCH = 0 (brief 96C addendum 2): its commit is in builds/control/commit.txt. Regenerate: `python3 results/b96c/gen_gates.py`.","",
"| metric | "+" | ".join(V)+" |","|---|"+"---|"*len(V)]
def row(n,f): o.append(f"| {n} | "+" | ".join(str(f(v)) for v in V)+" |")
row("LUT",lambda v:D[v]["utilization"]["lut"]); row("FF",lambda v:D[v]["utilization"]["ff"])
row("LUTRAM",lambda v:D[v]["utilization"]["lutram"]); row("BRAM tiles",lambda v:D[v]["utilization"]["bram_tile"])
row("WNS ns",lambda v:D[v]["timing"]["wns_ns"]); row("WHS ns",lambda v:D[v]["timing"]["whs_ns"])
row("period ns",lambda v:D[v]["timing"]["period_ns"])
row("power W",lambda v:D[v]["power"]["total_w"]); row("Tj C",lambda v:D[v]["power"]["junction_c"])
row("DRC critical",lambda v:D[v]["drc"]["critical_warnings"]); row("methodology critical",lambda v:D[v]["methodology"]["critical_warnings"])
row("wall s",lambda v:R[v]["wall_s"]); row("scope cap hits",lambda v:R[v].get("scope_cap_hits"))
row("scope swap peak MiB",lambda v:R[v].get("scope_swap_peak_mib")); row("scope anon peak MiB",lambda v:R[v].get("scope_anon_peak_mib"))
g=sorted(D[V[0]]["gates"])
row(f"gates true (of {len(g)})",lambda v:sum(bool(x) for x in D[v]["gates"].values()))
o+=["","Per-gate (T = true):","","| gate | "+" | ".join(V)+" |","|---|"+"---|"*len(V)]
for k in g: o.append(f"| {k} | "+" | ".join("T" if D[v]["gates"].get(k) else "F" for v in V)+" |")
open("builds/gates.md","w").write("\n".join(o)+"\n")
