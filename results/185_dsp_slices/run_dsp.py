#!/usr/bin/env python3
"""DSP-slice experiments (brief 185): list, run and record out-of-context Vivado builds.

    python3 results/185_dsp_slices/run_dsp.py list  [--part a7|k26|vu2p] [--group mul|wide|dot|feat]
    python3 results/185_dsp_slices/run_dsp.py run   --part a7 --group mul        # takes a heavy slot (prefix 185), one Vivado session
    python3 results/185_dsp_slices/run_dsp.py parse [--part ...]                 # rebuild data/<part>.json from the run directories
    python3 results/185_dsp_slices/run_dsp.py recompute --part k26               # re-derive Fmax in data/<part>.json from the stored setup / minimum-period figures (brief 199)

Parts: a7 = xc7a100tcsg324-1 (DSP48E1), k26 = xck26-sfvc784-2LV-c (DSP48E2), vu2p = xcvu2p-fsvj2104-3-e (DSP48E2, only if the licence allows).
Each point is synthesised, placed and routed out of context at the part's target clock (one thread). WNS gives Fmax = 1000 / (clock - WNS),
one run at that clock, so an estimate; the pulse-width limit is applied as in flow/ipchar.py. Run directories: build/185_dsp/<part>/<point>/
(not committed); the small per-point files that carry the evidence (DSP cell properties, DSP lines of the methodology and DRC reports, the
synthesis DSP report) are copied to results/185_dsp_slices/raw/<part>/<point>/.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from flow import ipchar  # noqa: E402

HANDOFF = Path("/home/brendan/Claude_sandbox/_handoff")
WORK = ROOT / "build" / "185_dsp"
RTL = HERE / "rtl"
PARTS = {  # key: (part, target clock ns, wide-port limb width LB, native A x B of one slice)
    "a7": ("xc7a100tcsg324-1", 1.8, 24, (25, 18)),
    "k26": ("xck26-sfvc784-2LV-c", 1.0, 26, (27, 18)),
    "vu2p": ("xcvu2p-fsvj2104-3-e", 0.9, 26, (27, 18)),
}
# Brief 199: the clock-buffer minimum period Vivado checks as soon as the clock goes through a BUFG (measured, results/199_dsp_fmax: a7 BUFG/I 2.155 ns,
# k26 BUFGCE/I 1.379 ns = DS925 Table 84 BUFG FMAX of 725 MHz, -2 at 0.72 V). The out-of-context wrappers have no clock buffer, so their own
# reports never show it; a design clocked in a real system cannot run faster. None = not measured (vu2p).
BUF_MIN_PERIOD_NS = {"a7": 2.155, "k26": 1.379, "vu2p": None}
PEAK_G = int(os.environ.get("DSP185_PEAK_G", "4"))
PREFIX = "185"
SRC = {"mul": ["dsp_mul_pipe.sv", "dsp_mul_pipe_ooc.sv"],
       "wide": ["dsp_mul_pipe.sv", "dsp_wide_mul.sv", "dsp_wide_mul_ooc.sv"],
       "dot": ["dsp_dot.sv", "dsp_dot_ooc.sv"],
       "preadd": ["dsp_preadd.sv", "dsp_preadd_ooc.sv"],
       "simdpat": ["dsp_simd_pat.sv", "dsp_simd_pat_ooc.sv"]}
TOP = {"mul": "dsp_mul_pipe_ooc", "wide": "dsp_wide_mul_ooc", "dot": "dsp_dot_ooc", "preadd": "dsp_preadd_ooc", "simdpat": "dsp_simd_pat_ooc"}
GROUPS = {"mul": ["mul"], "wide": ["wide"], "dot": ["dot"], "feat": ["preadd", "simdpat"]}


def fmax_limits(setup_mhz, min_period_mhz, cell, buf_ns):
    """Fmax = min(setup-derived, 1000 / slice minimum period, 1000 / clock-buffer minimum period) and which one limited (brief 199)."""
    buf_mhz = round(1000.0 / buf_ns, 1) if buf_ns else None
    cand = [(v, w) for v, w in ((setup_mhz, "setup slack at the target clock"), (min_period_mhz, f"minimum period of {cell}"),
                                (buf_mhz, "clock-buffer minimum period (BUFG)")) if v]
    if not cand:
        return None, None, buf_mhz
    v, w = cand[0]
    for v2, w2 in cand[1:]:
        if v2 < v - 0.5:       # a limit within 0.5 MHz of an earlier one is the same limit (a7: slice 2.154 ns, BUFG 2.155 ns); the earlier is named
            v, w = v2, w2
    return round(v, 1), w, buf_mhz


def recompute(pk: str) -> None:
    """Re-derive fmax_mhz / fmax_bound of data/<pk>.json from the stored setup and minimum-period figures, no Vivado."""
    f = HERE / "data" / f"{pk}.json"
    d = json.loads(f.read_text())
    for r in d["points"]:
        if r.get("status") != "ok":
            continue
        r["fmax_mhz"], r["fmax_bound"], r["fmax_clock_buffer_mhz"] = fmax_limits(r.get("fmax_setup_mhz"), r.get("fmax_min_period_mhz"),
                                                                                  r.get("min_period_cell"), BUF_MIN_PERIOD_NS[pk])
    d["flow"] = d["flow"].replace("Fmax = min(1000 / (clock_ns - WNS), 1000 / the largest 'Min Period' required in the timing summary)",
                                  "Fmax = min(1000 / (clock_ns - WNS), 1000 / the largest 'Min Period' required in the timing summary, 1000 / the BUFG minimum period measured in results/199_dsp_fmax)") if "BUFG minimum" not in d["flow"] else d["flow"]
    d["brief_199"] = "fmax_mhz now also capped by the clock-buffer minimum period (BUF_MIN_PERIOD_NS); fmax_setup_mhz and fmax_min_period_mhz are unchanged"
    f.write_text(json.dumps(d, indent=1) + "\n")
    print("recomputed", f.relative_to(ROOT))


def points(kind: str, pk: str) -> list[dict]:
    """The generics of every point of one kind on one part, with the latency the RTL is written for (register stages, inputs to output)."""
    out = []
    nat = PARTS[pk][3]
    if kind == "mul":
        for na in (0, 1, 2):
            for nm in (0, 1):
                for np_ in (0, 1):
                    out.append({"WA": 18, "WB": 18, "NA": na, "NM": nm, "NP": np_, "RSTP": 0, "latency": na + nm + np_})
        for na, nm, np_, r in ((1, 1, 1, 1), (1, 1, 1, 2), (0, 0, 1, 1), (0, 0, 1, 2)):
            out.append({"WA": 18, "WB": 18, "NA": na, "NM": nm, "NP": np_, "RSTP": r, "latency": na + nm + np_})
        for na in (1, 2):
            out.append({"WA": nat[0], "WB": nat[1], "NA": na, "NM": 1, "NP": 1, "RSTP": 0, "latency": na + 2})
    elif kind == "wide":
        lb = PARTS[pk][2]
        for wa, wb in ((27, 27), (32, 32), (35, 25), (44, 35), (48, 48), (64, 64)):
            nal, nbl = (wa - 1 + 16) // 17, (wb - 1 + lb - 1) // lb
            lat = {0: None, 1: 2 + nal + (1 if nbl > 1 else 0), 2: 3 + math.ceil(math.log2(nal * nbl)) if nal * nbl > 1 else 3}
            for style, na in ((0, 1), (0, 2), (1, 1), (2, 1)):
                out.append({"WA": wa, "WB": wb, "STYLE": style, "NA": na, "LB": lb,
                            "latency": (na + 2) if style == 0 else lat[style]})
    elif kind == "dot":
        for k in (4, 8, 16):
            out.append({"W": 16, "K": k, "STYLE": 0, "TR": 1, "latency": 2 + k})
            for tr in (1, 2, 99):
                lv = int(math.ceil(math.log2(k)))
                nreg = sum(1 for l in range(lv) if (l + 1) % tr == 0 or l == lv - 1)
                out.append({"W": 16, "K": k, "STYLE": 1, "TR": tr, "latency": 3 + nreg})
    elif kind == "preadd":
        out = [{"WA": 24, "WB": 18, "VAR": 0, "latency": 4}, {"WA": 24, "WB": 18, "VAR": 1, "latency": 3}]
    elif kind == "simdpat":
        out = [{"MODE": 0, "latency": 2}, {"MODE": 1, "latency": 3}]
    return out


def pid(kind: str, g: dict) -> str:
    return kind + "_" + "_".join(f"{k}{v}" for k, v in g.items() if k != "latency")


def jobs(pk: str, group: str) -> list[dict]:
    js = []
    for kind in GROUPS[group]:
        for g in points(kind, pk):
            js.append({"kind": kind, "id": pid(kind, g), "generics": {k: v for k, v in g.items() if k != "latency"}, "latency": g["latency"],
                       "wd": WORK / pk / pid(kind, g)})
    return js


def tcl_word(v) -> str:
    s = str(v)
    return "{" + s + "}" if (not s or re.search(r'[\s"{}$\[\]\;]', s)) else s


def write_jobs(pk: str, group: str, js: list[dict], path: Path) -> None:
    part, clock = PARTS[pk][0], PARTS[pk][1]
    srcs = sorted({str(RTL / f) for kind in GROUPS[group] for f in SRC[kind]})
    lines = [f"set dsc(part) {part}", "set dsc(sources) {" + " ".join(srcs) + "}", "set dsc(jobs) {}"]
    for j in js:
        gen = " ".join(f"{k} {v}" for k, v in j["generics"].items())
        lines.append(f"lappend dsc(jobs) {{{pk}/{j['id']} {TOP[j['kind']]} {j['wd']} {clock} {{{gen}}}}}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def take_slot(text: str) -> str:
    while True:
        r = subprocess.run([str(HANDOFF / "take_heavy_slot.sh"), text], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        time.sleep(45)


def release(lock: str) -> None:
    p = Path(lock)
    if p.exists() and p.read_text().startswith(PREFIX + ":"):
        p.unlink()


def run(pk: str, group: str) -> int:
    js = jobs(pk, group)
    batch = WORK / "batch" / f"{pk}_{group}"
    write_jobs(pk, group, js, batch / "jobs.tcl")
    for j in js:
        for m in ("done.txt", "error.txt"):
            (j["wd"] / m).unlink(missing_ok=True)
    now = datetime.datetime.now()
    end = now + datetime.timedelta(minutes=max(15, int(2.5 * len(js))))
    lock = take_slot(f"{PREFIX}: Vivado impl OOC DSP-slice points {pk}/{group} ({len(js)} points, one session), {now:%H:%M}, expected end {end:%H:%M}, peak {PEAK_G}G")
    try:
        unit = f"fda-185-{pk}-{group}-{int(time.time())}"
        cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", f"MemoryMax={PEAK_G + 2}G", "nice", "-n", "15",
               ipchar.vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"),
               "-source", str(HERE / "dsp_char.tcl"), "-tclargs", str(batch / "jobs.tcl")]
        rc = subprocess.run(cmd, cwd=batch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    finally:
        release(lock)
    print(f"{pk}/{group}: exit {rc}; parsing", flush=True)
    parse(pk, group)
    return rc


# ---- parsing ---------------------------------------------------------------------------------------------------------
def prim(txt: str, name: str) -> int:
    m = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*(\d+)\s*\|", txt, re.M)
    return int(m.group(1)) if m else 0


def dsp_cells(wd: Path) -> list[dict]:
    cells = []
    f = wd / "dsp_cells.txt"
    if not f.exists():
        return cells
    for line in f.read_text().splitlines():
        t = line.split()
        if len(t) < 2:
            continue
        d = {"cell": t[0], "type": t[1]}
        for kv in t[2:]:
            k, _, v = kv.partition("=")
            d[k] = int(v) if v.isdigit() else v
        cells.append(d)
    return cells


def log_section(batch_log: Path, name: str) -> str:
    if not batch_log.exists():
        return ""
    txt = batch_log.read_text(errors="replace")
    a = txt.find(f"DSC-START {name}\n")
    b = txt.find(f"DSC-END {name} ")
    return txt[a:b] if a >= 0 and b > a else ""


def dsp_report(sec: str) -> str:
    """The synthesis 'DSP Report' tables of a job's log section (Vivado prints them after the DSP mapping)."""
    out = []
    for m in re.finditer(r"(Start DSP Report|DSP Report: [^\n]*\n(?:[^\n]*\n)*?(?=\n|Start|Finished))", sec):
        out.append(m.group(0).rstrip())
    return "\n".join(out)


def methodology_dsp(wd: Path) -> list[str]:
    lines = []
    for fn in ("methodology.rpt", "drc.rpt"):
        f = wd / fn
        if f.exists():
            for ln in f.read_text().splitlines():
                if re.search(r"\b(DPIP|DPOP|DSP|DPREG|DREG)", ln) and ln.startswith("|"):
                    lines.append(f"{fn}: {ln.strip()}")
    return lines


def parse(pk: str, group: str | None = None) -> None:
    groups = [group] if group else list(GROUPS)
    rows = []
    batch_logs = {g: WORK / "batch" / f"{pk}_{g}" / "vivado.log" for g in groups}
    for g in groups:
        for j in jobs(pk, g):
            wd = j["wd"]
            if not ((wd / "done.txt").exists() or (wd / "error.txt").exists()):
                continue
            if not (wd / "power.rpt").exists() and (wd / "done.txt").exists():
                (wd / "power.rpt").write_text("")      # power is not measured here; flow.ipchar.parse expects the file
            r = ipchar.parse(wd, PARTS[pk][1])
            r.update({"id": j["id"], "kind": j["kind"], "params": j["generics"], "latency_clocks": j["latency"]})
            if r["status"] == "ok":
                u = (wd / "utilization.rpt").read_text()
                r["carry"] = prim(u, "CARRY4") + prim(u, "CARRY8")
                us = (wd / "utilization_synth.rpt").read_text()
                r["dsp_synth"] = ipchar._row(us, "DSPs") or 0
                r["dsp"] = r.get("dsp") or 0
                rt = (wd / "timing_worst_setup.rpt").read_text()
                m = re.search(r"Logic Levels:\s+(\d+)", rt)
                r["logic_levels"] = int(m.group(1)) if m else None
                # planner note 2026-11-23: our own per-level and per-register delay numbers, from the worst setup path
                d = re.search(r"Data Path Delay:\s+([\d.]+)ns\s+\(logic ([\d.]+)ns \(([\d.]+)%\)\s+route ([\d.]+)ns", rt)
                r["path_delay_ns"], r["path_logic_ns"], r["path_route_ns"] = (float(d.group(1)), float(d.group(2)), float(d.group(4))) if d else (None, None, None)
                sr = re.search(r"Source:\s+(\S+).*?Destination:\s+(\S+)", rt, re.S)
                r["path_source"], r["path_dest"] = (sr.group(1), sr.group(2)) if sr else (None, None)
                r["path_per_level_ns"] = round(r["path_delay_ns"] / r["logic_levels"], 3) if r["path_delay_ns"] and r["logic_levels"] else None
                r["runtime_s"] = int((wd / "done.txt").read_text().strip())
                # The slice's own limit is a "Min Period" check (DSP48E1/CLK required 2.154 ns at -1), an absolute period, not a half-period pulse
                # width: flow.ipchar.parse's 2 x shortfall rule over-penalises it, so Fmax is recomputed here (the slice limit is 1000 / required).
                ts = (wd / "timing_summary.rpt").read_text()
                mp = [(m.group(1), float(m.group(2))) for m in re.finditer(r"^Min Period\s+\S+\s+(\S+)\s+\S+\s+([\d.]+)\s+[\d.]+\s+-?[\d.]+", ts, re.M)]
                r["min_period_required_ns"] = max((v for _, v in mp), default=None)
                r["min_period_cell"] = max(mp, key=lambda x: x[1])[0] if mp else None
                r["fmax_ipchar_mhz"] = r.get("fmax_mhz")
                r["fmax_min_period_mhz"] = round(1000.0 / r["min_period_required_ns"], 1) if r["min_period_required_ns"] else None
                r["fmax_mhz"], r["fmax_bound"], r["fmax_clock_buffer_mhz"] = fmax_limits(r.get("fmax_setup_mhz"), r["fmax_min_period_mhz"],
                                                                                          r["min_period_cell"], BUF_MIN_PERIOD_NS[pk])
                r["dsp_cells"] = dsp_cells(wd)
                r["methodology_dsp"] = methodology_dsp(wd)
                for k in ("power_w",):
                    r.pop(k, None)
                dst = HERE / "raw" / pk / j["id"]
                dst.mkdir(parents=True, exist_ok=True)
                if (wd / "dsp_cells.txt").exists():
                    shutil.copy(wd / "dsp_cells.txt", dst / "dsp_cells.txt")
                (dst / "dsp_lines_methodology_drc.txt").write_text("\n".join(r["methodology_dsp"]) + "\n")
                (dst / "synth_dsp_report.txt").write_text(dsp_report(log_section(batch_logs[g], f"{pk}/{j['id']}")) + "\n")
                shutil.copy(wd / "timing_worst_setup.rpt", dst / "timing_worst_setup.rpt")
                (dst / "pulse_width_checks.txt").write_text(ts.split("Pulse Width Checks", 1)[-1][:1800] if "Pulse Width Checks" in ts else "")
            rows.append(r)
    f = HERE / "data" / f"{pk}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(f.read_text()) if f.exists() else {"points": []}
    merged = {p["id"]: p for p in old["points"]}
    merged.update({r["id"]: r for r in rows})
    tool = "Vivado (version not read)"
    for lg in batch_logs.values():
        if lg.exists():
            h = lg.read_text(errors="replace")[:4000]
            m, b = re.search(r"Vivado v(\S+) \(64-bit\)", h), re.search(r"SW Build (\d+)", h)
            if m:
                tool = f"Vivado {m.group(1)}" + (f" (build {b.group(1)})" if b else "")
    out = {"schema": "fda-185/dsp_slices/1", "part_key": pk, "part": PARTS[pk][0], "clock_ns": PARTS[pk][1], "tool": tool,
           "date": datetime.date.today().isoformat(), "brief": 185,
           "flow": "out-of-context synth_design, opt_design, place_design, route_design; one thread; clock on port clk only; kept (DONT_TOUCH) registers on "
                   "every port of the wrapper, so the timed path is register to register through the module under test; I/O paths unconstrained; "
                   "Fmax = min(1000 / (clock_ns - WNS), 1000 / the largest 'Min Period' required in the timing summary, 1000 / the BUFG minimum period measured in results/199_dsp_fmax) after routing, one run at that clock (an estimate); a setup-limited Fmax above the slice's own minimum period is not reachable",
           "points": sorted(merged.values(), key=lambda r: r["id"])}
    f.write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", f.relative_to(ROOT), len(out["points"]), "points")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "run", "parse", "recompute"])
    ap.add_argument("--part", default="a7")
    ap.add_argument("--group", default="")
    a = ap.parse_args()
    if a.cmd == "list":
        for g in ([a.group] if a.group else GROUPS):
            for j in jobs(a.part, g):
                print(a.part, g, j["id"], "latency", j["latency"])
        return 0
    if a.cmd == "recompute":
        recompute(a.part)
        return 0
    if a.cmd == "parse":
        parse(a.part, a.group or None)
        return 0
    return run(a.part, a.group)


if __name__ == "__main__":
    sys.exit(main())
