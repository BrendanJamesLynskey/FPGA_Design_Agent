#!/usr/bin/env python3
"""Brief 178: candidate tournaments. Run several synthesis (or implementation) variants of one block, keep the best, record why
the others were dropped, and log each prediction against the routed outcome.

    python3 -m flow.tournament plan  <spec.yaml> --stage synth|impl [--menu a,b,c] [--k 2]        # print the candidates, run nothing
    python3 -m flow.tournament run   <spec.yaml> --stage synth [--menu ...] [--k 2] [--jobs 3]    # light synthesis class (decision 32)
    python3 -m flow.tournament run   <spec.yaml> --stage impl  --from <synth candidate id> [--menu ...] [--k 1]
    python3 -m flow.tournament score <tournament.json> [--routed <candidate id>=<wns>] ...        # join predictions with outcomes
    python3 -m flow.tournament strategies                                                        # probe AMD's own -strategy sets (Vivado)

Spec (YAML): name, part, top, sources (globs relative to the repo), clock_ns, generics (optional dict), fanout_nets (optional list of net
names for the max_fanout constraint variant).

Two stages, two resource classes (owner decision 32, 2026-11-22):
* ``synth``: small out-of-context synthesis-only runs, each declared at 2 GiB or less. The tournament takes ONE heavy slot (its text names
  the tournament and the declared total peak), then fans out up to 4 children under it. Each child runs under its own
  ``systemd-run --user --scope -p MemoryMax=2G`` and ``nice -n 15`` with one thread, and a child starts only while MemAvailable covers
  every running child's peak plus this one's plus 8 GiB. Nothing changes for how other jobs take slots.
* ``impl``: place and route candidates are normal heavy jobs: one at a time, each takes a slot under CLAUDE.md section 4.

Ranking (documented, tie-broken): see ``score_key``. Shadow data: every run writes ``tournament.json`` (all candidates, the rank, kept or
dropped and why) and appends the prediction to ``tournament_log.jsonl``; ``score`` adds the routed outcome later (brief 177's pattern).
Nothing here changes a gate; the agent may call it in shadow or opt-in mode only (docs/tournament.md).
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HANDOFF = Path(os.environ.get("TOURNAMENT_HANDOFF", "/home/brendan/Claude_sandbox/_handoff"))
WORK = ROOT / "build" / "tournament"
CHILD_PEAK_G = 2.0        # decision 32: the light class is for runs that declare 2 GiB or less
MAX_CHILDREN = 4          # decision 32: never more than 4 at once
RESERVE_G = 8.0           # free memory must cover every running child's peak plus this
STRATEGIES = Path(__file__).resolve().parent.parent / "results" / "178_tournament" / "vendor_strategies.json"

# ---- the menu (documented: docs/tournament.md). Each entry: id, family, the options, and where the knob is documented ----------------
#: synthesis candidates: ``args`` go to ``synth_design``. Every one is an AMD-documented option (UG901 / UG835 `synth_design -help`).
SYNTH_MENU: list[dict[str, Any]] = [
    {"id": "default", "family": "directive", "args": "-directive Default", "note": "the reference: what the flow does today"},
    {"id": "perf", "family": "directive", "args": "-directive PerformanceOptimized"},
    {"id": "area_high", "family": "directive", "args": "-directive AreaOptimized_high"},
    {"id": "altroute", "family": "directive", "args": "-directive AlternateRoutability"},
    {"id": "runtime", "family": "directive", "args": "-directive RuntimeOptimized"},
    {"id": "carry", "family": "directive", "args": "-directive FewerCarryChains"},
    {"id": "flat_full", "family": "hierarchy", "args": "-flatten_hierarchy full"},
    {"id": "flat_none", "family": "hierarchy", "args": "-flatten_hierarchy none"},
    {"id": "retime", "family": "retiming", "args": "-retiming"},
    {"id": "perf_retime", "family": "retiming", "args": "-directive PerformanceOptimized -retiming"},
    {"id": "fsm_onehot", "family": "fsm", "args": "-fsm_extraction one_hot"},
    {"id": "shreg5", "family": "shreg", "args": "-shreg_min_size 5"},
    {"id": "keep_eq", "family": "registers", "args": "-keep_equivalent_registers"},
    {"id": "no_share", "family": "sharing", "args": "-resource_sharing off"},
    {"id": "dsp0", "family": "dsp", "args": "-max_dsp 0", "note": "force logic instead of DSP: only useful where the block is DSP-bound"},
    {"id": "fanout50", "family": "constraint", "args": "-fanout_limit 50", "note": "global fanout limit; the net-specific max_fanout needs spec.fanout_nets"},
    {"id": "fanout_nets", "family": "constraint", "args": "", "needs": "fanout_nets", "note": "MAX_FANOUT on the spec's named nets"},
]
#: implementation candidates (opt / place / post-place phys_opt / route / post-route phys_opt directives). Names are `*_design -directive`
#: values; the AMD strategy equivalents are measured by `strategies` into results/178_tournament/vendor_strategies.json and added at run time.
IMPL_MENU: list[dict[str, Any]] = [
    {"id": "default", "family": "directive", "opt": "Default", "place": "Default", "route": "Default", "note": "the reference"},
    {"id": "explore", "family": "directive", "opt": "Explore", "place": "Explore", "phys": "Explore", "route": "Explore", "post": "Explore"},
    {"id": "extra_timing", "family": "directive", "opt": "Explore", "place": "ExtraTimingOpt", "phys": "AggressiveExplore", "route": "Explore",
     "post": "AggressiveExplore"},
    {"id": "extra_netdelay", "family": "directive", "opt": "Explore", "place": "ExtraNetDelay_high", "phys": "Explore", "route": "NoTimingRelaxation",
     "post": "Explore"},
    {"id": "aggressive", "family": "directive", "opt": "ExploreWithRemap", "place": "ExtraPostPlacementOpt", "phys": "AggressiveExplore",
     "route": "AggressiveExplore", "post": "AggressiveExplore"},
    {"id": "congestion", "family": "directive", "opt": "Default", "place": "AltSpreadLogic_high", "route": "AlternateCLBRouting"},
]


# ---- spec ---------------------------------------------------------------------------------------------------------------------------
def load_spec(path: str | Path) -> dict[str, Any]:
    s = yaml.safe_load(Path(path).read_text())
    for k in ("name", "part", "top", "sources", "clock_ns"):
        if k not in s:
            raise SystemExit(f"tournament: spec {path} lacks '{k}'")
    s["files"] = [str(p) for g in s["sources"] for p in (sorted(map(Path, glob.glob(str(ROOT / g)))) or [ROOT / g])]
    s["clock_ns"] = float(s["clock_ns"])
    return s


def synth_candidates(spec: dict[str, Any], menu: list[str] | None) -> list[dict[str, Any]]:
    """The candidates to run, in menu order; ``default`` is always first (it is the reference). Skips (with a reason) those whose need is missing."""
    out, skipped = [], []
    for m in SYNTH_MENU:
        if menu and m["id"] not in menu and m["id"] != "default":
            continue
        if m.get("needs") and not spec.get(m["needs"]):
            skipped.append({"id": m["id"], "reason": f"spec has no {m['needs']}"})
            continue
        out.append(dict(m))
    spec["_skipped"] = skipped
    return out


def impl_candidates(menu: list[str] | None) -> list[dict[str, Any]]:
    ms = [dict(m) for m in IMPL_MENU]
    if STRATEGIES.exists():                              # AMD's own -strategy sets, measured (strategies probe), not recalled
        for name, st in json.loads(STRATEGIES.read_text()).get("impl", {}).items():
            ms.append({"id": "amd:" + name, "family": "vendor_strategy", **st})
    return [m for m in ms if not menu or m["id"] in menu or m["id"] == "default"]


# ---- scoring ------------------------------------------------------------------------------------------------------------------------
def p_pass(wns: float | None, stage: str) -> float | None:
    """Brief 177's shadow predictor rule_v0 (an unfitted prior), so the tournament's early score and 177's are the same number."""
    from flow import predict
    return predict.rule_v0("post_synth" if stage == "synth" else "post_place", {"wns_ns": wns})[0]


def score_key(c: dict[str, Any]) -> tuple:
    """Sort key, best first. (1) failed candidates last; (2) WNS rounded DOWN to 0.05 ns buckets (smaller differences are inside the
    placement noise measured in docs/tournament.md), higher is better; (3) then fewer LUT+FF (area); (4) fewer logic levels;
    (5) menu order, so on a complete tie the default wins and nothing changes without evidence. WNS of None (unconstrained) ranks as a tie at +inf."""
    if c.get("status") != "ok":
        return (1, 0, 0, 0, 0, c.get("order", 0))
    w = c.get("wns_ns")
    bucket = float("-inf") if w is None else -int(w // 0.05)           # higher WNS -> smaller key
    return (0, bucket if w is not None else -10 ** 9, (c.get("lut") or 0) + (c.get("ff") or 0), c.get("levels") or 0, c.get("order", 0))


def rank(cands: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """Sets ``rank``, ``kept`` and ``dropped_because`` on every candidate. Keeps the top k."""
    ok = sorted(cands, key=score_key)
    best = next((c for c in ok if c.get("status") == "ok"), None)
    for i, c in enumerate(ok, 1):
        c["rank"] = i
        c["kept"] = c.get("status") == "ok" and i <= k
        if c["kept"]:
            c.pop("dropped_because", None)
        elif c.get("status") != "ok":
            c["dropped_because"] = f"run failed: {c.get('status')}"
        elif best is not None:
            dw = None if (c.get("wns_ns") is None or best.get("wns_ns") is None) else round(best["wns_ns"] - c["wns_ns"], 3)
            if dw is not None and dw >= 0.05:
                c["dropped_because"] = f"WNS {dw} ns behind rank 1 ({best['id']})"
            else:
                da = ((c.get("lut") or 0) + (c.get("ff") or 0)) - ((best.get("lut") or 0) + (best.get("ff") or 0))
                c["dropped_because"] = f"WNS within 0.05 ns of rank 1 ({best['id']}); tie broken on area (+{da} LUT+FF), then levels, then menu order"
    return ok


# ---- memory admission (decision 32) ------------------------------------------------------------------------------------------------
def mem_available_g() -> float:
    for ln in Path("/proc/meminfo").read_text().splitlines():
        if ln.startswith("MemAvailable:"):
            return int(ln.split()[1]) / 1024 / 1024
    return 0.0


def may_launch(running_peaks: list[float], peak: float, avail_g: float, children_max: int = MAX_CHILDREN) -> tuple[bool, str]:
    """True when a child of declared ``peak`` GiB may start: fewer than 4 running, and MemAvailable covers every running child's peak plus
    this one's plus 8 GiB. (Ignores that a child may not have reached its peak yet: the declared peaks are the conservative reading.)"""
    if peak > CHILD_PEAK_G:
        return False, f"declared peak {peak} G is above the light class limit {CHILD_PEAK_G} G"
    if len(running_peaks) >= children_max:
        return False, f"{children_max} children already running"
    need = sum(running_peaks) + peak + RESERVE_G
    if avail_g < need:
        return False, f"MemAvailable {avail_g:.1f} G < running {sum(running_peaks):.1f} + {peak:.1f} + {RESERVE_G:.0f} G reserve"
    return True, "ok"


# ---- Tcl ----------------------------------------------------------------------------------------------------------------------------
def _tcl(s: str) -> str:
    return "{" + s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}") + "}"


def synth_tcl(spec: dict[str, Any], cand: dict[str, Any], wd: Path) -> str:
    gen = " ".join(f"-generic {k}={v}" for k, v in (spec.get("generics") or {}).items())
    reads = "\n".join(f"read_{'vhdl' if f.endswith(('.vhd', '.vhdl')) else 'verilog -sv'} {_tcl(f)}" for f in spec["files"])
    xdc = [f"create_clock -period {spec['clock_ns']} -name clk [get_ports clk]"]
    if cand["id"] == "fanout_nets":
        xdc += [f"set_property MAX_FANOUT 50 [get_nets {_tcl(n)}]" for n in spec["fanout_nets"]]
    return f"""set_param general.maxThreads 1
set_param synth.maxThreads 1
file mkdir {_tcl(str(wd))}
set t0 [clock seconds]
create_project -in_memory -part {spec['part']}
{reads}
set f [open {_tcl(str(wd / 'clock.xdc'))} w]
puts $f {_tcl(chr(10).join(xdc))}
close $f
read_xdc -mode out_of_context {_tcl(str(wd / 'clock.xdc'))}
synth_design -top {spec['top']} -part {spec['part']} -mode out_of_context {cand['args']} {gen}
report_utilization -file {_tcl(str(wd / 'utilization.rpt'))}
report_timing_summary -max_paths 5 -file {_tcl(str(wd / 'timing_summary.rpt'))}
report_timing -max_paths 1 -path_type full -file {_tcl(str(wd / 'worst_path.rpt'))}
write_checkpoint -force {_tcl(str(wd / 'post_synth.dcp'))}
set f [open {_tcl(str(wd / 'done.txt'))} w]; puts $f [expr {{[clock seconds] - $t0}}]; close $f
"""


def impl_tcl(src_dcp: Path, cand: dict[str, Any], wd: Path) -> str:
    lines = [f"opt_design -directive {cand['opt']}" if cand.get("opt", "Default") != "Default" else "opt_design",
             f"place_design -directive {cand['place']}" if cand.get("place", "Default") != "Default" else "place_design"]
    if cand.get("phys"):
        lines.append(f"phys_opt_design -directive {cand['phys']}")
    lines.append(f"route_design -directive {cand['route']}" if cand.get("route", "Default") != "Default" else "route_design")
    if cand.get("post"):
        lines.append(f"phys_opt_design -directive {cand['post']}")
    body = "\n".join(lines)
    return f"""set_param general.maxThreads 1
file mkdir {_tcl(str(wd))}
set t0 [clock seconds]
open_checkpoint {_tcl(str(src_dcp))}
{body}
report_utilization -file {_tcl(str(wd / 'utilization.rpt'))}
report_timing_summary -max_paths 5 -file {_tcl(str(wd / 'timing_summary.rpt'))}
report_timing -max_paths 1 -path_type full -file {_tcl(str(wd / 'worst_path.rpt'))}
set f [open {_tcl(str(wd / 'done.txt'))} w]; puts $f [expr {{[clock seconds] - $t0}}]; close $f
"""


# ---- parsing ------------------------------------------------------------------------------------------------------------------------
def _row(txt: str, name: str):
    m = re.search(rf"^\|\s*{re.escape(name)}\*?\s*\|\s*(\d+)\s*\|", txt, re.M)
    return int(m.group(1)) if m else None


def parse(wd: Path) -> dict[str, Any]:
    """LUT, FF, DSP, BRAM, WNS/TNS/WHS and the worst path's logic levels from one candidate's reports."""
    if (wd / "error.txt").exists():
        return {"status": "error: " + (wd / "error.txt").read_text().strip().splitlines()[0][:200]}
    if not (wd / "done.txt").exists():
        return {"status": "not run"}
    u, t = (wd / "utilization.rpt").read_text(), (wd / "timing_summary.rpt").read_text()
    r: dict[str, Any] = {"status": "ok", "runtime_s": int((wd / "done.txt").read_text().split()[0])}
    for k, names in (("lut", ("Slice LUTs", "CLB LUTs")), ("ff", ("Slice Registers", "CLB Registers")), ("dsp", ("DSPs",)),
                     ("bram_tiles", ("Block RAM Tile",))):
        r[k] = next((v for v in (_row(u, n) for n in names) if v is not None), None)
    hm = re.search(r"^\s*(WNS\(ns\)\s[^\n]*)\n\s*-+[^\n]*\n\s*([^\n]+)", t, re.M)
    cols = dict(zip(re.split(r"\s{2,}", hm.group(1).strip()), hm.group(2).split())) if hm else {}
    num = lambda k: float(cols[k]) if re.fullmatch(r"-?\d+\.\d+", cols.get(k, "")) else None
    r["wns_ns"], r["tns_ns"], r["whs_ns"] = num("WNS(ns)"), num("TNS(ns)"), num("WHS(ns)")
    wp = wd / "worst_path.rpt"
    m = re.search(r"Logic Levels:\s+(\d+)", wp.read_text()) if wp.exists() else None
    r["levels"] = int(m.group(1)) if m else None
    return r


# ---- running ------------------------------------------------------------------------------------------------------------------------
def vivado() -> str:
    return os.environ.get("VIVADO") or subprocess.run([sys.executable, str(ROOT / "flow" / "version_pin.py"), "--vivado"],
                                                      capture_output=True, text=True, check=True).stdout.strip()


def take_slot(text: str, wait_s: int = 6 * 3600) -> Path:
    """Poll take_heavy_slot.sh until a slot is ours. Returns the lock file (release with release_slot)."""
    t0 = time.time()
    while True:
        p = subprocess.run([str(HANDOFF / "take_heavy_slot.sh"), text], capture_output=True, text=True)
        if p.returncode == 0:
            return Path(p.stdout.strip().splitlines()[-1])
        if time.time() - t0 > wait_s:
            raise SystemExit("tournament: no heavy slot within the wait limit")
        time.sleep(120)


def release_slot(lock: Path, prefix: str) -> None:
    try:
        if lock.read_text().startswith(prefix + ":"):          # owner-checked release: only a lock whose text is ours
            lock.unlink()
    except FileNotFoundError:
        pass


def _child_cmd(tcl: Path, log: Path, peak_g: float) -> list[str]:
    return ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={int(peak_g)}G", "nice", "-n", "15",
            vivado(), "-mode", "batch", "-nojournal", "-log", str(log), "-source", str(tcl)]


def run_children(jobs: list[dict[str, Any]], peak_g: float, max_children: int = MAX_CHILDREN, poll_s: float = 5.0,
                 launch=subprocess.Popen, avail=mem_available_g) -> None:
    """Fan ``jobs`` (each {tcl, log}) out inside the slot we hold; the admission rule is ``may_launch`` before every launch."""
    pending, running, t_wait = list(jobs), [], time.time()
    while pending or running:
        if not running and time.time() - t_wait > 3600:
            raise SystemExit("tournament: memory never allowed a child to start within an hour")
        running = [(p, j) for p, j in running if p.poll() is None]
        while pending:
            ok, why = may_launch([peak_g] * len(running), peak_g, avail(), max_children)
            if not ok:
                break
            t_wait = time.time()
            j = pending.pop(0)
            j["started"] = time.time()
            running.append((launch(_child_cmd(j["tcl"], j["log"], peak_g), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), j))
        time.sleep(poll_s)


def run(spec: dict[str, Any], stage: str, menu: list[str] | None, k: int, jobs: int, src: str | None = None, take: bool = True,
        out: Path | None = None) -> dict[str, Any]:
    out = out or WORK / spec["name"] / stage
    out.mkdir(parents=True, exist_ok=True)
    cands = synth_candidates(spec, menu) if stage == "synth" else impl_candidates(menu)
    for i, c in enumerate(cands):
        c["order"] = i
        c["wd"] = str(out / c["id"].replace(":", "_"))
    prefix = "178"
    t_wall = time.time()
    if stage == "synth":
        peak = CHILD_PEAK_G
        n = max(1, min(jobs, MAX_CHILDREN))
        text = (f"178: tournament {spec['name']} synth, {len(cands)} candidates, up to {n} at once under this slot, total peak "
                f"{peak * n:g}G, {datetime.datetime.now():%H:%M}, expected end {(datetime.datetime.now() + datetime.timedelta(minutes=20)):%H:%M}")
        lock = take_slot(text) if take else None
        try:
            js = []
            for c in cands:
                wd = Path(c["wd"])
                wd.mkdir(parents=True, exist_ok=True)
                (wd / "run.tcl").write_text(synth_tcl(spec, c, wd))
                js.append({"tcl": wd / "run.tcl", "log": wd / "vivado.log"})
            run_children(js, peak, n)
        finally:
            if lock:
                release_slot(lock, prefix)
    else:
        if not src:
            raise SystemExit("tournament: --stage impl needs --from <synth candidate id> (its post_synth.dcp)")
        dcp = WORK / spec["name"] / "synth" / src / "post_synth.dcp"
        for c in cands:                      # one at a time, each its own slot (CLAUDE.md section 4)
            wd = Path(c["wd"])
            wd.mkdir(parents=True, exist_ok=True)
            (wd / "run.tcl").write_text(impl_tcl(dcp, c, wd))
            text = (f"178: tournament {spec['name']} impl {c['id']} from {src}, {datetime.datetime.now():%H:%M}, expected end "
                    f"{(datetime.datetime.now() + datetime.timedelta(minutes=15)):%H:%M}, peak {os.environ.get('TOURNAMENT_IMPL_PEAK', '4')}G")
            lock = take_slot(text) if take else None
            try:
                run_children([{"tcl": wd / "run.tcl", "log": wd / "vivado.log"}], float(os.environ.get("TOURNAMENT_IMPL_PEAK", "4")), 1,
                             avail=lambda: 99.0)
            finally:
                if lock:
                    release_slot(lock, prefix)
    for c in cands:
        c.update(parse(Path(c["wd"])))
        c["p_pass"] = p_pass(c.get("wns_ns"), stage) if c.get("status") == "ok" else None
    ranked = rank(cands, k)
    ref = next((c for c in ranked if c["id"] == "default"), None)
    rec = {"schema": "fda-tournament/1", "date": datetime.date.today().isoformat(), "design": spec["name"], "stage": stage, "part": spec["part"],
           "clock_ns": spec["clock_ns"], "k": k, "vivado": Path(vivado()).parts[-3] if len(Path(vivado()).parts) > 3 else vivado(),
           "wall_s": round(time.time() - t_wall), "cpu_s": sum(c.get("runtime_s") or 0 for c in cands), "skipped": spec.get("_skipped", []),
           "score": "flow/tournament.py score_key: WNS in 0.05 ns buckets, then LUT+FF, then logic levels, then menu order",
           "candidates": ranked, "winner": ranked[0]["id"] if ranked and ranked[0].get("kept") else None,
           "default_rank": ref["rank"] if ref else None}
    (out / "tournament.json").write_text(json.dumps(rec, indent=1, default=str))
    with (WORK / "tournament_log.jsonl").open("a") as f:           # shadow data for 177: prediction now, outcome joined later by `score`
        for c in ranked:
            f.write(json.dumps({"design": spec["name"], "stage": stage, "id": c["id"], "rank": c["rank"], "p_pass": c.get("p_pass"),
                                "wns_ns": c.get("wns_ns"), "kept": c["kept"], "routed_wns_ns": None}) + "\n")
    return rec


def score(path: str, routed: dict[str, float]) -> dict[str, Any]:
    """Join the tournament's early ranking with routed WNS values (``id`` -> WNS). Spearman rho and whether rank 1 was best routed."""
    import numpy as np
    r = json.loads(Path(path).read_text())
    rows = [(c["id"], c["wns_ns"], routed[c["id"]]) for c in r["candidates"] if c["id"] in routed and c.get("wns_ns") is not None]
    out: dict[str, Any] = {"design": r["design"], "n": len(rows)}
    if len(rows) >= 3:
        a, b = (np.array([x[i] for x in rows]) for i in (1, 2))
        ra, rb = a.argsort().argsort(), b.argsort().argsort()
        out["spearman"] = float(np.corrcoef(ra, rb)[0, 1]) if ra.std() and rb.std() else None
    if rows:
        out["early_best"] = max(rows, key=lambda x: x[1])[0]
        out["routed_best"] = max(rows, key=lambda x: x[2])[0]
        out["early_best_is_routed_best"] = out["early_best"] == out["routed_best"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flow.tournament", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("spec")
        p.add_argument("--stage", choices=("synth", "impl"), required=True)
        p.add_argument("--menu", help="comma list of candidate ids (default is always included)")
        p.add_argument("--k", type=int, default=2)
        p.add_argument("--jobs", type=int, default=3, help="children at once under the one slot (max 4)")
        p.add_argument("--from", dest="src", help="impl: the synthesis candidate whose checkpoint to implement")
        p.add_argument("--no-slot", action="store_true", help="the caller already holds a slot (tests, scripted sweeps)")
    sc = sub.add_parser("score")
    sc.add_argument("record")
    sc.add_argument("--routed", action="append", default=[], metavar="ID=WNS")
    a = ap.parse_args(argv)
    if a.cmd == "score":
        print(json.dumps(score(a.record, {k: float(v) for k, v in (x.split("=") for x in a.routed)}), indent=1))
        return 0
    spec = load_spec(a.spec)
    menu = a.menu.split(",") if a.menu else None
    if a.cmd == "plan":
        cs = synth_candidates(spec, menu) if a.stage == "synth" else impl_candidates(menu)
        print(json.dumps({"stage": a.stage, "candidates": cs, "skipped": spec.get("_skipped", [])}, indent=1))
        return 0
    rec = run(spec, a.stage, menu, a.k, a.jobs, a.src, take=not a.no_slot)
    print(json.dumps({k: rec[k] for k in ("design", "stage", "winner", "default_rank", "wall_s", "cpu_s")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
