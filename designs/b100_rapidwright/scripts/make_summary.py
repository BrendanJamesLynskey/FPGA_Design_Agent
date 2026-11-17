"""Build results/b100/summary.json, the one record the README, handover.yaml and what_we_found.md quote (brief 100). It only reads the
run records already committed under results/b100/ (Vivado's run.json, route status and timing, the RapidWright logs, the stage 2 audit
logs); it computes nothing new. Usage: make_summary.py   (from the repository root). Pure Python."""
import json
import re
import statistics as st
from pathlib import Path

R = Path(__file__).resolve().parents[3] / "results" / "b100"


def jl(p):
    return json.loads(Path(p).read_text())


def last_json_line(p):
    rows = [l for l in Path(p).read_text().splitlines() if l.startswith("{")]
    return json.loads(rows[-1]) if rows else {}


def time_file(p):
    d = dict(l.split(None, 1) for l in Path(p).read_text().splitlines() if l.strip() and l.split()[0] in ("wall_s", "peak_bytes", "rc"))
    return {"wall_s": round(float(d["wall_s"]), 1), "peak_gib": round(int(d["peak_bytes"]) / 2**30, 2), "rc": int(d["rc"])}


out = {"schema": "b100-summary/1"}
# --- stage 0
s0 = R / "s0"
out["stage0"] = {
    "xck26": {"vivado_wns_ns": jl(s0 / "xck26-sfvc784-2LV-c_run.json")["wns_ns"], "after_rapidwright_wns_ns": jl(s0 / "xck26_rw_ref_run.json")["wns_ns"],
              "roundtrip": last_json_line(s0 / "rw_xck26_peak.log"), "bitstream_bytes": int(re.search(r"(\d+)", (s0 / "xck26_rw_ref_bitstream.txt").read_text()).group(1)) if (s0 / "xck26_rw_ref_bitstream.txt").exists() else None},
    "xc7a100t": {"vivado_wns_ns": jl(s0 / "xc7a100tcsg324-1_run.json")["wns_ns"], "after_rapidwright_wns_ns": jl(s0 / "xc7_rw_ref_run.json")["wns_ns"],
                 "roundtrip": last_json_line(s0 / "rw_xc7a100t.log"), "bitstream_bytes": int(re.search(r"(\d+)", (s0 / "xc7_rw_ref_bitstream.txt").read_text()).group(1))},
    "jvm_peak_gib_first_read": time_file(s0 / "rw_xck26_peak.time")["peak_gib"],
}
# --- capability 1
c1 = R / "c1"
if (c1 / "summary.json").exists():
    out["capability1"] = {"blocks": jl(c1 / "summary.json"), "block_ooc": jl(c1 / "blk_p0_run.json"),
                          "relocations": {p.name[6:-4]: last_json_line(p) for p in sorted(c1.glob("rw_mv_*.log"))}}
    runs = {}
    for arm in ("stamp", "alone"):
        for f in sorted(c1.glob(f"{arm}_p*_run.json")):
            runs[f.name[:-9]] = jl(f)
    out["capability1"]["whole_design_runs"] = runs
# --- capabilities 2 and 3
if (R / "summary_c23.json").exists():
    out["capabilities23"] = jl(R / "summary_c23.json")
# --- stage 2
ag = {}
for arm in ("a", "b"):
    d = R / "agent" / arm
    if (d / "meta.json").exists():
        ag[arm] = jl(d / "meta.json")
        calls = [json.loads(l) for l in (d / "audit.jsonl").read_text().splitlines() if '"tool"' in l]
        ag[arm]["tool_calls"] = len(calls)
        ag[arm]["tool_counts"] = {t: sum(1 for c in calls if c["tool"] == t) for t in sorted({c["tool"] for c in calls})}
        if (d / "result.json").exists():
            ag[arm]["result"] = jl(d / "result.json")
if ag:
    out["stage2"] = ag
(R / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
print("wrote", R / "summary.json")
