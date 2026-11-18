#!/usr/bin/env python3
"""Yosys + ABC against Vivado synthesis, post-route, out of context, on the same RTL (brief 101, part 1).

    python3 -m flow.oss_compare.run --part xck26-sfvc784-2LV-c [--blocks crc64_rx ...] [--arms ys_abc9 ...] [--perturb]
    python3 -m flow.oss_compare.run --table          # no tools: rebuild results/b101/summary.{json,md} from the records

Every block is wrapped (``rtl/wrap_<block>.sv``: an input register, the block, its own or an added output register, so each
path is register to register and the latency is 2 clocks in every arm). Every arm is then placed and routed by Vivado with
the same constraint (one clock on port ``clk``) and the same default ``opt_design``/``place_design``/``route_design``:

* ``viv_default``      ``synth_design`` defaults
* ``viv_perf``         ``-directive PerformanceOptimized``
* ``viv_perf_retime``  ``-directive PerformanceOptimized -retiming``
* ``ys_abc9`` / ``ys_abc9_dff`` / ``ys_abc_d``   flow/oss_synth.py scripts, EDIF read by Vivado (``read_edif``)

The clock search is the house pulse-width-aware one (designs/b87_ml_trading/ooc, brief 89): an arm closes when setup, hold
and pulse width are all met; the next period is ``period - min(WNS, 2 * WPWS)`` rounded up to 0.05 ns; an arm is never tried
faster than a period that failed. All the numbers are Vivado's (utilisation and timing reports of the placed and routed
design); Yosys's own cell counts are in ``synth.json`` and are not used for any comparison. Vivado has no user placement
seed; ``--perturb`` re-runs each closed arm at +0.01 ns and +0.02 ns, which changes the placer's cost function, and the
spread of the achievable period over the three runs is the seed variation reported.

Results: results/b101/<part>/<block>__<arm>.json; reports under results/b101/<part>/reports/. Builds: build/b101/.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import oss_synth  # noqa: E402
from flow.ipchar import tcl_list, vivado  # noqa: E402

HERE = Path(__file__).resolve().parent
RTL = HERE / "rtl"
B96 = ROOT / "designs" / "b96_kr260_10g" / "rtl"
B89 = ROOT / "designs" / "b89_lutnet_gen" / "rtl" / "gen"
TCL = HERE / "ooc.tcl"
PARTS = {"xck26-sfvc784-2LV-c": "k26", "xc7a100tcsg324-1": "a7"}
LATENCY_CLOCKS = 2          # input register + block (or block + output register), in every block

BLOCKS = {
    "crc64_rx": [B96 / "b96_pkg.sv", RTL / "crc64_rx.sv", RTL / "wrap_crc64_rx.sv"],
    "pcs_tx": [B96 / "b96_pkg.sv", B96 / "pcs_tx.sv", RTL / "wrap_pcs_tx.sv"],
    "lg_small_comb": [B89 / "lg_small_comb.sv", RTL / "wrap_lg_small_comb.sv"],
    "adder_tree8": [RTL / "adder_tree8.sv", RTL / "wrap_adder_tree8.sv"],
}
ARMS = {
    "viv_default": "rtl:Default",
    "viv_perf": "rtl:PerformanceOptimized",
    "viv_perf_retime": "rtl:PerformanceOptimized:retime",
    "ys_abc9": "edif", "ys_abc9_dff": "edif", "ys_abc_d": "edif",
}
YS_SCRIPT = {"ys_abc9": "abc9", "ys_abc9_dff": "abc9_dff", "ys_abc_d": "abc_d"}
TOP = "ooc_wrap"


def _row(txt: str, *labels: str):
    for label in labels:
        m = re.search(rf"^\|\s*{re.escape(label)}\*?\s*\|\s*([\d.]+)", txt, re.M)
        if m:
            return float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    return None


def parse(wd: Path, clock_ns: float) -> dict:
    """The Vivado numbers of one pass directory (a failed or missing pass is a status, never a guess)."""
    if (wd / "error.txt").exists():
        return {"status": "error: " + (wd / "error.txt").read_text().strip().splitlines()[0][:300], "clock_ns": clock_ns}
    if not (wd / "done.txt").exists():
        return {"status": "not run", "clock_ns": clock_ns}
    u = (wd / "utilization.rpt").read_text()
    t = (wd / "timing_summary.rpt").read_text()
    w = (wd / "timing_worst.rpt").read_text()
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)"
                  r"\s+\d+\s+\d+\s+(-?\d+\.\d+)", t, re.S)
    lv = re.search(r"Logic Levels:\s+(\d+)", w)
    dd = re.search(r"Data Path Delay:\s+(-?\d+\.\d+)ns", w)
    r = {"status": "ok", "clock_ns": clock_ns,
         "lut": _row(u, "CLB LUTs", "Slice LUTs"), "ff": _row(u, "CLB Registers", "Slice Registers"),
         "carry": _row(u, "CARRY8", "CARRY4"), "lut_levels": int(lv.group(1)) if lv else None,
         "data_path_ns": float(dd.group(1)) if dd else None,
         "wns_ns": float(m.group(1)) if m else None, "whs_ns": float(m.group(3)) if m else None,
         "wpws_ns": float(m.group(5)) if m else None,
         "build_seconds": int((wd / "done.txt").read_text().strip())}
    r["closed"] = None not in (r["wns_ns"], r["whs_ns"], r["wpws_ns"]) and min(r["wns_ns"], r["whs_ns"], r["wpws_ns"]) >= 0
    return r


def achievable(r: dict) -> float:
    return r["clock_ns"] - min(r["wns_ns"], 2 * (r["wpws_ns"] or 0.0))


def _ys_version() -> str:
    from flow.checks.elab import version
    return version()


def _src_hash(block: str) -> str:
    import hashlib
    return hashlib.sha256(b"".join(Path(s).read_bytes() for s in BLOCKS[block])).hexdigest()


def yosys_edif(block: str, part: str, arm: str) -> dict:
    out = ROOT / "build" / "b101" / "yosys" / PARTS[part] / f"{block}__{arm}"
    f = out / "synth.json"
    if f.exists():      # reused only while the sources, script and Yosys are the ones it was made from
        rec = json.loads(f.read_text())
        if rec.get("sources_sha256") == _src_hash(block) and rec.get("script") == YS_SCRIPT[arm] and rec.get("yosys") == _ys_version():
            return rec
    rec = oss_synth.synth(TOP, [str(s) for s in BLOCKS[block]], oss_synth.family_of_part(part), YS_SCRIPT[arm], out)
    rec["sources_sha256"] = _src_hash(block)
    (out / "synth.json").write_text(json.dumps(rec, indent=1))
    return rec


def run_pass(part: str, jobs: list[tuple[str, str, float]], tag: str) -> tuple[dict, str]:
    """jobs: (block, arm, clock_ns). Vivado sessions (one for the RTL arms, one for the EDIF arms: a session that has had an
    in-memory project cannot link an EDIF, "Project 1-68"); returns {(block, arm, clock): result}, Vivado version."""
    out, ver = {}, "unknown"
    for kind in ("rtl", "edif"):
        sub = [j for j in jobs if (ARMS[j[1]] == "edif") == (kind == "edif")]
        if sub:
            r, v = _session(part, sub, f"{tag}_{kind}")
            out.update(r)
            ver = v if v != "unknown" else ver
    return out, ver


def _session(part: str, jobs: list[tuple[str, str, float]], tag: str) -> tuple[dict, str]:
    batch = ROOT / "build" / "b101" / "vivado" / PARTS[part] / tag
    batch.mkdir(parents=True, exist_ok=True)
    lines = [f"set ooc(part) {part}", "set ooc(jobs) {}"]
    wds = {}
    for block, arm, ck in jobs:
        wd = batch / f"{block}__{arm}_{ck:.2f}"
        wd.mkdir(parents=True, exist_ok=True)
        for mk in ("done.txt", "error.txt"):
            (wd / mk).unlink(missing_ok=True)
        srcs = [yosys_edif(block, part, arm)["edif"]] if ARMS[arm] == "edif" else [str(s) for s in BLOCKS[block]]
        lines.append("lappend ooc(jobs) " + tcl_list([f"{block}__{arm}", TOP, str(wd), ck, ARMS[arm], srcs]))
        wds[(block, arm, ck)] = wd
    (batch / "jobs.tcl").write_text("\n".join(lines) + "\n")
    unit = f"b101-ooc-{PARTS[part]}-{tag}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"), "-source", str(TCL),
           "-tclargs", str(batch / "jobs.tcl")]
    print(f"run: {part} {tag}: {len(jobs)} jobs, scope {unit}", flush=True)
    subprocess.run(cmd, cwd=batch)
    log = batch / "vivado.log"
    m = re.search(r"Vivado v(\S+) \(64-bit\)", log.read_text()) if log.exists() else None
    return {k: dict(parse(wd, k[2]), wd=str(wd)) for k, wd in wds.items()}, (m.group(1) if m else "unknown")


def search(part: str, pairs: list[tuple[str, str]], start: float, passes: int, out: Path, fresh: bool) -> None:
    hist: dict[tuple[str, str], list[dict]] = {}
    ver = "unknown"
    for b, a in pairs:
        f = out / f"{b}__{a}.json"
        hist[(b, a)] = json.loads(f.read_text())["passes"] if f.exists() and not fresh else []
        if f.exists():
            ver = json.loads(f.read_text()).get("tool", "").replace("Vivado ", "") or ver
    todo = {k: start for k, h in hist.items() if not any(r.get("closed") for r in h)}
    base = f"run{len(list((ROOT / 'build' / 'b101' / 'vivado' / PARTS[part]).glob('run*_pass1_rtl'))) + 1}"
    for p in range(passes):
        if not todo:
            break
        res, v = run_pass(part, [(b, a, ck) for (b, a), ck in sorted(todo.items())], f"{base}_pass{p + 1}")
        ver = v if v != "unknown" else ver
        nxt = {}
        for (b, a, ck), r in res.items():
            hist[(b, a)].append(r)
            if r["status"] != "ok":
                continue
            t = math.ceil(achievable(r) * 20 - 1e-6) / 20
            fails = [x["clock_ns"] for x in hist[(b, a)] if x.get("status") == "ok" and not x["closed"]]
            closed = [x["clock_ns"] for x in hist[(b, a)] if x.get("closed")]
            if r["closed"]:
                if t <= r["clock_ns"] - 0.05 and not any(f >= t for f in fails):
                    nxt[(b, a)] = t
                continue
            t = t + (0.05 if p >= 1 else 0.0)
            if not closed or t < min(closed):
                nxt[(b, a)] = t
        todo = nxt
    write(part, hist, ver, out)


def write(part: str, hist: dict, ver: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for (b, a), h in hist.items():
        closed = [r for r in h if r.get("closed")]
        best = min(closed, key=lambda r: r["clock_ns"]) if closed else None
        if best:
            rd = out / "reports" / f"{b}__{a}"
            rd.mkdir(parents=True, exist_ok=True)
            for fn in ("utilization.rpt", "timing_summary.rpt", "timing_worst.rpt"):
                shutil.copy(Path(best["wd"]) / fn, rd / fn)
        rec = {"block": b, "arm": a, "part": part, "tool": f"Vivado {ver}", "flow": "out of context, post-route, one thread",
               "synthesis": ARMS[a], "latency_clocks": LATENCY_CLOCKS,
               "closed_at_ns": best["clock_ns"] if best else None,
               "closed_at_mhz": round(1000 / best["clock_ns"], 1) if best else None,
               "latency_ns": round(LATENCY_CLOCKS * best["clock_ns"], 3) if best else None,
               "at_closed_clock": {k: v for k, v in best.items() if k != "wd"} if best else None,
               "passes": h}
        if a in YS_SCRIPT:
            ys = yosys_edif(b, part, a)
            rec["yosys"] = {k: ys[k] for k in ("script", "script_text", "yosys", "yosys_commands", "seconds", "lut", "ff", "carry", "d_ps")}
        # perturbation records, if any, stay
        old = out / f"{b}__{a}.json"
        if old.exists() and "perturb" in json.loads(old.read_text()):
            rec["perturb"] = json.loads(old.read_text())["perturb"]
        old.write_text(json.dumps(rec, indent=1))
        print(b, a, rec["closed_at_ns"], best and {k: best[k] for k in ("lut", "ff", "lut_levels", "wns_ns", "wpws_ns")})


def perturb(part: str, pairs: list[tuple[str, str]], out: Path) -> None:
    """Re-run each closed arm at +0.01 and +0.02 ns; record the achievable period of all three."""
    jobs = []
    for b, a in pairs:
        rec = json.loads((out / f"{b}__{a}.json").read_text())
        if rec["closed_at_ns"] and rec.get("at_closed_clock"):
            jobs += [(b, a, round(rec["closed_at_ns"] + d, 2)) for d in (0.01, 0.02)]
    res, _ = run_pass(part, jobs, f"perturb{len(list((ROOT / 'build' / 'b101' / 'vivado' / PARTS[part]).glob('perturb*'))) + 1}")
    for b, a in pairs:
        f = out / f"{b}__{a}.json"
        rec = json.loads(f.read_text())
        if not rec.get("at_closed_clock"):
            continue
        pts = [{k: v for k, v in rec["at_closed_clock"].items() if k in ("clock_ns", "wns_ns", "wpws_ns", "lut", "closed")}]
        pts[0]["achievable_ns"] = round(achievable(rec["at_closed_clock"]), 3)
        for (bb, aa, ck), r in sorted(res.items(), key=lambda kv: kv[0][2]):
            if (bb, aa) == (b, a) and r["status"] == "ok":
                pts.append({"clock_ns": ck, "wns_ns": r["wns_ns"], "wpws_ns": r["wpws_ns"], "lut": r["lut"], "closed": r["closed"],
                            "achievable_ns": round(achievable(r), 3)})
        ach = [p["achievable_ns"] for p in pts]
        rec["perturb"] = {"points": pts, "achievable_min_ns": min(ach), "achievable_max_ns": max(ach),
                          "spread_ns": round(max(ach) - min(ach), 3)}
        f.write_text(json.dumps(rec, indent=1))


def table() -> None:
    """results/b101/summary.json and summary.md from the per-arm records (no tools needed)."""
    rows = []
    for part in PARTS:
        d = ROOT / "results" / "b101" / PARTS[part]
        for f in sorted(d.glob("*__*.json")):
            r = json.loads(f.read_text())
            c = r.get("at_closed_clock") or {}
            p = r.get("perturb") or {}
            rows.append({"part": PARTS[part], "block": r["block"], "arm": r["arm"], "closed_ns": r["closed_at_ns"],
                         "fmax_mhz": r["closed_at_mhz"], "latency_ns": r["latency_ns"], "lut_levels": c.get("lut_levels"),
                         "lut": c.get("lut"), "ff": c.get("ff"), "carry": c.get("carry"), "data_path_ns": c.get("data_path_ns"),
                         "vivado_s": c.get("build_seconds"), "yosys_s": (r.get("yosys") or {}).get("seconds"),
                         "spread_ns": p.get("spread_ns")})
    out = ROOT / "results" / "b101"
    (out / "summary.json").write_text(json.dumps(rows, indent=1))
    md = ["| part | block | arm | T closed (ns) | Fmax (MHz) | latency (ns) | LUT levels | LUT | FF | CARRY | seed spread (ns) | Vivado s | Yosys s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| " + " | ".join("" if v is None else str(v) for v in (r["part"], r["block"], r["arm"], (None if r["closed_ns"] is None else round(r["closed_ns"], 2)), r["fmax_mhz"],
                                                                            r["latency_ns"], r["lut_levels"], r["lut"], r["ff"], r["carry"],
                                                                            r["spread_ns"], r["vivado_s"], r["yosys_s"])) + " |")
    (out / "summary.md").write_text("\n".join(md) + "\n")
    print(f"table: {len(rows)} rows")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--part", choices=sorted(PARTS))
    ap.add_argument("--blocks", nargs="+", default=list(BLOCKS), choices=sorted(BLOCKS))
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=sorted(ARMS))
    ap.add_argument("--start", type=float, default=2.0)
    ap.add_argument("--passes", type=int, default=5)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--perturb", action="store_true", help="after the search, re-run each closed arm at +0.01 and +0.02 ns")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--yosys-only", action="store_true", help="run only the Yosys syntheses (both parts' families), no Vivado")
    a = ap.parse_args(argv)
    if a.yosys_only:
        for part in PARTS:
            for b in a.blocks:
                for x in (x for x in a.arms if x in YS_SCRIPT):
                    r = yosys_edif(b, part, x)
                    print(PARTS[part], b, x, r["lut"], r["ff"], r["carry"], r["seconds"])
        return 0
    if a.table:
        table()
        return 0
    if not a.part:
        ap.error("--part is required")
    pairs = [(b, x) for b in a.blocks for x in a.arms]
    out = ROOT / "results" / "b101" / PARTS[a.part]
    out.mkdir(parents=True, exist_ok=True)
    search(a.part, pairs, a.start, a.passes, out, a.fresh)
    if a.perturb:
        perturb(a.part, pairs, out)
    table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
