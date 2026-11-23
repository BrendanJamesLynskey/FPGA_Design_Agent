#!/usr/bin/env python3
"""Assurance checks and cost measurement (brief 194): the netlist-level checks of the `thorough` profile and the area/Fmax cost of the
reliability structures. See docs/assurance.md.

    python3 -m flow.assurance cost --variants u ecc_prim ...   Vivado 2026.1 out-of-context synthesis and routing of the development design
    python3 -m flow.assurance netsim ...                       the functional bench on the post-synthesis netlist (xsim)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "designs" / "b194_assurance"
sys.path.insert(0, str(ROOT))
from flow.ipchar import tcl_list, vivado  # noqa: E402

PART = "xc7a100tcsg324-1"
sys.path.insert(0, str(DESIGN / "tests"))
from run_faults import VARIANTS  # noqa: E402


def sources() -> list[str]:
    return [str(DESIGN / "rtl" / f) for f in ("a194_secded.sv", "a194_fifo.sv", "a194_ctrl.sv", "a194_core.sv")]


def generics(v: tuple) -> list[str]:
    return [f"{k}={x}" for k, x in zip(("ECC", "PAR", "SAFE", "TMR", "WD"), v)]


def cost(names: list[str], work: Path, period: float, impl: bool, mem: str = "4G", extra: list | None = None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    lines = [f"set aj(part) {PART}", "set aj(top) a194_core", f"set aj(period) {period}", "set aj(jobs) {}"]
    for n in names:
        lines.append("lappend aj(jobs) " + tcl_list([n, str(work / n), generics(VARIANTS[n]), sources(), int(impl)]))
    for e in extra or []:       # (name, top, generics, sources): control-only netlists for eqy, synthesis only
        lines.append("lappend aj(jobs) " + tcl_list([e[0], str(work / e[0]), e[2], e[3], 0, e[1]]))
    (work / "jobs.tcl").write_text("\n".join(lines) + "\n")
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"-p", f"MemoryMax={mem}", "nice", "-n", "15", vivado(), "-mode", "batch", "-nojournal",
           "-log", str(work / "vivado.log"), "-source", str(ROOT / "flow" / "assurance_ooc.tcl"), "-tclargs", str(work / "jobs.tcl")]
    t0 = time.time()
    subprocess.run(cmd, cwd=work)
    out = {"wall_s": round(time.time() - t0, 1)}
    for n in [*names, *[e[0] for e in extra or []]]:
        d = work / n / "done.txt"
        out[n] = dict(l.split(" ", 1) for l in d.read_text().splitlines()) if d.exists() else {"ok": "0", "error": "no done.txt"}
    return out


def latency(name: str) -> int:
    """Clocks from the edge that accepts the first word to the first edge with m_axis_tvalid high (tb/tb_lat.sv). ECC = 2 needs xsim (RAMB36E1)."""
    import tempfile
    v = VARIANTS[name]
    params = "#(.ECC(%d),.PAR(%d),.SAFE(%d),.TMR(%d),.WD(%d))" % v
    src = [str(DESIGN / "rtl" / f) for f in ("a194_secded.sv", "a194_fifo.sv", "a194_ctrl.sv", "a194_core.sv")] + [str(DESIGN / "tb" / "tb_lat.sv")]
    with tempfile.TemporaryDirectory() as td:
        if v[0] == 2:
            sh = (f"source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; cd {td}; xvlog -sv {' '.join(src)} -d 'DUT_PARAMS={params}' >/dev/null && "
                  "xvlog $XILINX_VIVADO/data/verilog/src/glbl.v >/dev/null && xelab -L unisims_ver tb_lat glbl -s s >/dev/null 2>&1 && xsim s -R")
            out = subprocess.run(["bash", "-c", sh], capture_output=True, text=True).stdout
        else:
            subprocess.run(["iverilog", "-g2012", "-o", f"{td}/s.out", f"-DDUT_PARAMS={params}", *src], check=True, capture_output=True)
            out = subprocess.run(["vvp", f"{td}/s.out"], capture_output=True, text=True).stdout
    return int(re.search(r"LAT (-?\d+)", out).group(1))


def parse_util(rpt: Path) -> dict:
    t = rpt.read_text()
    def row(label):
        m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*(\d+)\s*\|", t)
        return int(m.group(1)) if m else 0
    return {"lut": row("Slice LUTs") or row("LUT as Logic"), "ff": row("Slice Registers"), "bram36": row("RAMB36/FIFO*") or row("RAMB36/FIFO"), "bram18": row("RAMB18")}


def costs(work: Path) -> dict:
    """costs.json: per variant the routed area, Fmax estimated from WNS at the constraint, latency; per structure the delta against u."""
    res = {"part": PART, "vivado": "2026.1", "period_ns": 5.0, "note": "one out-of-context run per variant, a fixed 5.0 ns clock constraint; Fmax = 1 / (period - WNS) from the routed setup slack at that constraint (an estimate, not a closure search)", "variants": {}, "structures": {}}
    for n in VARIANTS:
        d = work / n
        if not (d / "done.txt").exists():
            continue
        kv = dict(l.split(" ", 1) for l in (d / "done.txt").read_text().splitlines())
        if kv.get("ok") != "1":
            res["variants"][n] = {"error": kv.get("error", "failed")}
            continue
        u = parse_util(d / "util_route.rpt")
        wns = float(kv["wns_route"])
        regs = [l.split()[0] for l in (d / "copies.txt").read_text().splitlines()] if (d / "copies.txt").exists() else []
        copies = {c: sum(1 for r in regs if re.search(rf"g_tmr\.{c}_reg\[", r)) for c in ("ra", "rb", "rc")}
        fsm = sorted(r for r in regs if re.search(r"(sq_reg|FSM_)", r))
        log = (work / "vivado.log").read_text() if (work / "vivado.log").exists() else ""
        res["variants"][n] = {**u, "tmr_copies_after_route": copies if any(copies.values()) or "tmr" in n or n == "all" else None, "state_registers_after_route": len(fsm),
                              "wns_route_ns": wns, "whs_route_ns": float(kv["whs_route"]), "fmax_mhz": round(1000.0 / (5.0 - wns), 1), "latency_clocks": latency(n),
                              "synth_s": int(kv["synth_s"]), "impl_s": int(kv["impl_s"])}
    base = res["variants"].get("u")
    names = {"ecc": "ecc_prim", "ecc_fabric": "ecc_fabric", "parity": "par", "safe_fsm": "safe", "tmr": "tmr", "watchdog": "wd", "all": "all"}
    if base and "lut" in base:
        for k, v in names.items():
            r = res["variants"].get(v)
            if r and "lut" in r:
                res["structures"][k] = {"variant": v, "d_lut": r["lut"] - base["lut"], "d_ff": r["ff"] - base["ff"], "d_bram": (r["bram36"] + r["bram18"] / 2) - (base["bram36"] + base["bram18"] / 2),
                                        "fmax_pct": round(100.0 * (r["fmax_mhz"] / base["fmax_mhz"] - 1), 1), "d_latency": r["latency_clocks"] - base["latency_clocks"]}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cost")
    c.add_argument("--variants", nargs="+", default=list(VARIANTS))
    c.add_argument("--work", type=Path, default=ROOT / "build" / "b194" / "cost")
    c.add_argument("--period", type=float, default=5.0)
    c.add_argument("--synth-only", action="store_true")
    c.add_argument("--ctrl", action="store_true", help="also synthesise the RAM-free control module (plain and SAFE+TMR+WD) for eqy")
    k = sub.add_parser("costs", help="write results/b194/costs.json from a finished cost run")
    k.add_argument("--work", type=Path, default=ROOT / "build" / "b194" / "cost")
    k.add_argument("--out", type=Path, default=ROOT / "results" / "b194" / "costs.json")
    a = ap.parse_args(argv)
    if a.cmd == "costs":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(costs(a.work), indent=1) + "\n")
        return 0
    if a.cmd == "cost":
        ctrl_src = [str(DESIGN / "rtl" / "a194_ctrl.sv")]
        extra = [("ctrl_u", "a194_ctrl", ["SAFE=0", "TMR=0", "WD=0"], ctrl_src), ("ctrl_all", "a194_ctrl", ["SAFE=1", "TMR=1", "WD=1"], ctrl_src)] if a.ctrl else None
        r = cost(a.variants, a.work, a.period, not a.synth_only, extra=extra)
        print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
