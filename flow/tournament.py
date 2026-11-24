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
    if spec.get("xdc"):                                  # the build file's own constraints (arith ooc.xdc) replace the generated clock
        xdc = [Path(ROOT / x).read_text() for x in spec["xdc"]]
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


def synth_peak_g(spec: dict[str, Any]) -> float:
    """Declared peak of one synthesis child. Measured 2026-11-23 (brief 178b): the 2 GiB cap held for the 7-series adder but killed every UltraScale+ (K26)
    child during cross-boundary optimisation (Vivado reported ~3.07 GB), which is why four of the five 178 tournaments recorded no result. A spec may set
    ``synth_peak_g``; otherwise 2 GiB (light class) for xc7 parts and 4 GiB for the rest. Above 2 GiB the run is not light class: one child at a time."""
    if spec.get("synth_peak_g"):
        return float(spec["synth_peak_g"])
    return CHILD_PEAK_G if str(spec.get("part", "")).startswith("xc7") else 4.0


def _child_cmd(tcl: Path, log: Path, peak_g: float) -> list[str]:
    return ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={int(peak_g)}G", "nice", "-n", "15",
            vivado(), "-mode", "batch", "-nojournal", "-log", str(log), "-source", str(tcl)]


FALLBACK_AFTER_S = 120.0   # idle this long with the gate refusing: run one child alone (the slot we hold already admits one Vivado)
FALLBACK_FLOOR_G = 1.0     # ... provided MemAvailable still covers the child's peak plus this much


def run_children(jobs: list[dict[str, Any]], peak_g: float, max_children: int = MAX_CHILDREN, poll_s: float = 5.0,
                 launch=subprocess.Popen, avail=mem_available_g, fallback_after_s: float = FALLBACK_AFTER_S, log=print) -> None:
    """Fan ``jobs`` (each {tcl, log}) out inside the slot we hold; the admission rule is ``may_launch`` before every launch.

    Fallback (brief 178b): when nothing is running and the gate has refused for ``fallback_after_s``, start ONE child anyway, one at a time, as long as
    MemAvailable covers its peak plus 1 GiB. The held slot is the normal one-Vivado admission, so a single child inside it is within the rules; the
    8 GiB reserve is only what lets several children share the slot. If even that is not free the wait goes on (an hour, then an error)."""
    pending, running, t_wait, t_idle = list(jobs), [], time.time(), time.time()
    while pending or running:
        if not running and time.time() - t_wait > 3600:
            raise SystemExit("tournament: memory never allowed a child to start within an hour")
        running = [(p, j) for p, j in running if p.poll() is None]
        while pending:
            if max_children == 1:
                # one child at a time (K26 synthesis, every place-and-route run): the slot we hold admits it, so only the child's own peak
                # plus 1 GiB must be free. Brief 178c: the old code asked the light-class gate (peak <= 2 G, plus 8 G reserve) and waited for the fallback.
                ok = not running and avail() >= peak_g + FALLBACK_FLOOR_G
                if not ok:
                    break
            else:
                ok, why = may_launch([peak_g] * len(running), peak_g, avail(), max_children)
            if not ok and not running and time.time() - t_idle >= fallback_after_s and avail() >= peak_g + FALLBACK_FLOOR_G:
                ok = True
                log(f"tournament: gate refused ({why}); running one child alone inside the slot (MemAvailable {avail():.1f} G)")
            if not ok:
                break
            t_wait = t_idle = time.time()
            j = pending.pop(0)
            j["started"] = time.time()
            running.append((launch(_child_cmd(j["tcl"], j["log"], peak_g), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), j))
        if running:
            t_idle = time.time()
        time.sleep(poll_s)


def run(spec: dict[str, Any], stage: str, menu: list[str] | None, k: int, jobs: int, src: str | None = None, take: bool = True,
        out: Path | None = None, tag: str = "") -> dict[str, Any]:
    out = out or WORK / spec["name"] / (stage + (("_" + tag) if tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    cands = synth_candidates(spec, menu) if stage == "synth" else impl_candidates(menu)
    for i, c in enumerate(cands):
        c["order"] = i
        c["wd"] = str(out / c["id"].replace(":", "_"))
    prefix = "178"
    t_wall = time.time()
    if stage == "synth":
        peak = synth_peak_g(spec)
        n = max(1, min(jobs, MAX_CHILDREN)) if peak <= CHILD_PEAK_G else 1
        text = (f"178: tournament {spec['name']} synth, {len(cands)} candidates, up to {n} at once under this slot, total peak "
                f"{peak * n:g}G, {datetime.datetime.now():%H:%M}, expected end "
                f"{(datetime.datetime.now() + datetime.timedelta(minutes=max(20, int(2.5 * len(cands) / n)))):%H:%M}")
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
            raise SystemExit("tournament: --stage impl needs --from <synth candidate id[,id...]> (their post_synth.dcp)")
        srcs = src.split(",")
        cands = [dict(c, id=f"{sid}/{c['id']}", synth=sid, order=i * 100 + c["order"], wd=str(out / (sid + "_" + c["id"].replace(":", "_"))))
                 for i, sid in enumerate(srcs) for c in cands]
        # place and route candidates stay under the normal slot rule (CLAUDE.md section 4, decision 32): ONE slot, one Vivado at a time, never fanned out
        text = (f"178: tournament {spec['name']} impl, {len(cands)} place-and-route runs one after another, {datetime.datetime.now():%H:%M}, expected end "
                f"{(datetime.datetime.now() + datetime.timedelta(minutes=5 * len(cands))):%H:%M}, peak {os.environ.get('TOURNAMENT_IMPL_PEAK', '4')}G")
        lock = take_slot(text) if take else None
        try:
            for c in cands:
                wd = Path(c["wd"])
                wd.mkdir(parents=True, exist_ok=True)
                (wd / "run.tcl").write_text(impl_tcl(WORK / spec["name"] / "synth" / c["synth"] / "post_synth.dcp", c, wd))
                run_children([{"tcl": wd / "run.tcl", "log": wd / "vivado.log"}], float(os.environ.get("TOURNAMENT_IMPL_PEAK", "4")), 1)
        finally:
            if lock:
                release_slot(lock, prefix)
    for c in cands:
        c.update(parse(Path(c["wd"])))
        c["p_pass"] = p_pass(c.get("wns_ns"), stage) if c.get("status") == "ok" else None
    if not any(c.get("status") == "ok" for c in cands):    # brief 178b: a tournament in which nothing ran is a failure, never a "null winner" record
        (out / "tournament_failed.txt").write_text("no candidate completed: " + "; ".join(sorted({str(c.get("status")) for c in cands})) + "\n")
        raise SystemExit(f"tournament: no candidate completed for {spec['name']} {stage} (see {out}/*/vivado.log)")
    ranked = rank(cands, k)
    ref = next((c for c in ranked if c["id"] in ("default", "default/default")), None)   # impl ids are "<synth>/<impl>" (null before brief 178c)
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


PROBE_TCL = '''set_param general.maxThreads 1
create_project -force probe {wd} -part xc7a100tcsg324-1
set out [open {res} w]
set impl [get_runs impl_1]
set synth [get_runs synth_1]
puts $out "FLOWS [get_property FLOW $synth] | [get_property FLOW $impl]"
foreach {{kind run}} [list synth $synth impl $impl] {{
    foreach s [list_property_value STRATEGY $run] {{
        if {{[catch {{
            if {{$kind eq "synth"}} {{ set r [create_run probe_s_[regsub -all {{[^A-Za-z0-9]}} $s _] -flow [get_property FLOW $synth] -strategy $s] }} else {{
                set r [create_run probe_i_[regsub -all {{[^A-Za-z0-9]}} $s _] -flow [get_property FLOW $impl] -parent_run synth_1 -strategy $s] }}
            foreach p [list_property $r -regexp {{^STEPS\\..*(ARGS|IS_ENABLED)}}] {{ puts $out "$kind\t$s\t$p\t[get_property $p $r]" }}
            foreach st {{OPT_DESIGN PLACE_DESIGN PHYS_OPT_DESIGN ROUTE_DESIGN POST_ROUTE_PHYS_OPT_DESIGN}} {{
                if {{[catch {{set d [get_property STEPS.$st.ARGS.DIRECTIVE $r]}}]}} {{ continue }}
                puts $out "$kind\t$s\tSTEPS.$st.ARGS.DIRECTIVE\t$d"
            }}
        }} e]}} {{ puts $out "$kind\t$s\tERROR\t$e" }}
    }}
}}
close $out
'''


def probe_strategies() -> Path:
    """Measure AMD's own -strategy sets (the vendor convention) from Vivado itself: every strategy's step arguments, written to
    results/178_tournament/strategies_raw.tsv and condensed to vendor_strategies.json (impl directives, used as menu entries)."""
    wd = WORK / "strategy_probe"
    wd.mkdir(parents=True, exist_ok=True)
    raw = ROOT / "results" / "178_tournament" / "strategies_raw.tsv"
    tcl = wd / "probe.tcl"
    tcl.write_text(PROBE_TCL.format(wd=_tcl(str(wd / "proj")), res=_tcl(str(raw))))
    lock = take_slot(f"178: strategy probe (Vivado, a few seconds, no implementation), {datetime.datetime.now():%H:%M}, expected end "
                     f"{(datetime.datetime.now() + datetime.timedelta(minutes=5)):%H:%M}, peak 2G")
    try:
        subprocess.run(_child_cmd(tcl, wd / "vivado.log", 2.0), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        release_slot(lock, "178")
    cond: dict[str, Any] = {"impl": {}, "synth": {}}
    for ln in raw.read_text().splitlines() if raw.exists() else []:
        f = ln.split("\t")
        if len(f) != 4:
            continue
        kind, strat, prop, val = f
        e = cond[kind].setdefault(strat, {})
        m = re.match(r"STEPS\.(\w+)\.(ARGS\.DIRECTIVE|IS_ENABLED)$", prop)
        if kind == "impl" and m:
            step, what = m.groups()
            key = {"OPT_DESIGN": "opt", "PLACE_DESIGN": "place", "PHYS_OPT_DESIGN": "phys", "ROUTE_DESIGN": "route", "POST_ROUTE_PHYS_OPT_DESIGN": "post"}.get(step)
            if key and what == "ARGS.DIRECTIVE":
                e[key] = val
            elif key in ("phys", "post") and what == "IS_ENABLED" and val in ("0", "false"):
                e[key + "_off"] = True
        elif kind == "synth":
            e[prop] = val
    for st in cond["impl"].values():                       # a disabled phys_opt step has no directive in the candidate
        for key in ("phys", "post"):
            if st.pop(key + "_off", False):
                st.pop(key, None)
    STRATEGIES.write_text(json.dumps(cond, indent=1, sort_keys=True))
    return STRATEGIES


# ---- up-front triage (owner 2026-11-22: decide whether a design is difficult enough to warrant a tournament) -----------------------------
#: thresholds, documented in docs/tournament.md; set from the evaluation (results/178_tournament/triage_eval.json), changed only with a dated note
TRIAGE = {"pre_hard": 1.00, "pre_marginal": 0.85,      # target frequency / typical routed Fmax of the nearest rows
          "syn_easy_wns": 0.50, "syn_hard_wns": -0.30,    # estimated post-synthesis WNS (ns): >= easy_wns easy, < hard_wns hard, between marginal
          "min_rows": 3}


def triage_pre(spec: dict[str, Any], dataset: Path | None = None) -> dict[str, Any]:
    """Cheapest signal first, before any synthesis: the target clock against the routed Fmax of the nearest rows of the 177 dataset (same function
    and part; Fmax = 1000 / (clock - routed WNS)). No rows, or fewer than ``min_rows``: ``unknown`` (the caller then runs one default synthesis)."""
    import csv
    import statistics
    ds = dataset or ROOT / "results" / "177_qor" / "dataset.csv"
    fn = spec.get("function") or str(spec.get("from", "")).split("/")[1:2] and str(spec.get("from")).split("arith/")[-1].split("/")[0]
    key = "k26" if "xck26" in spec["part"] else "a7" if "xc7a100" in spec["part"] else None
    fm = []
    if ds.exists() and fn and key:
        for r in csv.DictReader(ds.open()):
            if r["source"] == "arith" and r["row_id"].startswith(fn + "/") and f"/{key}/" in r["row_id"] and r["rt_wns"]:
                fm.append(1000.0 / (float(r["clock_ns"]) - float(r["rt_wns"])))
    out: dict[str, Any] = {"signal": "pre_synthesis", "function": fn, "n_rows": len(fm)}
    if len(fm) < TRIAGE["min_rows"]:
        return {**out, "class": "unknown", "reason": f"only {len(fm)} nearest rows in the 177 dataset"}
    typ = statistics.median(fm)
    ratio = (1000.0 / spec["clock_ns"]) / typ
    cls = "hard" if ratio >= TRIAGE["pre_hard"] else "marginal" if ratio >= TRIAGE["pre_marginal"] else "easy"
    return {**out, "class": cls, "target_mhz": round(1000.0 / spec["clock_ns"], 1), "typical_fmax_mhz": round(typ, 1), "ratio": round(ratio, 3),
            "reason": f"target is {ratio:.2f} x the median routed Fmax of {len(fm)} nearest {fn}/{key} rows"}


def triage_post(wns: float | None) -> dict[str, Any]:
    """After ONE default synthesis: the estimated post-synthesis WNS (and brief 177's p_pass, which is a step function of it)."""
    if wns is None:
        return {"signal": "post_synthesis", "class": "unknown", "reason": "no constrained path"}
    cls = "easy" if wns >= TRIAGE["syn_easy_wns"] else "hard" if wns < TRIAGE["syn_hard_wns"] else "marginal"
    return {"signal": "post_synthesis", "class": cls, "wns_ns": wns, "p_pass": p_pass(wns, "synth"),
            "reason": f"default synthesis estimates WNS {wns} ns (easy >= {TRIAGE['syn_easy_wns']}, hard < {TRIAGE['syn_hard_wns']})"}


def triage(spec: dict[str, Any], default_wns: float | None = None, have_default: bool = False) -> dict[str, Any]:
    """The decision: ``easy`` = default flow only, ``marginal`` = synthesis tournament, ``hard`` = synthesis plus place-and-route tournament.
    The post-synthesis signal overrides the pre-synthesis one when the default synthesis has run; both are recorded with reasons."""
    pre = triage_pre(spec)
    post = triage_post(default_wns) if have_default else None
    final = (post if post and post["class"] != "unknown" else pre)["class"]
    return {"decision": final, "pre": pre, "post": post,
            "next": {"easy": "default flow only", "marginal": "synthesis tournament", "hard": "synthesis + place-and-route tournament",
                     "unknown": "run one default synthesis, then triage again"}[final]}


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
        p.add_argument("--tag", default="", help="impl: output directory suffix (several impl runs of one design)")
        p.add_argument("--no-slot", action="store_true", help="the caller already holds a slot (tests, scripted sweeps)")
    sub.add_parser("strategies", help="probe AMD's own -strategy sets in Vivado")
    tr = sub.add_parser("triage", help="classify a design easy / marginal / hard before any candidate runs")
    tr.add_argument("spec")
    tr.add_argument("--default-wns", type=float, help="estimated WNS of one default synthesis, if it has run")
    sc = sub.add_parser("score")
    sc.add_argument("record")
    sc.add_argument("--routed", action="append", default=[], metavar="ID=WNS")
    a = ap.parse_args(argv)
    if a.cmd == "score":
        print(json.dumps(score(a.record, {k: float(v) for k, v in (x.split("=") for x in a.routed)}), indent=1))
        return 0
    if a.cmd == "strategies":
        print(probe_strategies())
        return 0
    spec = load_spec(a.spec)
    if a.cmd == "triage":
        print(json.dumps(triage(spec, a.default_wns, a.default_wns is not None), indent=1))
        return 0
    menu = a.menu.split(",") if a.menu else None
    if a.cmd == "plan":
        cs = synth_candidates(spec, menu) if a.stage == "synth" else impl_candidates(menu)
        print(json.dumps({"stage": a.stage, "candidates": cs, "skipped": spec.get("_skipped", [])}, indent=1))
        return 0
    rec = run(spec, a.stage, menu, a.k, a.jobs, a.src, take=not a.no_slot, tag=a.tag)
    print(json.dumps({k: rec[k] for k in ("design", "stage", "winner", "default_rank", "wall_s", "cpu_s")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
