#!/usr/bin/env python3
"""Brief 49: collect the Vivado 2026.1 re-measurements made outside the fixture tables into this folder.

    python3 results/vivado_2026_1_remeasure/collect.py <xpm_before build dir> <xpm_after build dir>

- dev_rebuilds.json: each development run whose saved design was kept (runs/<run_id>/<task>, git-ignored), rebuilt with
  `FDA_BUILD_CACHE=0 flow/run_vivado.sh runs/<run_id>/<task> base` on 2026.1, today's flow and test shell. Read from each
  build's gates.json and run.json (post-route timing at 100 MHz, utilisation, vectorless power, today's gate verdicts).
- xpm_probe.json: the QR1 probe (flow/tests/fixtures/xpm_probe) built to route with and without flow/xpm_cdc.tcl
  (`FDA_XPM_CDC=0`), clk_a -> clk_b from the Inter Clock Table, report_cdc's Exception column.
- b30_hil_audio.json: designs/b30_hil_audio base, totals and the per-instance utilisation of report_utilization -hierarchical.
- b2_builds.json: the four read-only board self-check designs (designs/b2_*) built base on 2026.1 (the board runs in
  results/board_v2 used bitstreams from the earlier release; these builds were not programmed).
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def build_summary(b: Path) -> dict:
    g = json.loads((b / "gates.json").read_text())
    r = json.loads((b / "run.json").read_text())
    t, u, p = g.get("timing") or {}, g.get("utilization") or {}, g.get("power") or {}
    return {"vivado": r["vivado_version"], "threads": r.get("max_threads"), "wall_s": r["wall_s"],
            "vivado_peak_rss_mib": r["vivado_peak_rss_mib"], "scope_anon_peak_mib": r["scope_anon_peak_mib"],
            "wns_ns": t.get("wns_ns"), "whs_ns": t.get("whs_ns"), "lut": u.get("lut"), "ff": u.get("ff"), "dsp": u.get("dsp"),
            "bram36": u.get("bram_tile"), "power_w": p.get("total_w"), "gates_pass": g["pass"],
            "gates_failed": sorted(k for k, v in g["gates"].items() if v is False), "sources_sha256": g.get("sources_sha256")}


def dev():
    recs = {json.loads(p.read_text())["run_id"]: json.loads(p.read_text()) for p in (ROOT / "results/course").glob("*/run_*.json")}
    runs, rows = {}, []
    for b in sorted((ROOT / "runs").glob("*/*/build/base/gates.json")):
        d = b.parent
        rid = d.parents[2].name
        rec = recs[rid]
        s = build_summary(d)
        s.update({"task": rec["task"], "run": rec["run"], "run_id": rid,
                  "wns_ns_at_100MHz_post_route": s["wns_ns"],
                  "recorded_on_earlier_release": {k: (rec.get("qor") or {}).get(k) for k in ("wns_ns_at_100MHz_post_route", "lut", "ff", "dsp", "power_w")}})
        runs[f'{rec["task"]}/run_{rec["run"]}'] = s
        rows.append(s)
    note = ("Each run's saved design (the agent's RTL and XDC at the end of the run) rebuilt on Vivado 2026.1 with today's flow and "
            "test shell, so counts can differ from the run record by the shell's growth; the run record keeps what its own build reported. "
            "gates_failed lists today's gates, some added after the run (the I/O gate of brief 20B), not the run's own verdict.")
    (HERE / "dev_rebuilds.json").write_text(json.dumps({"vivado": "2026.1", "note": note, "runs": runs, "rows": rows}, indent=1) + "\n")


def inter(rpt: Path, a="clk_a", b="clk_b"):
    for line in rpt.read_text().splitlines():
        f = line.split()
        if len(f) >= 6 and f[0] == a and f[1] == b:
            return {"wns_ns": float(f[2]), "tns_ns": float(f[3]), "failing_endpoints": int(f[4]), "total_endpoints": int(f[5])}


def cdc_exc(rpt: Path):
    out = {}
    for line in rpt.read_text().splitlines():
        m = re.match(r"\s*\d+\s+CDC-\d+\s+\w+\s+.*?\s{2,}\d+\s{2,}(.+?)\s{2,}(u_single|u_gray)/", line)
        if m:
            out["single" if m.group(2) == "u_single" else "gray"] = m.group(1).strip()
    return out


def xpm(before: Path, after: Path):
    x = {"design": "flow/tests/fixtures/xpm_probe (two clocks, one xpm_cdc_single, one xpm_cdc_gray), built as designs/qr_xpm_probe",
         "part": "xc7a100tcsg324-1", "vivado": "2026.1", "clk_a_period_ns": 10, "clk_b_period_ns": 7}
    for k, d, what in (("before", before, "FDA_XPM_CDC=0 FDA_STOP_AFTER=route flow/run_vivado.sh (without flow/xpm_cdc.tcl)"),
                       ("after", after, "FDA_STOP_AFTER=route flow/run_vivado.sh (with flow/xpm_cdc.tcl)")):
        x[k] = {"what": what, **inter(d / "timing_summary.rpt"), "report_cdc_exception": cdc_exc(d / "cdc.rpt")}
    (HERE / "xpm_probe.json").write_text(json.dumps({"xpm_probe": x}, indent=1) + "\n")


def b30():
    b = ROOT / "designs/b30_hil_audio/build/base"
    s = build_summary(b)
    inst = {}
    for line in (b / "utilization_hier.rpt").read_text().splitlines():
        f = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(f) == 10 and f[0].startswith("u_"):
            inst[f[0]] = {"module": f[1], "lut": int(f[2]), "logic_lut": int(f[3]), "lutram": int(f[4]), "srl": int(f[5]),
                          "ff": int(f[6]), "ramb36": int(f[7]), "ramb18": int(f[8]), "dsp": int(f[9])}
    s["instances"] = inst
    (HERE / "b30_hil_audio.json").write_text(json.dumps(s, indent=1) + "\n")


def b2():
    out = {d.name: build_summary(d / "build/base") for d in sorted((ROOT / "designs").glob("b2_*")) if (d / "build/base/gates.json").exists()}
    (HERE / "b2_builds.json").write_text(json.dumps({"vivado": "2026.1", "builds": out}, indent=1) + "\n")


if __name__ == "__main__":
    b2()
    dev()
    xpm(Path(sys.argv[1]), Path(sys.argv[2]))
    b30()
