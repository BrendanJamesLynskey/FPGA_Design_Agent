#!/usr/bin/env python3
"""Brief 178d: repeat place-and-route from the stored synthesis checkpoints with a small clock-period perturbation (no placer seed exists).

    python3 tools/qor/run_178d_seeds.py run [--src <178-tournament worktree>]     # resumable; one Vivado at a time, one heavy slot per run
    python3 tools/qor/run_178d_seeds.py score                                      # writes results/178_tournament/seeds/summary.json

Settings per design: (a) default synthesis + default implementation, (b) the 178b tournament winner, (c) the best AMD -strategy set among the stored
candidates (skipped when it is the winner). Each is run at the nominal clock period times each factor in FACTORS (plus the stored single run as repeat 0).
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import tournament as T  # noqa: E402

OUT = ROOT / "results" / "178_tournament" / "seeds"
BUILD = ROOT / "build" / "seeds"
FACTORS = [0.99, 1.01, 1.02]      # clock-period perturbations of the 3 repeats (Vivado 2026.1 has no placer seed: see README)
CHECK = 1.0                       # one nominal-period rerun of the winner of the first design (determinism check)
DEFAULT_SRC = Path("/home/brendan/Claude_sandbox/_worktrees/178-tournament")
# The stored 178b records (results/178_tournament/runs/) are gitignored by the repo's `runs/` rule, so they are read from the worktree that produced them.
RUNS = DEFAULT_SRC / "results" / "178_tournament" / "runs"


def settings(design: str) -> list[dict]:
    top = json.loads((RUNS / design / "impl_top2.json").read_text())
    base = json.loads((RUNS / design / "impl_base.json").read_text())
    cands = [c for c in top["candidates"] if c["status"] == "ok"]
    win = next(c for c in cands if c.get("rank") == 1)
    amd = max((c for c in cands if c["id"].split("/", 1)[1].startswith("amd:")), key=lambda c: c["wns_ns"])
    out = [{"name": "default", "cand": base["candidates"][0]}, {"name": "winner", "cand": win}]
    if amd["id"] != win["id"]:
        out.append({"name": "best_amd", "cand": amd})
    for s in out:
        c = s["cand"]
        s["id"], s["synth"] = c["id"], c["synth"]
        s["nominal"] = {"wns_ns": c["wns_ns"], "lut": c["lut"], "ff": c["ff"]}
    return out


def designs() -> list[str]:
    return sorted(p.name for p in RUNS.iterdir() if p.is_dir())


def clock_ns(design: str) -> float:
    return float(json.loads((RUNS / design / "impl_top2.json").read_text())["clock_ns"])


def job_list() -> list[dict]:
    jobs = []
    for f in FACTORS:                                  # round-robin so a partial run is balanced
        for d in designs():
            for s in settings(d):
                jobs.append({"design": d, "setting": s, "factor": f})
    d0 = designs()[0]
    jobs.append({"design": d0, "setting": next(s for s in settings(d0) if s["name"] == "winner"), "factor": CHECK})
    return jobs


def tcl(src_dcp: Path, cand: dict, wd: Path, period: float) -> str:
    base = T.impl_tcl(src_dcp, cand, wd)
    line = f"create_clock -period {period:.4f} -name clk [get_ports clk]\n"
    marker = f"open_checkpoint {T._tcl(str(src_dcp))}\n"
    assert marker in base
    return base.replace(marker, marker + line)


def run(src: Path) -> None:
    jobs = job_list()
    for i, j in enumerate(jobs):
        d, s, f = j["design"], j["setting"], j["factor"]
        wd = BUILD / d / s["name"] / f"p{f:.2f}"
        if (wd / "done.txt").exists():
            continue
        dcp = BUILD / "src" / d / f"{s['synth']}.dcp"
        if not dcp.exists():
            dcp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / "build" / "tournament" / d / "synth" / s["synth"] / "post_synth.dcp", dcp)
        wd.mkdir(parents=True, exist_ok=True)
        period = round(clock_ns(d) * f, 4)
        (wd / "run.tcl").write_text(tcl(dcp, s["cand"], wd, period))
        now = datetime.datetime.now()
        lock = T.take_slot(f"178d: Vivado impl seed repeat {d} {s['name']} x{f:.2f}, peak 4G, start {now:%H:%M}, expected end "
                           f"{(now + datetime.timedelta(minutes=15)):%H:%M}")
        try:
            print(f"[{i + 1}/{len(jobs)}] {d} {s['name']} {s['id']} period {period} ns", flush=True)
            subprocess.run(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=5G", "nice", "-n", "15", T.vivado(), "-mode", "batch",
                            "-nojournal", "-log", str(wd / "vivado.log"), "-source", str(wd / "run.tcl")], check=False)
        finally:
            T.release_slot(lock, "178d")
        if not (wd / "done.txt").exists():
            (wd / "error.txt").write_text("no done.txt after the run (see vivado.log)\n")
        r = T.parse(wd)
        r.update({"design": d, "setting": s["name"], "id": s["id"], "factor": f, "period_ns": period})
        (wd / "record.json").write_text(json.dumps(r, indent=1))
        print("   ", {k: r.get(k) for k in ("status", "wns_ns", "lut", "ff", "runtime_s")}, flush=True)


def score() -> None:
    summ = {"schema": "fda-seeds/1", "date": datetime.date.today().isoformat(), "factors": FACTORS, "designs": {}}
    for d in designs():
        nom = clock_ns(d)
        rows = {}
        for s in settings(d):
            samples = [{"factor": 1.0, "period_ns": nom, "wns_ns": s["nominal"]["wns_ns"], "source": "178b stored run"}]
            for f in FACTORS + [CHECK]:
                p = BUILD / d / s["name"] / f"p{f:.2f}" / "record.json"
                if p.exists():
                    r = json.loads(p.read_text())
                    if r.get("status") == "ok":
                        samples.append({"factor": f, "period_ns": r["period_ns"], "wns_ns": r["wns_ns"], "lut": r["lut"], "ff": r["ff"],
                                        "source": "178d repeat" if f != CHECK else "178d determinism check"})
            for x in samples:      # WNS referred to the nominal period: nominal - (period - WNS) = WNS + (nominal - period)
                x["wns_nominal_ns"] = round(x["wns_ns"] + nom - x["period_ns"], 3)
            rep = [x["wns_nominal_ns"] for x in samples if x["source"] != "178d determinism check"]
            rows[s["name"]] = {"id": s["id"], "samples": samples, "n": len(rep), "mean": round(statistics.mean(rep), 3),
                               "min": min(rep), "max": max(rep), "spread": round(max(rep) - min(rep), 3),
                               "sd": round(statistics.stdev(rep), 3) if len(rep) > 1 else None,
                               # the stored run is the best of ~20 (winner) so it is biased high: the mean of the 3 fresh repeats is the unbiased estimate
                               "fresh_mean": round(statistics.mean(rep[1:]), 3), "fresh_min": min(rep[1:]), "fresh_max": max(rep[1:])}
        w, df = rows["winner"], rows["default"]
        gain = round(w["mean"] - df["mean"], 3)
        fresh_gain = round(w["fresh_mean"] - df["fresh_mean"], 3)
        rows["_verdict"] = {"winner_minus_default_mean": gain, "winner_minus_default_fresh_mean": fresh_gain,
                            "fresh_winner_min_above_fresh_default_max": w["fresh_min"] > df["fresh_max"], "max_spread": max(rows[k]["spread"] for k in ("default", "winner")),
                            "winner_min_above_default_max": w["min"] > df["max"],
                            "gain_larger_than_spread": gain > max(rows[k]["spread"] for k in ("default", "winner"))}
        if "best_amd" in rows:
            a = rows["best_amd"]
            rows["_verdict"]["winner_minus_best_amd_mean"] = round(w["mean"] - a["mean"], 3)
            rows["_verdict"]["winner_min_above_amd_max"] = w["min"] > a["max"]
            rows["_verdict"]["winner_minus_best_amd_fresh_mean"] = round(w["fresh_mean"] - a["fresh_mean"], 3)
        summ["designs"][d] = {"clock_ns": nom, "settings": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1))
    recs = OUT / "records"
    recs.mkdir(exist_ok=True)
    for p in BUILD.glob("*/*/*/record.json"):
        dst = recs / p.parents[2].name / p.parents[1].name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst / f"{p.parent.name}.json")
    print(json.dumps({d: {k: v for k, v in x["settings"].items()} for d, x in summ["designs"].items()}, indent=1)[:6000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "score"])
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    a = ap.parse_args()
    run(Path(a.src)) if a.cmd == "run" else score()
