#!/usr/bin/env python3
"""Verified Pareto surface for one arithmetic function on one FPGA fabric (brief 137, phase 0): CORDIC sin/cos.

The design space (families, word lengths, iterations, rounding), the bit-exact NumPy model, the SystemVerilog generator and
the analytical FPGA cost models belong to HW_Design_Space_Agent (read, not changed); this module imports them from a
checkout (``$HW_DSE_SRC``, default ``<sandbox>/HW_Design_Space_Agent/src``) and adds what is new here: a fixed point list, a
verification record per point, a Vivado out-of-context implementation driver, the report parsers, the cost-model comparison and
the figures. See docs/arithmetic_pareto_plan.md.

    python3 flow/arith_pareto.py verify  --out results/137_arith_pareto/verify.json        (Icarus; no Vivado)
    python3 flow/arith_pareto.py export  --part xc7a35tcpg236-1 --clock 3.5 --work <dir>   (RTL + one Vivado Tcl)
    <vivado> -mode batch -source <dir>/run.tcl                                             (heavy slot; run_all below)
    python3 flow/arith_pareto.py collect --part xc7a35tcpg236-1 --work <dir> --out results/137_arith_pareto/<tag>
    python3 flow/arith_pareto.py report                                                    (compare + figures from the records)

The parsers and the comparison maths read only committed records and do not need hw_dse; ``verify``, ``export`` and the
predictions do.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "137_arith_pareto"

# (id, family, params). Chosen to span the knobs, none equal to a point already in HW_Design_Space_Agent's
# eval/data/vivado_measured*.csv (so the refit model is also tested out of sample), plus P13 = the reference pipelined
# anchor (W=16, N=14) as a bridge to the earlier-release data. "short" fields: angle_guard ag, frac_guard fg.
POINTS = [
    ("P01", "iterative", dict(data_width=14, n_iter=12, angle_guard=0, frac_guard=0, rounding="trunc")),
    ("P02", "iterative", dict(data_width=20, n_iter=18, angle_guard=1, frac_guard=2, rounding="round")),
    ("P03", "unrolled_k", dict(data_width=20, n_iter=18, angle_guard=0, frac_guard=1, rounding="trunc", k=2)),
    ("P04", "unrolled_k", dict(data_width=12, n_iter=12, angle_guard=0, frac_guard=0, rounding="trunc", k=4)),
    ("P05", "unrolled_k", dict(data_width=18, n_iter=16, angle_guard=0, frac_guard=2, rounding="round", k=6)),
    ("P06", "pipelined", dict(data_width=10, n_iter=10, angle_guard=0, frac_guard=0, rounding="trunc")),
    ("P07", "pipelined", dict(data_width=20, n_iter=18, angle_guard=1, frac_guard=2, rounding="round")),
    ("P08", "pipelined", dict(data_width=14, n_iter=12, angle_guard=0, frac_guard=0, rounding="round")),
    ("P09", "pipelined_m", dict(data_width=18, n_iter=16, angle_guard=0, frac_guard=0, rounding="trunc", m=3)),
    ("P10", "pipelined_m", dict(data_width=12, n_iter=12, angle_guard=0, frac_guard=0, rounding="round", m=2)),
    ("P11", "pipelined_m", dict(data_width=22, n_iter=20, angle_guard=2, frac_guard=1, rounding="round", m=5)),
    ("P12", "pipelined_m", dict(data_width=14, n_iter=12, angle_guard=0, frac_guard=0, rounding="trunc", m=8)),
    ("P13", "pipelined", dict(data_width=16, n_iter=14, angle_guard=0, frac_guard=0, rounding="trunc")),
]
K26_IDS = ["P01", "P04", "P07", "P09"]
PARTS = {"xc7a35tcpg236-1": {"tag": "artix7", "label": "Artix-7 xc7a35t-1", "clock": 3.5, "ids": [p[0] for p in POINTS]},
         "xck26-sfvc784-2LV-c": {"tag": "k26", "label": "Zynq UltraScale+ K26 (xck26)", "clock": 2.0, "ids": K26_IDS}}


def hwdse():
    """Import hw_dse from a checkout and return the pieces this module uses."""
    import os
    src = os.environ.get("HW_DSE_SRC") or str(ROOT.parents[1] / "HW_Design_Space_Agent" / "src")
    if not Path(src).is_dir():
        sys.exit(f"arith_pareto: hw_dse source not found at {src} (set HW_DSE_SRC)")
    if src not in sys.path:
        sys.path.insert(0, src)
    from hw_dse.families import ArchConfig
    from hw_dse.models.cordic_bitexact import accuracy, sweep_angles
    from hw_dse.models.cost_fpga import FpgaCostModel
    from hw_dse.rtl import sim
    from hw_dse.rtl.generator import generate
    return dict(ArchConfig=ArchConfig, accuracy=accuracy, sweep_angles=sweep_angles, FpgaCostModel=FpgaCostModel, sim=sim,
                generate=generate, src=Path(src))


def arch_of(H, family, params):
    return H["ArchConfig"].from_params(family, params)


# ---------------------------------------------------------------- verification
def verify(out: Path) -> int:
    """Simulate every point's generated RTL in Icarus on the model's sweep (exhaustive for W <= 16, else 2^17 dense angles) and
    compare every output code with the bit-exact model; record the error against ideal sin/cos and the measured latency."""
    H = hwdse()
    rows = []
    for pid, fam, params in POINTS:
        arch = arch_of(H, fam, params)
        v = H["sim"].verify_rtl(arch, simulator="icarus")
        acc = H["accuracy"](arch.numerics)
        rows.append(dict(id=pid, key=arch.key(), family=fam, **params, simulator=v.simulator_version, sweep=v.sweep,
                         n_angles=v.n_angles, n_results=v.n_results, mismatches=v.mismatches,
                         latency_expected=v.latency_expected, latency_measured=v.latency_measured, latency_ok=v.latency_ok,
                         passed=v.passed, max_abs_err_lsb=round(acc.max_abs_lsb, 4), rms_err_lsb=round(acc.rms_lsb, 4),
                         accuracy_bits=round(acc.accuracy_bits, 3), error_sweep=acc.sweep, seconds=v.seconds))
        print(pid, arch.key(), "PASS" if v.passed else "FAIL", f"mism={v.mismatches} lat={v.latency_measured} err={acc.max_abs_lsb:.3f} LSB")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(schema="fda/arith_pareto_verify/v1", points=rows), indent=1) + "\n")
    return 0 if all(r["passed"] for r in rows) else 1


# ------------------------------------------------------------------- Vivado
TCL = """# Generated by flow/arith_pareto.py (brief 137): out-of-context synthesis, place and route of each point, one session.
#   vivado -mode batch -source run.tcl
set_param general.maxThreads {threads}
set_param synth.maxThreads {threads}
set part {part}
set clock_ns {clock}
foreach job {{{jobs}}} {{
    lassign $job name top
    set wd [file join [file dirname [info script]] $name]
    set t0 [clock seconds]
    if {{[catch {{
        create_project -in_memory -part $part
        read_verilog -sv [file join $wd $top.sv]
        set f [open $wd/clock.xdc w]; puts $f "create_clock -period $clock_ns -name clk \\[get_ports clk\\]"; close $f
        read_xdc -mode out_of_context $wd/clock.xdc
        synth_design -top $top -part $part -mode out_of_context
        report_utilization -file $wd/utilization_synth.rpt
        report_timing_summary -max_paths 3 -file $wd/timing_synth.rpt
        write_verilog -force -mode funcsim $wd/netlist_synth.v
        opt_design
        place_design
        route_design
        report_utilization -file $wd/utilization.rpt
        report_timing_summary -max_paths 5 -file $wd/timing.rpt
        report_power -file $wd/power.rpt
        set f [open $wd/done.txt w]; puts $f [expr {{[clock seconds] - $t0}}]; close $f
    }} err]}} {{
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "arith_pareto: $name failed: $err"
    }}
    catch {{close_project -quiet}}
    puts "arith_pareto: $name finished in [expr {{[clock seconds] - $t0}}] s"
}}
"""


def export(part: str, clock: float, work: Path, threads: int, ids: list[str] | None) -> None:
    H = hwdse()
    work.mkdir(parents=True, exist_ok=True)
    want = ids or PARTS[part]["ids"]
    jobs = []
    for pid, fam, params in POINTS:
        if pid not in want:
            continue
        d = H["generate"](arch_of(H, fam, params))
        wd = work / pid
        d.write(wd)
        (wd / "module.txt").write_text(d.module + "\n")
        jobs.append(f"{{{pid} {d.module}}}")
    (work / "run.tcl").write_text(TCL.format(threads=threads, part=part, clock=clock, jobs=" ".join(jobs)))
    print(f"exported {len(jobs)} points for {part} at {clock} ns to {work}")


def parse_util(text: str) -> dict:
    """LUTs, registers, carry cells, DSPs, BRAM tiles from a report_utilization text (7-series and UltraScale+ labels)."""
    def first(*labels):
        for lab in labels:
            m = re.search(rf"^\|\s*{re.escape(lab)}\*?\s*\|\s*(\d+)\s*\|", text, re.M)
            if m:
                return int(m.group(1))
        return None
    return dict(luts=first("Slice LUTs", "CLB LUTs"), ffs=first("Slice Registers", "CLB Registers"),
                carry=first("CARRY4", "CARRY8"), dsp=first("DSPs") or 0, bram=first("Block RAM Tile") or 0,
                lut_mem=first("LUT as Memory") or 0)


def parse_wns(text: str) -> dict:
    m = re.search(r"Design Timing Summary.*?WNS\(ns\).*?\n\s*-+.*?\n\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\d+)\s+(\d+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)", text, re.S)
    if not m:
        raise ValueError("no Design Timing Summary in report")
    return dict(wns=float(m.group(1)), tns=float(m.group(2)), whs=float(m.group(5)))


def parse_power(text: str) -> dict:
    def num(label):
        m = re.search(rf"^\|\s*{re.escape(label)}\s*\|\s*([0-9.]+)", text, re.M)
        return float(m.group(1)) if m else None
    m = re.search(r"^\|\s*Confidence Level\s*\|\s*(\w+)", text, re.M)
    return dict(total_w=num("Total On-Chip Power (W)"), dynamic_w=num("Dynamic (W)"), static_w=num("Device Static (W)"),
                confidence=m.group(1) if m else None)


def _clean(text: str) -> str:
    """Strip dates, host, command line and local paths from a Vivado report before it is committed."""
    keep = []
    for ln in text.splitlines():
        if re.match(r"^\|\s*(Date|Host|Command)\s*:", ln) or re.match(r"^(Copyright|Version|Date|Host|Command)\b", ln):
            continue
        keep.append(re.sub(r"/home/[^ |]+", "<path>", ln))
    return "\n".join(keep) + "\n"


def collect(part: str, work: Path, out: Path, clock: float, vivado_version: str, threads: int) -> None:
    rows = []
    out.mkdir(parents=True, exist_ok=True)
    for pid, fam, params in POINTS:
        wd = work / pid
        if not wd.is_dir():
            continue
        if (wd / "error.txt").exists():
            rows.append(dict(id=pid, error=(wd / "error.txt").read_text().strip()[:300]))
            continue
        r = dict(id=pid, part=part, vivado=vivado_version, clock_ns=clock, threads=threads,
                 seconds=int((wd / "done.txt").read_text().strip()))
        for stage, util, tim in (("synth", "utilization_synth.rpt", "timing_synth.rpt"), ("route", "utilization.rpt", "timing.rpt")):
            u, t = parse_util((wd / util).read_text()), parse_wns((wd / tim).read_text())
            r[stage] = dict(**u, **t, fmax_mhz=round(1000.0 / (clock - t["wns"]), 2))
        r["power"] = parse_power((wd / "power.rpt").read_text())
        rows.append(r)
        d = out / "reports" / pid
        d.mkdir(parents=True, exist_ok=True)
        for f in ("utilization_synth.rpt", "timing_synth.rpt", "utilization.rpt", "timing.rpt", "power.rpt"):
            (d / f).write_text(_clean((wd / f).read_text()))
        (d / "module.txt").write_text((wd / "module.txt").read_text())
    (out / "measured.json").write_text(json.dumps(dict(schema="fda/arith_pareto_measured/v1", part=part, rows=rows), indent=1) + "\n")
    print(f"collected {len(rows)} points to {out}")


# ----------------------------------------------------- comparison and Pareto
def predictions(models: dict, ids: list[str]) -> dict:
    """{model name: {id: estimate dict}} from hw_dse's FPGA cost models."""
    H = hwdse()
    out = {}
    for name, path in models.items():
        cm = H["FpgaCostModel"](path)
        out[name] = {}
        for pid, fam, params in POINTS:
            if pid in ids:
                arch = arch_of(H, fam, params)
                e = cm.estimate(arch)
                out[name][pid] = dict(luts=e.area["luts"], ffs=e.area["ffs"], fmax_mhz=e.fmax_mhz, latency_cycles=arch.latency_cycles,
                                      results_per_cycle=arch.results_per_cycle, key=arch.key(), calibration=cm.calibration_id)
    return out


def rel(pred: float, meas: float) -> float:
    return (pred - meas) / meas * 100.0


def errors(pred: dict, meas: list[dict], stage: str) -> dict:
    """Per-axis signed % error of prediction against measurement: {axis: [(id, err_pct)]}, and the RMS and max-abs per axis."""
    out = {"luts": [], "ffs": [], "fmax_mhz": []}
    for r in meas:
        if "error" in r or r["id"] not in pred:
            continue
        for ax in out:
            out[ax].append((r["id"], rel(pred[r["id"]][ax], r[stage][ax])))
    summ = {}
    for ax, v in out.items():
        e = [x for _, x in v]
        summ[ax] = dict(n=len(e), rms=round(math.sqrt(sum(x * x for x in e) / len(e)), 2), max_abs=round(max(abs(x) for x in e), 2),
                        bias=round(statistics.fmean(e), 2))
    return dict(per_point=out, summary=summ)


def dominates(a: tuple, b: tuple) -> bool:
    """a dominates b when a is no worse on every objective (all minimised) and better on at least one."""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def front(points: dict[str, tuple]) -> list[str]:
    return sorted(k for k, v in points.items() if not any(dominates(w, v) for j, w in points.items() if j != k))


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float("nan")


def objectives(meas: list[dict], ver: dict, stage: str = "route") -> dict[str, dict]:
    """Per point: area (LUT+FF), latency (ns), throughput (Msps), accuracy bits, with the model-independent definitions."""
    H = hwdse()
    rows = {}
    for r in meas:
        if "error" in r:
            continue
        pid = r["id"]
        _, fam, params = next(p for p in POINTS if p[0] == pid)
        arch = arch_of(H, fam, params)
        s = r[stage]
        rows[pid] = dict(area=s["luts"] + s["ffs"], luts=s["luts"], ffs=s["ffs"], fmax=s["fmax_mhz"], cycles=arch.latency_cycles,
                         latency_ns=arch.latency_cycles * 1000.0 / s["fmax_mhz"], throughput=s["fmax_mhz"] * arch.results_per_cycle,
                         acc_bits=ver[pid]["accuracy_bits"], err_lsb=ver[pid]["max_abs_err_lsb"], family=fam, power_dyn=r["power"]["dynamic_w"])
    return rows


# ------------------------------------------------- structural equivalence
MITER = """module m(input clk, rst, valid_in, input [{w1}:0] th, output ok);
  wire vg, vd, rg, rd; wire [{w1}:0] cg, sg, cd, sd;
  gold g(.clk(clk),.rst(rst),.valid_in(valid_in),.ready(rg),.theta_in(th),.valid_out(vg),.cos_out(cg),.sin_out(sg));
  gate d(.clk(clk),.rst(rst),.valid_in(valid_in),.ready(rd),.theta_in(th),.valid_out(vd),.cos_out(cd),.sin_out(sd));
  assign ok = (vg == vd) && (rg == rd) && (!vg || (cg == cd && sg == sd));
endmodule
"""


def equiv_point(work: Path, pid: str, scratch: Path, yosys: str, timeout: int) -> dict:
    """Bounded equivalence of Vivado's post-synthesis netlist (write_verilog -mode funcsim) against the generated RTL: a miter
    of both, free inputs, every register at 0, rst high in the first clock, then latency + 4 clocks; outputs compared whenever
    either side says valid. Yosys SAT with the Xilinx simulation cells. Bounded, not a proof; says so in the record."""
    import subprocess
    import time
    H = hwdse()
    _, fam, params = next(p for p in POINTS if p[0] == pid)
    arch = arch_of(H, fam, params)
    mod = (work / pid / "module.txt").read_text().strip()
    d = scratch / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "gold.sv").write_text(re.sub(rf"^module {mod}\b", "module gold", (work / pid / f"{mod}.sv").read_text(), flags=re.M))
    net = (work / pid / "netlist_synth.v").read_text()
    net = net[:net.index("`ifndef GLBL")] if "`ifndef GLBL" in net else net
    (d / "gate.v").write_text(re.sub(rf"^module {mod}\b", "module gate", net, flags=re.M))
    (d / "m.sv").write_text(MITER.format(w1=params["data_width"] - 1))
    depth = arch.latency_cycles + 4
    script = (f"read_verilog -sv gold.sv; read_verilog -DNO_ICARUS +/xilinx/cells_sim.v; read_verilog gate.v; read_verilog -sv m.sv; "
              f"hierarchy -top m; proc; flatten; memory; memory_map; opt_clean; sat -seq {depth} -prove ok 1 -set-init-zero -set-at 1 rst 1 -verify")
    t0 = time.time()
    try:
        p = subprocess.run([yosys, "-q", "-p", script], cwd=d, capture_output=True, text=True, timeout=timeout)
        status = "equivalent (bounded)" if p.returncode == 0 else "NOT equivalent or tool error"
        tail = (p.stdout + p.stderr).strip().splitlines()[-1:] if p.returncode else []
    except subprocess.TimeoutExpired:
        status, tail = f"timeout after {timeout} s", []
    return dict(id=pid, status=status, depth_clocks=depth, seconds=round(time.time() - t0, 1), note=" ".join(tail)[:200])


def equiv(work: Path, out: Path, yosys: str, timeout: int, ids: list[str] | None) -> int:
    import tempfile
    recs = []
    with tempfile.TemporaryDirectory(prefix="arith_eq_") as t:
        for pid, *_ in POINTS:
            if ids and pid not in ids or not (work / pid / "netlist_synth.v").exists():
                continue
            r = equiv_point(work, pid, Path(t), yosys, timeout)
            print(r, flush=True)
            recs.append(r)
            out.write_text(json.dumps(dict(schema="fda/arith_pareto_equiv/v1", method="yosys sat, miter of RTL and Vivado funcsim netlist", points=recs), indent=1) + "\n")
    out.write_text(json.dumps(dict(schema="fda/arith_pareto_equiv/v1", method="yosys sat, miter of RTL and Vivado funcsim netlist", points=recs), indent=1) + "\n")
    return 0


# ------------------------------------------------------------------- report
FLOOR_BITS = 8.0
MODELS = {"default (2-anchor)": None, "refit m4 (51 points)": "REFIT"}


def _model_paths(H) -> dict:
    refit = str(H["src"] / "hw_dse" / "models" / "calibration_artix7_refit_vivado-2025.2-m4.yaml")
    return {k: (refit if v == "REFIT" else v) for k, v in MODELS.items()}


def report(res: Path) -> int:
    """Comparison tables, the Pareto fronts and the figures from the committed records (needs hw_dse for the predictions only)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    H = hwdse()
    ver = {r["id"]: r for r in json.loads((res / "verify.json").read_text())["points"]}
    fabrics = {}
    for part, info in PARTS.items():
        f = res / info["tag"] / "measured.json"
        if f.exists():
            fabrics[part] = json.loads(f.read_text())["rows"]
    out = {"schema": "fda/arith_pareto_comparison/v1", "fabrics": {}}
    md = []
    for part, rows in fabrics.items():
        info = PARTS[part]
        ids = [r["id"] for r in rows if "error" not in r]
        pred = predictions(_model_paths(H), ids)
        obj = objectives(rows, ver)
        fr = {"latency": front({k: (v["area"], v["latency_ns"], -v["acc_bits"]) for k, v in obj.items()}),
              "throughput": front({k: (v["area"], 1000.0 / v["throughput"], -v["acc_bits"]) for k, v in obj.items()})}
        comp = {}
        for mname, pm in pred.items():
            comp[mname] = {st: errors(pm, rows, st) for st in ("synth", "route")}
        rank = {}
        for ax in ("luts", "ffs", "fmax_mhz"):
            for st in ("synth", "route"):
                m = [r for r in rows if "error" not in r]
                rank[f"{ax}_{st}"] = round(spearman([pred["default (2-anchor)"][r["id"]][ax] for r in m], [r[st][ax] for r in m]), 3)
        m = [r for r in rows if "error" not in r]
        rank["power_dyn_vs_luts+ffs"] = round(spearman([pred["default (2-anchor)"][r["id"]]["luts"] + pred["default (2-anchor)"][r["id"]]["ffs"] for r in m],
                                                      [r["power"]["dynamic_w"] for r in m]), 3)
        # a spec: accuracy at least FLOOR bits; 2-D fronts (area against latency, area against 1/throughput) among the points meeting it,
        # measured and as the default cost model would have predicted them, to ask whether the model would have pruned a front point
        ok = {k: v for k, v in obj.items() if v["acc_bits"] >= FLOOR_BITS}
        pm = pred["default (2-anchor)"]
        def pobj(pid):
            e = pm[pid]
            return (e["luts"] + e["ffs"], e["latency_cycles"] * 1000.0 / e["fmax_mhz"], 1000.0 / (e["fmax_mhz"] * e["results_per_cycle"]))
        fl = {"measured": front({k: (v["area"], v["latency_ns"]) for k, v in ok.items()}),
              "predicted": front({k: pobj(k)[:2] for k in ok})}
        ft = {"measured": front({k: (v["area"], 1000.0 / v["throughput"]) for k, v in ok.items()}),
              "predicted": front({k: (pobj(k)[0], pobj(k)[2]) for k in ok})}
        fr["floor_bits"] = FLOOR_BITS
        fr["floor_latency"], fr["floor_throughput"] = fl, ft
        out["fabrics"][part] = dict(label=info["label"], clock_ns=rows[0]["clock_ns"], front=fr, objectives=obj, predictions=pred, comparison=comp, rank=rank)
        md.append(f"### {info['label']}, target {rows[0]['clock_ns']} ns\n")
        md.append("| id | family | W/N | LUT | FF | Fmax synth | Fmax route | WNS route | lat clk | latency ns | Msps | err LSB | dyn mW | on front |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in m:
            o = obj[r["id"]]
            _, fam, params = next(p for p in POINTS if p[0] == r["id"])
            tag = ("L" if r["id"] in fr["latency"] else "") + ("T" if r["id"] in fr["throughput"] else "")
            md.append(f"| {r['id']} | {fam} | {params['data_width']}/{params['n_iter']} | {r['route']['luts']} | {r['route']['ffs']} | {r['synth']['fmax_mhz']:.0f} | {r['route']['fmax_mhz']:.0f} | "
                      f"{r['route']['wns']:.2f} | {o['cycles']} | {o['latency_ns']:.1f} | {o['throughput']:.0f} | {o['err_lsb']:.2f} | {r['power']['dynamic_w']*1000:.0f} | {tag or '-'} |")
        md.append("")
        for mname, c in comp.items():
            md.append(f"{mname}: RMS % error of prediction against Vivado (max abs in brackets)\n")
            md.append("| stage | LUT | FF | Fmax |\n|---|---|---|---|")
            for st in ("synth", "route"):
                s_ = c[st]["summary"]
                md.append(f"| post-{st} | " + " | ".join(f"{s_[a]['rms']:.1f} ({s_[a]['max_abs']:.1f}), bias {s_[a]['bias']:+.1f}" for a in ("luts", "ffs", "fmax_mhz")) + " |")
            md.append("")
        for nm, f2 in (("area against latency", fl), ("area against throughput", ft)):
            miss = sorted(set(f2["measured"]) - set(f2["predicted"]))
            extra = sorted(set(f2["predicted"]) - set(f2["measured"]))
            md.append(f"Front of {len(ok)} points with at least {FLOOR_BITS} accuracy bits, {nm}: measured {', '.join(f2['measured'])}; the default model's front {', '.join(f2['predicted'])}; "
                      f"measured front points the model's front would have dropped: {', '.join(miss) or 'none'}; model-front points that are not on the measured front: {', '.join(extra) or 'none'}.\n")
        md.append("Spearman rank correlation, default model against measurement: " + ", ".join(f"{k} {v}" for k, v in rank.items()) + "\n")
    (res / "comparison.json").write_text(json.dumps(out, indent=1) + "\n")
    (res / "comparison.md").write_text("\n".join(md) + "\n")

    # figures
    col = {"iterative": "#1f77b4", "unrolled_k": "#ff7f0e", "pipelined": "#2ca02c", "pipelined_m": "#d62728"}
    mk = {"iterative": "o", "unrolled_k": "s", "pipelined": "^", "pipelined_m": "D"}
    a7 = out["fabrics"].get("xc7a35tcpg236-1")
    if a7:
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
        for k, (xkey, xl, fk) in enumerate((("latency_ns", "latency (ns)", "latency"), ("throughput", "throughput (Msps)", "throughput"))):
            for pid, o in a7["objectives"].items():
                on = pid in a7["front"][fk]
                ax[k].scatter(o[xkey], o["area"], marker=mk[o["family"]], s=70 + 6 * o["acc_bits"], facecolor=col[o["family"]] if on else "none",
                              edgecolor=col[o["family"]], linewidth=1.6)
                ax[k].annotate(f"{pid}\n{o['acc_bits']:.1f} b", (o[xkey], o["area"]), fontsize=7, xytext=(5, 4), textcoords="offset points")
            f2 = a7["front"]["floor_latency" if k == 0 else "floor_throughput"]["measured"]
            pts = sorted((a7["objectives"][i][xkey], a7["objectives"][i]["area"]) for i in f2)
            if k == 1:
                pts = sorted(pts, reverse=True)
            ax[k].step([x for x, _ in pts], [y for _, y in pts], where="post" if k == 0 else "pre", color="#444", lw=1, ls="--")
            ax[k].set_xlabel(xl); ax[k].set_ylabel("area: LUT + FF (post-route)"); ax[k].set_xscale("log"); ax[k].set_yscale("log")
            ax[k].grid(True, which="both", alpha=0.25)
            ax[k].set_title("lower left is better" if k == 0 else "lower right is better")
        h = [plt.Line2D([], [], marker=mk[f], color=col[f], linestyle="", label=f) for f in col]
        ax[0].legend(handles=h, fontsize=8, loc="lower right")
        fig.suptitle("CORDIC sin/cos on Artix-7 xc7a35t-1, Vivado 2026.1 out of context, post-route at %.1f ns (labels: accuracy bits)\nfilled: on the 3-objective front incl. accuracy; dashed: area front among points with accuracy >= %g bits" % (a7["clock_ns"], FLOOR_BITS), fontsize=10)
        fig.tight_layout(); fig.savefig(res / "fig1_pareto_artix7.svg"); fig.savefig(res / "fig1_pareto_artix7.png", dpi=130); plt.close(fig)

        fig, ax = plt.subplots(1, 3, figsize=(13, 4.4))
        for k, (axis, lab) in enumerate((("luts", "LUTs"), ("ffs", "FFs"), ("fmax_mhz", "Fmax (MHz)"))):
            lo, hi = 1e9, 0
            for mname, mkr, c in (("default (2-anchor)", "o", "#555"), ("refit m4 (51 points)", "x", "#c33")):
                xs = [r[axis] for r in [rr for rr in fabrics["xc7a35tcpg236-1"] if "error" not in rr] for r in [r["route"]]]
                ys = [a7["predictions"][mname][r["id"]][axis] for r in fabrics["xc7a35tcpg236-1"] if "error" not in r]
                ax[k].scatter(xs, ys, marker=mkr, color=c, label=mname, s=40)
                lo, hi = min(lo, *xs, *ys), max(hi, *xs, *ys)
            ax[k].plot([lo, hi], [lo, hi], "k-", lw=0.8); ax[k].plot([lo, hi], [lo * 1.2, hi * 1.2], "k:", lw=0.6); ax[k].plot([lo, hi], [lo / 1.2, hi / 1.2], "k:", lw=0.6)
            ax[k].set_xlabel(f"Vivado 2026.1 post-route {lab}"); ax[k].set_ylabel(f"cost model {lab}"); ax[k].set_xscale("log"); ax[k].set_yscale("log")
            ax[k].grid(True, which="both", alpha=0.25); ax[k].set_title(lab + " (dotted: +-20 %)")
        ax[0].legend(fontsize=7)
        fig.tight_layout(); fig.savefig(res / "fig2_model_vs_vivado.svg"); fig.savefig(res / "fig2_model_vs_vivado.png", dpi=130); plt.close(fig)

    k26 = out["fabrics"].get("xck26-sfvc784-2LV-c")
    if a7 and k26:
        ids = [i for i in k26["objectives"] if i in a7["objectives"]]
        fig, ax = plt.subplots(1, 2, figsize=(10, 4.2))
        for pid in ids:
            a, b = a7["objectives"][pid], k26["objectives"][pid]
            ax[0].plot([a["latency_ns"], b["latency_ns"]], [a["area"], b["area"]], "-", color="#888")
            ax[0].scatter(a["latency_ns"], a["area"], color="#1f77b4"); ax[0].scatter(b["latency_ns"], b["area"], color="#d62728")
            ax[0].annotate(pid, (b["latency_ns"], b["area"]), fontsize=8, xytext=(4, 3), textcoords="offset points")
        ax[0].set_xscale("log"); ax[0].set_yscale("log"); ax[0].set_xlabel("latency (ns)"); ax[0].set_ylabel("area: LUT + FF"); ax[0].grid(True, which="both", alpha=0.25)
        ax[0].set_title("blue: Artix-7, red: K26 (same RTL)")
        w = 0.38
        xs = range(len(ids))
        ax[1].bar([x - w / 2 for x in xs], [a7["objectives"][i]["fmax"] for i in ids], w, color="#1f77b4", label="Artix-7 xc7a35t-1")
        ax[1].bar([x + w / 2 for x in xs], [k26["objectives"][i]["fmax"] for i in ids], w, color="#d62728", label="K26")
        ax[1].set_xticks(list(xs)); ax[1].set_xticklabels(ids); ax[1].set_ylabel("Fmax (MHz), post-route"); ax[1].legend(fontsize=8); ax[1].grid(True, axis="y", alpha=0.25)
        fig.tight_layout(); fig.savefig(res / "fig3_k26_vs_artix7.svg"); fig.savefig(res / "fig3_k26_vs_artix7.png", dpi=130); plt.close(fig)
    print("wrote comparison.json, comparison.md and the figures to", res)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("verify"); s.add_argument("--out", type=Path, default=RES / "verify.json")
    s = sub.add_parser("report"); s.add_argument("--res", type=Path, default=RES)
    s = sub.add_parser("equiv"); s.add_argument("--work", type=Path, required=True); s.add_argument("--out", type=Path, required=True)
    s.add_argument("--yosys", default="yosys"); s.add_argument("--timeout", type=int, default=900); s.add_argument("--ids", nargs="*")
    s = sub.add_parser("export")
    s.add_argument("--part", default="xc7a35tcpg236-1"); s.add_argument("--clock", type=float); s.add_argument("--work", type=Path, required=True)
    s.add_argument("--threads", type=int, default=2); s.add_argument("--ids", nargs="*")
    s = sub.add_parser("collect")
    s.add_argument("--part", default="xc7a35tcpg236-1"); s.add_argument("--clock", type=float); s.add_argument("--work", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True); s.add_argument("--vivado", default="2026.1"); s.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "verify":
        return verify(a.out)
    if a.cmd == "equiv":
        return equiv(a.work, a.out, a.yosys, a.timeout, a.ids)
    if a.cmd == "report":
        return report(a.res)
    clock = a.clock or PARTS[a.part]["clock"]
    if a.cmd == "export":
        export(a.part, clock, a.work, a.threads, a.ids)
    elif a.cmd == "collect":
        collect(a.part, a.work, a.out, clock, a.vivado, a.threads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
