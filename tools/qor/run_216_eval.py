#!/usr/bin/env python3
"""Brief 216 live evaluation (pre-registered in results/216_closure_recipes/preregistration.md). Needs Vivado and the 178 post-synthesis checkpoints.

    python3 tools/qor/run_216_eval.py stage                 # copy the checkpoints this evaluation needs into build/216
    python3 tools/qor/run_216_eval.py run [--only design]   # run every (design, arm) not yet done; a heavy slot is taken per task and released after it
    python3 tools/qor/run_216_eval.py summary               # records.jsonl + the paired analysis (tools/stats/fpga_ablate.py)

Arms: guided, shuffled216, shuffled217 (control = the recorded 178 default flow, not re-run). One Vivado at a time inside one slot, each run under
``systemd-run --user --scope -p MemoryMax=<peak+1>G nice -n 15``. Identical plans of one design are run once and reused across arms (Vivado is
deterministic for identical input); each arm still counts them as its own runs. A task stopped by the slot or the memory cap is recorded with a
stop reason and is run again on the next ``run``; it is never scored.
"""
from __future__ import annotations

import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "stats"))
from agent.graph import closure_recipes as R          # noqa: E402
from agent.graph import closure_search as S           # noqa: E402
from flow import closure_recipe_run as CR             # noqa: E402
from flow import tournament as T                      # noqa: E402

HANDOFF = Path(os.environ.get("TOURNAMENT_HANDOFF", "/home/brendan/Claude_sandbox/_handoff"))
SRC178 = Path(os.environ.get("EVAL216_SRC", "/home/brendan/Claude_sandbox/_worktrees/178-tournament/build/tournament"))
BUILD = ROOT / "build" / "216"
RES = ROOT / "results" / "216_closure_recipes"
LIVE = RES / "live"
RUNS178 = ROOT / "results" / "178_tournament" / "runs"
DESIGNS = ["adder_csel_a7_w64b16", "divider_restpipe_k26_w16", "isqrt_restpipe_k26_w32", "lzc_treebarrel_k26_w32", "mac_fabric_k26"]
SYNTH_KEYS = {"default": "default", "retiming": "retime", "keep_equivalent_registers": "keep_eq"}     # synth_key -> 178 synthesis candidate
PEAK_G = 4.0
BUDGET, BEAM = 6, 3
ARMS = ["guided", "shuffled216", "shuffled217"]
PREFIX = "216"


def spec(design: str) -> dict:
    import yaml
    return yaml.safe_load((RUNS178.parent / "specs" / f"{design}.yaml").read_text())


def stage() -> None:
    for d in DESIGNS:
        for k, c in SYNTH_KEYS.items():
            dst = BUILD / "synth" / d / k / "post_synth.dcp"
            src = SRC178 / d / "synth" / c / "post_synth.dcp"
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    print("staged", sum(1 for _ in (BUILD / "synth").rglob("*.dcp")), "checkpoints")


def order_of_tasks(seed: int = 216) -> list[tuple[str, str]]:
    """Designs shuffled, and within a design the arm order shuffled, by one seeded generator (pre-registered)."""
    rng = random.Random(seed)
    ds = DESIGNS[:]
    rng.shuffle(ds)
    out = []
    for d in ds:
        arms = ARMS[:]
        rng.shuffle(arms)
        out += [(d, a) for a in arms]
    return out


def root_of(design: str) -> dict:
    b = json.loads((RUNS178 / design / "impl_base.json").read_text())
    c = next(c for c in b["candidates"] if c["id"] == "default/default")
    return {**c, "status": "ok", "clock_ns": spec(design)["clock_ns"]}


def features(design: str) -> S.Features:
    wp = SRC178 / design / "impl_base" / "default_default" / "worst_path.rpt"
    r = root_of(design)
    if wp.exists():
        return S.Features.from_path_report(wp.read_text(), whs_ns=r.get("whs_ns"))
    return S.Features(wns_ns=r["wns_ns"], whs_ns=r.get("whs_ns"), logic_levels=r.get("levels"), clock_ns=r["clock_ns"])


def take_slot(text: str) -> Path:
    t0 = time.time()
    while True:
        p = subprocess.run([str(HANDOFF / "take_heavy_slot.sh"), text], capture_output=True, text=True)
        if p.returncode == 0:
            return Path(p.stdout.strip().splitlines()[-1])
        if time.time() - t0 > 8 * 3600:
            raise SystemExit("BLOCKED: no heavy slot in 8 h")
        time.sleep(120)


def release(lock: Path) -> None:
    try:
        if lock.read_text().startswith(PREFIX + ":"):
            lock.unlink()
    except FileNotFoundError:
        pass


def run_task(design: str, arm: str) -> dict:
    sp = spec(design)
    ctx = R.Context(family=CR.family_of(sp["part"]), clock_ns=float(sp["clock_ns"]))
    root = root_of(design)
    feats = features(design)
    cache_f = LIVE / design / "cache.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    synth = {k: BUILD / "synth" / design / k / "post_synth.dcp" for k in SYNTH_KEYS if (BUILD / "synth" / design / k / "post_synth.dcp").exists()}
    log: list[dict] = []
    stop = {"reason": None}

    def runner(plan: R.ImplPlan, nid: str) -> dict:
        key = plan.key()
        k = CR.synth_key(plan)
        if k not in synth:
            return {"status": "no synth checkpoint", "synth_key": k, "clock_ns": ctx.clock_ns}
        if key in cache:
            out = dict(cache[key], cached=True)
        else:
            out = CR.run_one(plan, synth[k], LIVE / design / "work" / f"p{len(cache)}", PEAK_G, ctx.clock_ns)
            if out.get("status", "ok").startswith("vivado exit") or out.get("status") == "not run":
                stop["reason"] = "memory_cap_or_vivado_killed"
                raise RuntimeError(out["status"])
            cache[key] = out
            cache_f.parent.mkdir(parents=True, exist_ok=True)
            cache_f.write_text(json.dumps(cache, indent=1))
        out["node"] = nid
        log.append(out)
        return out

    ordering = None if arm == "guided" else S.shuffled(int(arm.replace("shuffled", "")))
    priors = S.Priors.from_178()
    t0 = time.time()
    res = S.search(root, feats, ctx, runner, budget=BUDGET, beam=BEAM, margin=0.1, priors=priors, exclude=design, ordering=ordering)
    best = res.best.outcome
    clock = ctx.clock_ns
    rec = {"arm": arm, "design": design, "seed": 1, "status": "ok", "stop_reason": res.stop, "wns_ns": best.get("wns_ns"), "whs_ns": best.get("whs_ns"),
           "wns_gain_ns": round(best["wns_ns"] - root["wns_ns"], 3), "lut": best.get("lut"), "ff": best.get("ff"), "vivado_runs": res.runs,
           "fmax_mhz": round(1000 / (clock - best["wns_ns"]), 1), "clock_ns": clock, "part": sp["part"], "wall_s": round(time.time() - t0, 1),
           "cpu_s_runs": sum(o.get("runtime_s") or 0 for o in log if not o.get("cached")), "search": res.to_dict(),
           "date": datetime.datetime.now().isoformat(timespec="seconds")}
    return rec


def run(only: str | None) -> None:
    LIVE.mkdir(parents=True, exist_ok=True)
    for design, arm in order_of_tasks():
        if only and design != only:
            continue
        out = LIVE / f"{design}__{arm}.json"
        if out.exists() and json.loads(out.read_text()).get("status") == "ok":
            continue
        t = datetime.datetime.now()
        lock = take_slot(f"{PREFIX}: Vivado impl, closure recipe eval {design} {arm}, {t:%H:%M}, expected end {(t + datetime.timedelta(minutes=40)):%H:%M}, peak {int(PEAK_G)}G")
        try:
            rec = run_task(design, arm)
        except RuntimeError as e:
            rec = {"arm": arm, "design": design, "status": "not_run", "stop_reason": "memory_cap_or_vivado_killed", "detail": str(e)}
        finally:
            release(lock)
        out.write_text(json.dumps(rec, indent=1))
        print(design, arm, rec.get("status"), rec.get("stop_reason"), rec.get("wns_ns"), rec.get("vivado_runs"), flush=True)


def summary() -> None:
    import fpga_ablate as F
    recs = []
    for d in DESIGNS:
        r = root_of(d)
        recs.append({"arm": "control", "design": d, "seed": 1, "wns_ns": r["wns_ns"], "whs_ns": r.get("whs_ns"), "wns_gain_ns": 0.0, "vivado_runs": 1,
                     "fmax_mhz": round(1000 / (r["clock_ns"] - r["wns_ns"]), 1), "lut": r.get("lut"), "ff": r.get("ff")})
    for f in sorted(LIVE.glob("*__*.json")):
        j = json.loads(f.read_text())
        if j.get("status") == "ok":
            j.pop("search", None)
            recs.append(j)
    (RES / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    out = {}
    for arm, base in (("guided", "control"), ("shuffled216", "control"), ("shuffled217", "control"), ("guided", "shuffled216"), ("guided", "shuffled217")):
        for col in ("wns_gain_ns", "vivado_runs"):
            out[f"{arm}-{base}:{col}"] = F.paired_numeric(recs, arm, base, col)
    (RES / "paired.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(k, v["designs"], None if v["effect"] is None else round(v["effect"], 3), round(v["lo"], 3), round(v["hi"], 3), v["better"], v["worse"], v["p_sign"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "stage":
        stage()
    elif cmd == "run":
        run(sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None)
    elif cmd == "summary":
        summary()
    else:
        raise SystemExit(__doc__)
