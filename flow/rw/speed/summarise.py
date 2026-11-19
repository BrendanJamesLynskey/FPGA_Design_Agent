#!/usr/bin/env python3
"""Brief 100B: collect the timing records of experiments 1 and 2 into results/b100b/ (small files only: meas.json, run.json, route status, timing
reports, logs tails) and write summary.json and summary.md. Everything quoted in the report comes from these files.
    python3 flow/rw/speed/summarise.py [work dir]
"""
from __future__ import annotations

import json
import re
import shutil
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
W = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Claude_sandbox/_worktrees/100b-work"
DST = ROOT / "results" / "b100b"
KEEP = (".meas.json", "_run.json", "_route_status.txt", "_timing.rpt", "_reuse.rpt")


def collect() -> None:
    for exp in sorted(W.glob("e[12]*")):
        if not exp.is_dir():
            continue
        out = DST / exp.name
        out.mkdir(parents=True, exist_ok=True)
        for f in list(exp.glob("*.meas.json")) + list(exp.glob("*.d/*")) + [exp / "failures.txt"]:
            if f.is_file() and (f.name.endswith(KEEP) or f.name == "failures.txt"):
                shutil.copy(f, out / (f.parent.name.removesuffix(".d") + "_" + f.name if f.parent != exp else f.name))
        for f in exp.glob("*.log"):
            tail = f.read_text(errors="replace").splitlines()[-25:]
            (out / (f.stem + ".log.tail")).write_text("\n".join(tail) + "\n")


def load(p: Path):
    return json.loads(p.read_text()) if p.is_file() else None


def route_status(p: Path) -> dict:
    t = p.read_text() if p.is_file() else ""
    g = lambda pat: int(m.group(1)) if (m := re.search(pat + r"\.*\s*:\s*(\d+)", t)) else 0
    return {"routing_errors": g(r"# of nets with routing errors"), "unrouted": g(r"# of unrouted nets")}


def agg(v: list[float]) -> str:
    return f"{st.mean(v):.0f} ({min(v):.0f}-{max(v):.0f}, n={len(v)})" if v else "n/a"


def e1() -> dict:
    d = DST / "e1"
    res: dict = {}
    for r in (1, 2, 3):
        m = lambda t: load(d / f"{t}.meas.json")
        rec = {}
        for arm in ("F", "I"):
            mm, run = m(f"{arm}{r}"), load(d / f"{arm}{r}_res_run.json")
            if mm and mm["rc"] != 0:
                rec[arm] = {"failed": True, "wall_s": mm["wall_s"], "rc": mm["rc"]}
            elif mm:
                rec[arm] = {"wall_s": mm["wall_s"], "cpu_s": mm["cpu_s"], "peak_mib": mm["peak_mib"], "load_start": mm["load_start"],
                            "wns_ns": run and run["wns_ns"], "whs_ns": run and run["whs_ns"], "laps": run and run["times_s"],
                            **route_status(d / f"{arm}{r}_res_route_status.txt")}
        b, s = m(f"Sblk{r}"), m(f"Sstamp{r}")
        if b and s:
            run = load(d / f"Sstamp{r}_res_run.json")
            rec["S"] = {"wall_s": round(b["wall_s"] + s["wall_s"], 1), "cpu_s": round(b["cpu_s"] + s["cpu_s"], 1), "block_ooc_wall_s": b["wall_s"],
                        "stamp_wall_s": s["wall_s"], "peak_mib": max(b["peak_mib"], s["peak_mib"]), "load_start": s["load_start"],
                        "wns_ns": run and run["wns_ns"], "whs_ns": run and run["whs_ns"], "laps": run and run["times_s"],
                        **route_status(d / f"Sstamp{r}_res_route_status.txt")}
            rw, ref = m(f"S2rw{r}"), m(f"S2ref{r}")
            if rw and rw["rc"] != 0:
                rec["S2"] = {"failed": True, "wall_s": rw["wall_s"], "rc": rw["rc"]}
            elif rw and ref and run:
                lap = run["times_s"]
                # stamp up to and including placement (synth, setup, place laps + Vivado start-up ~ stamp wall minus route and later), RWRoute, referee
                pre = s["wall_s"] - lap["route"] - (s["wall_s"] - sum(lap.values()) - 0)  # wall minus laps = start-up + writes/reports
                refrun = load(d / f"S2ref{r}_res_run.json")
                rec["S2"] = {"wall_s": round(b["wall_s"] + (s["wall_s"] - lap["route"]) + rw["wall_s"] + ref["wall_s"], 1),
                             "rw_route_wall_s": rw["wall_s"], "referee_wall_s": ref["wall_s"], "rw_peak_mib": rw["peak_mib"],
                             "wns_ns": refrun and refrun["wns_ns"], "whs_ns": refrun and refrun["whs_ns"],
                             **route_status(d / f"S2ref{r}_res_route_status.txt"),
                             "note": "stamp wall minus its Vivado route lap, plus RWRoute and the Vivado referee; the stamp's post-route reports are still in the stamp wall"}
        res[r] = rec
    return res


def e2() -> dict:
    out: dict = {}
    for d in sorted(DST.glob("e2_*")):
        rows: dict = {}
        for f in sorted(d.glob("*.meas.json")):
            tag = f.name.removesuffix(".meas.json")
            if tag.startswith("prep"):
                continue
            mm = load(f)
            parts = tag.split("_"); arm, per, rep = parts[0], "_".join(parts[1:-1]), parts[-1]
            key = f"{arm}_{per}"
            rows.setdefault(key, {}).setdefault(rep, {})["meas"] = mm
            run = load(d / f"{tag}_res_run.json")
            if run:
                rows[key][rep]["wns_ns"], rows[key][rep]["whs_ns"] = run["wns_ns"], run["whs_ns"]
                rows[key][rep]["laps"] = run["times_s"]
                rows[key][rep].update(route_status(d / f"{tag}_res_route_status.txt"))
        out[d.name] = rows
    return out


def main() -> None:
    collect()
    out = {"e1": e1(), "e2": e2()}
    (DST / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    md = ["# Brief 100B summary (generated by flow/rw/speed/summarise.py)\n", "## Experiment 1: one-block edit (K26, 1 thread)\n",
          "| arm | wall s mean (min-max) | CPU s mean | peak MiB | WNS ns (per rep) | WHS ns | routing errors / unrouted |", "|---|---|---|---|---|---|---|"]
    for arm in ("F", "I", "S", "S2"):
        rs = [out["e1"][r][arm] for r in out["e1"] if arm in out["e1"][r]]
        if rs and rs[0].get("failed"):
            md.append(f"| {arm} | FAILED in all {len(rs)} runs after {agg([x['wall_s'] for x in rs])} s (see the e1 logs) | | | | | |")
        elif rs:
            md.append(f"| {arm} | {agg([x['wall_s'] for x in rs])} | {agg([x['cpu_s'] for x in rs]) if 'cpu_s' in rs[0] else ''} | "
                      f"{max(x.get('peak_mib', x.get('rw_peak_mib', 0)) for x in rs)} | {', '.join(str(x['wns_ns']) for x in rs)} | "
                      f"{', '.join(str(x['whs_ns']) for x in rs)} | {', '.join(str(x['routing_errors']) + '/' + str(x['unrouted']) for x in rs)} |")
    for name, rows in out["e2"].items():
        md += ["", f"## Experiment 2: router, {name}\n", "| arm_period | wall s (reps) | CPU s | peak MiB | WNS ns (referee) | WHS | errors/unrouted | closes |", "|---|---|---|---|---|---|---|---|"]
        for key, reps in rows.items():
            if key.startswith(("RTref", "RNref")):
                continue
            ref = rows.get(key.replace("RT", "RTref", 1) if key.startswith("RT") else key.replace("RN", "RNref", 1), {}) if not key.startswith("V") else reps
            walls = [reps[r]["meas"]["wall_s"] for r in reps]
            cpus = [reps[r]["meas"]["cpu_s"] for r in reps]
            peak = max(reps[r]["meas"]["peak_mib"] for r in reps)
            wns = [ref[r].get("wns_ns") for r in ref]
            closes = sum(1 for w in wns if w is not None and w >= 0)
            md.append(f"| {key} | {agg(walls)} | {agg(cpus)} | {peak} | {', '.join(str(w) for w in wns)} | {', '.join(str(ref[r].get('whs_ns')) for r in ref)} | "
                      f"{', '.join(str(ref[r].get('routing_errors', '?')) + '/' + str(ref[r].get('unrouted', '?')) for r in ref)} | {closes}/{len(wns)} |")
    (DST / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
