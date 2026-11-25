#!/usr/bin/env python3
"""Run the brief 204a report checks (flow/report_gates.py) over the recorded builds and count the hits (no Vivado).

    python3 tools/report_gate_hits.py --repo <main checkout with the builds> --session <dir of the one report session> --out results/204a_report_gates

``--repo`` holds the recorded builds (``build/bench/*/build/*``, ``designs/*/build/*``, ``runs/*/*/build/*``: git-ignored, so the
worktree has none). ``--session`` holds the reports the old builds never wrote (logic levels, clock utilisation, congestion, control
sets), made in one Vivado session that only opened the builds' checkpoints (``<design>_synth/``, ``<design>_route/``).
A check whose report an old build lacks is counted as not measured there, never as a pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flow import report_gates as R          # noqa: E402
from flow import gates as G                 # noqa: E402
from flow.gates import parse_utilization    # noqa: E402


def rd(p: Path) -> str | None:
    return p.read_text(errors="replace") if p.is_file() else None


def build_dirs(repo: Path) -> list[Path]:
    out = []
    for pat in ("build/bench/*/build/*", "designs/*/build/*", "runs/*/*/build/*"):
        out += [d for d in sorted(repo.glob(pat)) if d.is_dir() and ((d / "timing_summary_synth.rpt").is_file() or (d / "vivado.log").is_file())]
    return out


def tag(d: Path) -> str:
    """The session's name for a build: ``<design>`` for bench builds, ``<design>_ila`` for the ILA variant of a design."""
    parts = d.parts
    i = len(parts) - 1 - parts[::-1].index("build")
    design = parts[i - 1]
    return design if d.name == "base" else f"{design}_{d.name}"


def measure(d: Path, session: Path) -> dict:
    name = tag(d)
    s_syn, s_rt = session / f"{name}_synth", session / f"{name}_route"
    f: dict[str, list] = defaultdict(list)
    meas: dict[str, bool] = {}
    ts = rd(d / "timing_summary_synth.rpt")
    # LL-02 and the clock rows of the post-synthesis timing paths
    meas["RPT-LL-02"] = ts is not None
    if ts:
        f["RPT-LL-02"] += R.zero_net_delay_findings(ts)
    ll = rd(s_syn / "logic_levels.rpt")
    meas["RPT-LL-01"] = ll is not None
    if ll:
        f["RPT-LL-01"] += R.logic_level_findings(R.parse_logic_levels(ll))
    # clock tree
    cu = [rd(s_syn / "clock_utilization.rpt"), rd(s_rt / "clock_utilization.rpt")]
    cn = rd(d / "clock_networks_synth.rpt")
    meas["RPT-CLK-01"] = any(x is not None for x in cu) or cn is not None
    for x in cu:
        if x:
            f["RPT-CLK-01"] += R.clock_tree_findings(R.parse_clock_utilization(x), None)
    if cn:
        f["RPT-CLK-01"] += R.clock_tree_findings(None, R.parse_clock_networks(cn))
    paths = []
    for n in ("timing_summary_synth.rpt", "timing_summary.rpt", "timing_worst_setup.rpt", "timing_worst_hold.rpt"):
        x = rd(d / n)
        if x:
            f["RPT-CLK-02"] += R.path_clock_findings(R.T.parse_paths(x), n)
            paths.append(n)
    meas["RPT-CLK-02"] = bool(paths)
    # fan-out
    hf = rd(d / "high_fanout_synth.rpt")
    meas["RPT-FO-01"] = hf is not None
    if hf:
        f["RPT-FO-01"] += R.fanout_findings(R.parse_high_fanout(hf), R.parse_clock_summary(ts or ""))
    # log
    log = rd(d / "vivado.log")
    meas["RPT-LOG-01"] = meas["RPT-LOG-02"] = meas["RPT-LOG-03"] = log is not None
    if log:
        inp = rd(d / "inputs.tcl")
        for x in R.log_findings(log, generics=R.build_generics(inp) if inp else None):
            f[x["code"]].append(x)
    # congestion and utilisation
    cg = rd(s_rt / "congestion.rpt")
    meas["RPT-CONG-01"] = log is not None or cg is not None
    tables = R.parse_placer_congestion(log) if log else []
    wins = R.parse_congestion_report(cg) if cg else []
    for x in R.congestion_findings(tables, wins):
        f[x["code"]].append(x)
    ut = rd(d / "utilization.rpt") or rd(d / "utilization_synth.rpt")
    meas["RPT-CONG-02"] = ut is not None
    if ut:
        for x in R.utilization_findings(parse_utilization(ut)):
            f[x["code"]].append(x)
    # control sets
    cs = rd(s_syn / "control_sets.rpt")
    uts = rd(d / "utilization_synth.rpt") or ut
    meas["RPT-CS-01"] = meas["RPT-CS-02"] = cs is not None and uts is not None
    if cs and uts:
        for x in R.control_set_findings(R.parse_control_sets(cs), parse_utilization(uts).get("ff_available")):
            f[x["code"]].append(x)
    meas["RPT-IP-01"] = (d / "ip_status_synth.rpt").is_file()
    met = None
    routed = rd(d / "timing_summary.rpt")
    if routed:
        try:
            met = bool(G.parse_timing_summary(routed)["timing_met"])
        except ValueError:
            met = None
    return {"timing_met_after_route": met, "build": str(d), "tag": name, "measured": meas, "findings": {k: [x["message"][:200] for x in v] for k, v in f.items()},
            "blocking": {k: sum(1 for x in v if x["blocking"]) for k, v in f.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    repo, session, out = Path(a.repo), Path(a.session), Path(a.out)
    rows = [measure(d, session) for d in build_dirs(repo)]
    ids = list(R.INFO)
    summary = {}
    for i in ids:
        m = [r for r in rows if r["measured"].get(i)]
        h = [r for r in m if r["findings"].get(i)]
        summary[i] = {"level": R.INFO[i][0], "source": R.INFO[i][1], "builds_measured": len(m), "builds_with_a_hit": len(h),
                      "hits": sum(len(r["findings"][i]) for r in h),
                      "blocking_hits": sum(r["blocking"].get(i, 0) for r in h), "builds_with_a_hit_that_met_timing": sum(1 for r in h if r["timing_met_after_route"]),
                      "builds_measured_that_met_timing": sum(1 for r in m if r["timing_met_after_route"]), "hit_builds": [r["tag"] for r in h][:12]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "hits.json").write_text(json.dumps({"builds": len(rows), "summary": summary, "per_build": rows}, indent=1))
    print(f"{len(rows)} builds")
    for i, s in summary.items():
        print(f"{i:12s} {s['level']:8s} measured {s['builds_measured']:3d}  builds with a hit {s['builds_with_a_hit']:3d} (met timing: {s['builds_with_a_hit_that_met_timing']} of {s['builds_measured_that_met_timing']})  hits {s['hits']:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
