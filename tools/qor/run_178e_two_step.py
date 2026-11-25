#!/usr/bin/env python3
"""Brief 178e: the cheap two-step tournament. Step 1: synthesis, default against retiming (the two stored 178b synthesis results). Step 2: on the better
netlist, AMD's Performance_* implementation sets and the default, each place and route run once.

    python3 tools/qor/run_178e_two_step.py plan                      # print the picked netlist and the runs still needed per design
    python3 tools/qor/run_178e_two_step.py run [--src <178 worktree>] # resumable; workers share the job list through claim directories
    python3 tools/qor/run_178e_two_step.py validate [--worker W]     # 3 clock-period repeats (178d method) of the set step 2 picked, where 178d has none
    python3 tools/qor/run_178e_two_step.py score                     # writes results/178_tournament/two_step/summary.json from the records

Place and route runs reuse the stored 178b results where the netlist and the set are identical (same Tcl, deterministic: 178d re-ran one and got the
same WNS), and run only the rest. One heavy slot per run (``peak 4G``, ``Vivado impl``), one thread, under ``systemd-run MemoryMax=5G``.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import tournament as T  # noqa: E402

OUT = ROOT / "results" / "178_tournament" / "two_step"
REC = OUT / "records"
BUILD = ROOT / "build" / "two_step"
DEFAULT_SRC = Path("/home/brendan/Claude_sandbox/_worktrees/178-tournament")
RUNS = DEFAULT_SRC / "results" / "178_tournament" / "runs"     # stored 178b records (ignored by the repo's runs/ rule, so read from the worktree)
SEEDS = ROOT / "results" / "178_tournament" / "seeds" / "summary.json"


def designs() -> list[str]:
    return sorted(p.name for p in RUNS.iterdir() if p.is_dir())


def load(design: str, name: str) -> dict:
    return json.loads((RUNS / design / name).read_text())


def pick(design: str) -> dict:
    return T.two_step_pick(load(design, "synth.json")["candidates"])


def impl_set(set_id: str) -> dict:
    return next(c for c in T.impl_candidates([set_id]) if c["id"] == set_id)


def stored(design: str, synth: str, set_id: str) -> dict | None:
    """The stored 178b result for this netlist and set, if any."""
    for f in ("impl_base.json", "impl_top2.json"):
        for c in load(design, f)["candidates"]:
            if c["id"] == f"{synth}/{set_id}" and c["status"] == "ok":
                return c
    return None


def jobs() -> list[dict]:
    out = []
    for d in designs():
        p = pick(d)
        for sid in T.performance_menu():
            out.append({"design": d, "synth": p["id"], "set": sid, "stored": stored(d, p["id"], sid)})
    return out


def rec_path(j: dict) -> Path:
    return REC / j["design"] / (j["set"].replace(":", "_") + ".json")


def plan() -> None:
    js = jobs()
    for d in designs():
        p = pick(d)
        mine = [j for j in js if j["design"] == d]
        print(f"{d}: step 1 picks {p['id']} (WNS {p['wns_ns']}, LUT {p['lut']}, FF {p['ff']}); step 2 sets {len(mine)}, stored {sum(1 for j in mine if j['stored'])}, "
              f"to run {sum(1 for j in mine if not j['stored'])}")


def run(src: Path, worker: str) -> None:
    for j in jobs():
        d, sid, synth = j["design"], j["set"], j["synth"]
        if j["stored"]:
            continue
        rp = rec_path(j)
        claim = BUILD / "claims" / d / sid.replace(":", "_")
        wd = BUILD / d / sid.replace(":", "_")
        if rp.exists() or (wd / "done.txt").exists():
            continue
        try:
            claim.mkdir(parents=True)
        except FileExistsError:
            continue                      # another worker has it
        dcp = BUILD / "src" / d / f"{synth}.dcp"
        if not dcp.exists():
            dcp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / "build" / "tournament" / d / "synth" / synth / "post_synth.dcp", dcp)
        wd.mkdir(parents=True, exist_ok=True)
        cand = dict(impl_set(sid), id=f"{synth}/{sid}", synth=synth)
        (wd / "run.tcl").write_text(T.impl_tcl(dcp, cand, wd))
        now = datetime.datetime.now()
        lock = T.take_slot(f"178e: Vivado impl two-step {d} {sid}, peak 4G, start {now:%H:%M}, expected end {(now + datetime.timedelta(minutes=12)):%H:%M}")
        try:
            print(f"[{worker}] {d} {synth}/{sid}", flush=True)
            subprocess.run(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=5G", "nice", "-n", "15", T.vivado(), "-mode", "batch",
                            "-nojournal", "-log", str(wd / "vivado.log"), "-source", str(wd / "run.tcl")], check=False)
        finally:
            T.release_slot(lock, "178e")
        if not (wd / "done.txt").exists():
            (wd / "error.txt").write_text("no done.txt after the run (see vivado.log)\n")
        r = T.parse(wd)
        r.update({"design": d, "id": cand["id"], "synth": synth, "set": sid, "clock_ns": load(d, "impl_base.json")["clock_ns"], "source": "178e run"})
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(r, indent=1))
        print("   ", {k: r.get(k) for k in ("status", "wns_ns", "lut", "ff", "runtime_s")}, flush=True)


FACTORS = [0.99, 1.01, 1.02]       # the 178d perturbations (Vivado 2026.1 has no placer seed)
VAL = OUT / "validate"


def step2_pick(design: str) -> dict:
    """The set the tool's own score picks among step 2's results (0.05 ns bucket, then area, then menu order)."""
    rows = results(design)
    return T.rank([{"id": r["set"], "wns_ns": r["wns_ns"], "lut": r["lut"], "ff": r["ff"], "levels": 0, "order": i, "status": "ok"} for i, r in enumerate(rows)], 1)[0]


def covered_by_178d(design: str) -> str | None:
    """The 178d setting ('winner' or 'best_amd') that is exactly this netlist and set, if any: its four samples are then the repeats of the two-step pick."""
    sw = json.loads(SEEDS.read_text())["designs"][design]["settings"]
    want = f"{pick(design)['id']}/{step2_pick(design)['id']}"
    return next((k for k in ("best_amd", "winner") if k in sw and sw[k]["id"] == want), None)


def validate(src: Path, worker: str) -> None:
    sys.path.insert(0, str(ROOT / "tools" / "qor"))
    import run_178d_seeds as S
    for d in designs():
        if covered_by_178d(d):
            continue
        sid, synth = step2_pick(d)["id"], pick(d)["id"]
        for f in FACTORS:
            wd = BUILD / "validate" / d / f"p{f:.2f}"
            claim = BUILD / "claims_validate" / d / f"p{f:.2f}"
            if (VAL / d / f"p{f:.2f}.json").exists():
                continue
            try:
                claim.mkdir(parents=True)
            except FileExistsError:
                continue
            dcp = BUILD / "src" / d / f"{synth}.dcp"
            if not dcp.exists():
                dcp.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / "build" / "tournament" / d / "synth" / synth / "post_synth.dcp", dcp)
            wd.mkdir(parents=True, exist_ok=True)
            nom = float(load(d, "impl_base.json")["clock_ns"])
            period = round(nom * f, 4)
            cand = dict(impl_set(sid), id=f"{synth}/{sid}", synth=synth)
            (wd / "run.tcl").write_text(S.tcl(dcp, cand, wd, period))
            now = datetime.datetime.now()
            lock = T.take_slot(f"178e: Vivado impl two-step validate {d} {sid} x{f:.2f}, peak 4G, start {now:%H:%M}, expected end {(now + datetime.timedelta(minutes=12)):%H:%M}")
            try:
                print(f"[{worker}] validate {d} {synth}/{sid} period {period}", flush=True)
                subprocess.run(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=5G", "nice", "-n", "15", T.vivado(), "-mode", "batch",
                                "-nojournal", "-log", str(wd / "vivado.log"), "-source", str(wd / "run.tcl")], check=False)
            finally:
                T.release_slot(lock, "178e")
            if not (wd / "done.txt").exists():
                (wd / "error.txt").write_text("no done.txt after the run (see vivado.log)\n")
            r = T.parse(wd)
            r.update({"design": d, "id": cand["id"], "factor": f, "period_ns": period, "nominal_ns": nom})
            (VAL / d).mkdir(parents=True, exist_ok=True)
            (VAL / d / f"p{f:.2f}.json").write_text(json.dumps(r, indent=1))


def results(design: str) -> list[dict]:
    """Step 2 results for one design, in menu order: stored where identical, else the 178e record."""
    rows = []
    for j in jobs():
        if j["design"] != design:
            continue
        if j["stored"]:
            c = j["stored"]
            rows.append({"set": j["set"], "wns_ns": c["wns_ns"], "lut": c["lut"], "ff": c["ff"], "runtime_s": c["runtime_s"], "source": "178b stored"})
        elif rec_path(j).exists():
            r = json.loads(rec_path(j).read_text())
            if r.get("status") == "ok":
                rows.append({"set": j["set"], "wns_ns": r["wns_ns"], "lut": r["lut"], "ff": r["ff"], "runtime_s": r["runtime_s"], "source": "178e run"})
    return rows


def first_pass(rows: list[dict], order: list[str]) -> dict | None:
    """The rule 'walk the sets in this order, stop at the first with WNS >= 0': the set it stops at (or the best seen if none passes) and the CPU spent."""
    by = {r["set"]: r for r in rows}
    cpu, best = 0, None
    for sid in order:
        if sid not in by:
            continue
        r = by[sid]
        cpu += r["runtime_s"]
        if best is None or r["wns_ns"] > best["wns_ns"]:
            best = r
        if r["wns_ns"] >= 0:
            return {"stop_set": sid, "wns_ns": r["wns_ns"], "cpu_s": cpu, "stopped": True}
    return {"stop_set": best["set"], "wns_ns": best["wns_ns"], "cpu_s": cpu, "stopped": False} if best else None


TOOL_ORDER = T.performance_menu()                              # cheapest first: the order --stop-at-pass walks
ALPHA_ORDER = ["default"] + sorted(TOOL_ORDER[1:])           # the strategy file's (alphabetical) order, as a sensitivity check


def repeats(design: str, sid: str) -> dict | None:
    """Four-sample statistics (stored run + 3 clock-period repeats, WNS referred to the nominal period) for the two-step pick: from 178d where it
    is the same netlist and set, else from this brief's validation runs."""
    seeds = json.loads(SEEDS.read_text())["designs"][design]
    k = covered_by_178d(design)
    if k:
        x = seeds["settings"][k]
        return {"source": f"178d {k}", "mean": x["mean"], "min": x["min"], "max": x["max"], "spread": x["spread"], "fresh_mean": x["fresh_mean"], "n": x["n"]}
    nom = seeds["clock_ns"]
    first = next(r for r in results(design) if r["set"] == sid)["wns_ns"]
    xs = [first]
    for f in FACTORS:
        p = VAL / design / f"p{f:.2f}.json"
        if p.exists():
            r = json.loads(p.read_text())
            if r.get("status") == "ok":
                xs.append(round(r["wns_ns"] + nom - r["period_ns"], 3))
    if len(xs) < 2:
        return None
    return {"source": "178e validation", "mean": round(statistics.mean(xs), 3), "min": min(xs), "max": max(xs), "spread": round(max(xs) - min(xs), 3),
            "fresh_mean": round(statistics.mean(xs[1:]), 3), "n": len(xs)}


def score() -> None:
    seeds = json.loads(SEEDS.read_text())["designs"]
    summ = {"schema": "fda-two-step/1", "date": datetime.date.today().isoformat(), "designs": {}}
    for d in designs():
        p = pick(d)
        syn = {c["id"]: c for c in load(d, "synth.json")["candidates"]}
        rows = results(d)
        full = load(d, "impl_top2.json")
        base = load(d, "impl_base.json")["candidates"][0]
        full_cpu = sum(c.get("runtime_s") or 0 for c in load(d, "synth.json")["candidates"]) + sum(c.get("runtime_s") or 0 for c in full["candidates"]) + base["runtime_s"]
        step1_cpu = sum(syn[i]["runtime_s"] for i in T.TWO_STEP_SYNTH)
        step2_cpu = sum(r["runtime_s"] for r in rows)
        best = max(rows, key=lambda r: r["wns_ns"])
        sp = step2_pick(d)
        rep = repeats(d, sp["id"])
        sw = seeds[d]["settings"]
        t_win, t_def = sw["winner"], sw["default"]
        noise = max(t_win["spread"], t_def["spread"], rep["spread"] if rep else 0)
        verdict = None
        if rep:
            diff = round(rep["mean"] - t_win["mean"], 3)
            verdict = {"two_step_pick_minus_tournament_winner_mean": diff, "noise_floor_ns": noise, "within_noise": abs(diff) <= noise,
                       "two_step_pick_minus_default_mean": round(rep["mean"] - t_def["mean"], 3),
                       "gain_over_default_beyond_noise": (rep["mean"] - t_def["mean"]) > noise}
        rules = {}
        nz = max(t_win["spread"], t_def["spread"])                 # single-run rule outcomes: noise floor = the larger 178d spread of winner and default
        for name, res in (("pick the best of all 15 (tool rank)", {"stop_set": sp["id"], "wns_ns": next(r for r in rows if r["set"] == sp["id"])["wns_ns"], "cpu_s": step2_cpu, "stopped": False}),
                          ("default implementation only", first_pass(rows, ["default"])),
                          ("stop at first WNS>=0, cheapest first (the tool's order)", first_pass(rows, TOOL_ORDER)),
                          ("stop at first WNS>=0, alphabetical order", first_pass(rows, ALPHA_ORDER))):
            res = dict(res)
            res["total_cpu_s"] = step1_cpu + res["cpu_s"]
            res["share_of_full_tournament"] = round(res["total_cpu_s"] / full_cpu, 3)
            res["vs_tournament_winner_mean"] = round(res["wns_ns"] - t_win["mean"], 3)
            res["within_noise_of_tournament"] = res["wns_ns"] >= t_win["mean"] - nz
            res["meets_timing"] = res["wns_ns"] >= 0
            rules[name] = res
        summ["designs"][d] = {"clock_ns": full["clock_ns"], "step1_pick": p["id"], "step1_cpu_s": step1_cpu, "step2_runs": len(rows), "step2_cpu_s": step2_cpu,
                              "step2_cpu_new_s": sum(r["runtime_s"] for r in rows if r["source"] == "178e run"),
                              "full_tournament_cpu_s": full_cpu, "step2_best_single_run": best, "step2_ranked_pick": sp["id"], "pick_repeats": rep, "verdict": verdict,
                              "stop_rules": rules, "step2_default": next((r for r in rows if r["set"] == "default"), None),
                              "noise_single_run_ns": nz, "tournament_winner_id": t_win["id"], "tournament_winner_stored_run": t_win["samples"][0]["wns_ns"],
                              "tournament_winner_mean": t_win["mean"], "tournament_winner_spread": t_win["spread"],
                              "default_mean": t_def["mean"], "default_spread": t_def["spread"],
                              "best_amd_id": sw["best_amd"]["id"] if "best_amd" in sw else None, "best_amd_mean": sw["best_amd"]["mean"] if "best_amd" in sw else None,
                              "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps({d: {k: v for k, v in x.items() if k != "rows"} for d, x in summ["designs"].items()}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "run", "validate", "score"])
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--worker", default=str(os.getpid()))
    a = ap.parse_args()
    {"plan": plan, "run": lambda: run(Path(a.src), a.worker), "validate": lambda: validate(Path(a.src), a.worker), "score": score}[a.cmd]()
