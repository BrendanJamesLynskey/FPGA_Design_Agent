#!/usr/bin/env python3
"""Time and what-it-catches of each verification method on the development design (brief 194, docs/assurance.md).

    python3 -m flow.assurance_profiles rtl      lint, directed simulation, seed sweep and bounded formal against the RTL mutants (no Vivado)
Results go to results/b194/methods_rtl.json. Wall times are this PC's, one run each, not a benchmark.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "designs" / "b194_assurance"
sys.path.insert(0, str(D / "tests"))
from mutants import MUTANTS  # noqa: E402

OSS = Path(os.environ.get("FDA_OSS_CAD", Path.home() / ".local/opt/oss-cad-suite"))
FILES = ("a194_secded.sv", "a194_fifo.sv", "a194_ctrl.sv", "a194_core.sv")


def tool(name: str) -> str:
    return str(OSS / "bin" / name) if (OSS / "bin" / name).exists() else (shutil.which(name) or name)


def mutate(dst: Path, mid: str | None) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copy(D / "rtl" / f, dst / f)
    if mid:
        m = next(x for x in MUTANTS if x[0] == mid)
        p = dst / m[1]
        t = p.read_text()
        assert m[2] in t, f"{mid}: the text to mutate is not in {m[1]}"
        p.write_text(t.replace(m[2], m[3], 1))


def sim(rtl: Path, seed: int, bursts: int = 40, params: str = "") -> tuple[bool, float, str]:
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        exe = Path(td) / "s.out"
        c = subprocess.run(["iverilog", "-g2012", "-o", str(exe), *([f"-DDUT_PARAMS={params}"] if params else []), *[str(rtl / f) for f in FILES], str(D / "tb" / "tb_func.sv")],
                           capture_output=True, text=True)
        if c.returncode:
            return False, time.time() - t0, "compile: " + c.stderr[-200:]
        r = subprocess.run(["vvp", str(exe), f"+seed={seed}", f"+bursts={bursts}"], capture_output=True, text=True)
    ok = "TB PASS" in r.stdout
    return ok, time.time() - t0, "" if ok else next((l for l in r.stdout.splitlines() if "FAIL" in l), "no PASS line")[:160]


def lint(rtl: Path) -> tuple[bool, float, str]:
    t0 = time.time()
    r = subprocess.run([tool("verilator"), "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL", "-Wno-UNUSEDPARAM", "-Wno-PINCONNECTEMPTY", "--top-module", "a194_core",
                        *[str(rtl / f) for f in FILES]], capture_output=True, text=True)
    errs = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith("%Error")]
    return not errs, time.time() - t0, errs[0][:160] if errs else ""


FORMAL = """\
[tasks]
bmc
[options]
bmc: mode bmc
bmc: depth {depth}
[engines]
smtbmc z3
[script]
read_verilog -formal -sv a194_ctrl.sv
read_verilog -formal -sv f_ctrl.sv
prep -top f_ctrl
[files]
{ctrl}
f_ctrl.sv
"""

F_CTRL = """\
// f_ctrl.sv: properties of a194_ctrl (brief 194). Inputs are free. rem_v is the remaining count; the properties are the ones the bench relies on.
module f_ctrl (input logic clk, input logic start, input logic [15:0] len, input logic progress, input logic accept, input logic drained);
    logic rst, run, busy, done, fsm_fault, wd_fault, tmr_fault;
    logic [2:0] st;
    reg init = 1'b1;
    always @(posedge clk) init <= 1'b0;
    always_comb if (init) assume (rst);
    a194_ctrl #(.SAFE(0), .TMR(0), .WD(0)) dut (.*, .state_o(st));
    // the sequencer never accepts a word it has no count for; done only from the DONE state; busy is not-idle; len = 0 completes without words
    always_comb if (!init) begin
        assert (!(run && st != 3'd1));
        assert (done == (st == 3'd3));
        assert (busy == (st != 3'd0));
        assert (st <= 3'd3);
    end
    reg [2:0] prev_state;
    reg prev_start, prev_rst, prev_drained;
    reg [15:0] prev_len;
    always @(posedge clk) begin prev_state <= st; prev_start <= start; prev_len <= len; prev_rst <= rst; prev_drained <= drained; end
    always_comb if (!init && !prev_rst && prev_state == 3'd0 && prev_start && prev_len == 16'd0) assert (st == 3'd3);
    always_comb if (!init && !prev_rst && prev_state == 3'd0 && prev_start && prev_len != 16'd0) assert (st == 3'd1);
    always_comb if (!init && !prev_rst && prev_state == 3'd0 && prev_start && prev_len == 16'd1) assert (run);
    always_comb if (!init && !prev_rst && prev_state == 3'd2 && !prev_drained) assert (st == 3'd2);
endmodule
"""


def formal(rtl: Path, depth: int) -> tuple[bool, float, str]:
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shutil.copy(rtl / "a194_ctrl.sv", td / "a194_ctrl.sv")
        (td / "f_ctrl.sv").write_text(F_CTRL)
        (td / "f.sby").write_text(FORMAL.format(depth=depth, ctrl="a194_ctrl.sv"))
        env = {**os.environ, "PATH": f"{OSS / 'bin'}:{os.environ['PATH']}"}
        r = subprocess.run([tool("sby"), "-f", "-d", str(td / "w"), str(td / "f.sby")], capture_output=True, text=True, env=env, cwd=td)
        out = r.stdout + r.stderr
        ok = "DONE (PASS" in out
        msg = "" if ok else next((l for l in out.splitlines() if "FAIL" in l or "ERROR" in l or "Assert failed" in l), "no PASS line")[:200]
    return ok, time.time() - t0, msg


def rtl_methods(seeds: int, depth: int) -> dict:
    res: dict = {"seeds": seeds, "formal_depth": depth, "methods": {}, "mutants": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        base = td / "base"
        mutate(base, None)
        # the unmutated design must pass everything (otherwise a "catch" means nothing)
        res["baseline"] = {"lint": lint(base)[0], "directed": sim(base, 1)[0], "seed_sweep": all(sim(base, s)[0] for s in range(1, seeds + 1)), "formal": formal(base, depth)[0]}
        if not all(res["baseline"].values()):
            raise SystemExit(f"the baseline fails a method: {res['baseline']}")
        times = {"lint": [], "directed": [], "seed_one": [], "formal_1x": [], "formal_4x": []}
        for mid, _f, _o, _n, what in MUTANTS:
            m = td / mid
            mutate(m, mid)
            row = {"what": what}
            ok, t, msg = lint(m); row["lint"] = {"caught": not ok, "s": round(t, 2)}; times["lint"].append(t)
            ok, t, msg = sim(m, 1); row["directed_seed1"] = {"caught": not ok, "s": round(t, 2), "why": msg}; times["directed"].append(t)
            caught_seeds = []
            t0 = time.time()
            for s in range(1, seeds + 1):
                ok, t, msg = sim(m, s)
                if not ok:
                    caught_seeds.append(s)
            row["seed_sweep"] = {"caught": bool(caught_seeds), "seeds_that_catch": caught_seeds, "s": round(time.time() - t0, 2)}
            ok, t, msg = formal(m, depth); row["formal_1x"] = {"caught": not ok, "s": round(t, 2), "why": msg}; times["formal_1x"].append(t)
            ok, t, msg = formal(m, depth * 4); row["formal_4x"] = {"caught": not ok, "s": round(t, 2), "why": msg}; times["formal_4x"].append(t)
            res["mutants"][mid] = row
            print(mid, {k: (v["caught"] if isinstance(v, dict) else v) for k, v in row.items() if k != "what"}, flush=True)
        # method wall times on the unmutated design (what a passing run costs)
        res["mutation_sweep_s"] = round(sum(r["directed_seed1"]["s"] for r in res["mutants"].values()), 2)
        res["methods"] = {"lint_s": round(lint(base)[1], 2), "directed_one_seed_s": round(sim(base, 1)[1], 2),
                          "seed_sweep_s": round(sum(sim(base, s)[1] for s in range(1, seeds + 1)), 2),
                          "formal_1x_s": round(formal(base, depth)[1], 2), "formal_4x_s": round(formal(base, depth * 4)[1], 2)}
    return res


from flow.assurance import xsim_settings  # noqa: E402

XSET = xsim_settings()


def netsim(netlist: Path, seed: int, workdir: Path, timesim: bool = False, sdf: Path | None = None, bursts: int = 40) -> tuple[bool, float, str]:
    """The functional bench (tb/tb_func.sv, ports only) on a Vivado netlist in xsim: a post-synthesis funcsim netlist (unisims) or a post-route
    timesim netlist (simprims, with the SDF)."""
    t0 = time.time()
    workdir.mkdir(parents=True, exist_ok=True)
    lib = "simprims_ver" if timesim else "unisims_ver"
    extra = f" -sdfmax /tb_func/dut={sdf}" if (timesim and sdf) else ""
    sh = (f"source {XSET} >/dev/null 2>&1; cd {workdir}; rm -rf xsim.dir; xvlog -sv {netlist} {D / 'tb' / 'tb_func.sv'} >/dev/null 2>&1; "
          f"xvlog $XILINX_VIVADO/data/verilog/src/glbl.v >/dev/null; xelab -L {lib} tb_func glbl -s s{extra} -timescale 1ns/1ps >/dev/null 2>xelab.err; "
          f"xsim s -R -testplusarg seed={seed} -testplusarg bursts={bursts}")
    r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True)
    out = r.stdout + r.stderr
    ok = "TB PASS" in out
    if not ok:
        why = next((l for l in out.splitlines() if "FAIL" in l or "ERROR" in l), None) or ((workdir / "xelab.err").read_text()[-200:] if (workdir / "xelab.err").exists() else "no PASS line")
    return ok, time.time() - t0, "" if ok else why[:200]


def netlist_methods(cost_dir: Path, seeds: int) -> dict:
    """Run on the netlists flow.assurance cost wrote: funcsim simulation, eqy, planted netlist faults, timesim."""
    from flow import eqy_gate
    res: dict = {"netlists": {}}
    with tempfile.TemporaryDirectory(prefix="b194n_") as td:
        td = Path(td)
        for name in ("u", "all", "ecc_prim"):
            nl = cost_dir / name / "synth_funcsim.v"
            if nl.exists():
                ok, t, why = netsim(nl, 1, td / f"sim_{name}")
                res["netlists"][name] = {"funcsim_pass": ok, "funcsim_s": round(t, 1), "why": why}
        # a seed sweep on the netlist of the plain design: what it costs
        nl = cost_dir / "u" / "synth_funcsim.v"
        if nl.exists():
            t0 = time.time()
            res["netlist_seed_sweep"] = {"seeds": seeds, "all_pass": all(netsim(nl, s, td / "sweep")[0] for s in range(1, seeds + 1)), "s": round(time.time() - t0, 1)}
        # eqy: the whole core (a block RAM inside) and the RAM-free control module
        ctrl_rtl = [str(D / "rtl" / "a194_ctrl.sv")]
        for name, top, gold in (("u", "a194_core", [str(D / "rtl" / f) for f in FILES]), ("ctrl_u", "a194_ctrl", ctrl_rtl), ("ctrl_all", "a194_ctrl", ctrl_rtl)):
            nl = cost_dir / name / "synth_funcsim.v"
            if not nl.exists():
                continue
            t0 = time.time()
            r = eqy_gate.check(top, gold, str(nl), td / f"eqy_{name}", strategy="auto", timeout=1500)
            res["netlists"].setdefault(name, {})["eqy"] = {"status": r.status, "strategy": r.strategy, "s": round(time.time() - t0, 1), "message": r.message[:200]}
            print("eqy", name, r.status, r.message[:100], flush=True)
        # planted netlist faults: does eqy catch them (control module), and does the bench catch them (core netlist)?
        planted = []
        for kind, which in (("lut_init", 0), ("lut_init", 3), ("swap_regs", 0), ("reset_drop", 0), ("reset_drop", 2)):
            row = {"kind": kind, "which": which}
            nl = cost_dir / "ctrl_u" / "synth_funcsim.v"
            if nl.exists():
                try:
                    txt, desc = eqy_gate.plant(nl.read_text(), kind, which)
                    p = td / f"p_ctrl_{kind}{which}.v"
                    p.write_text(txt)
                    r = eqy_gate.check("a194_ctrl", ctrl_rtl, str(p), td / f"eqyp_{kind}{which}", strategy="auto", timeout=1500)
                    row.update(what=desc, eqy=r.status)
                except Exception as e:      # noqa: BLE001
                    row.update(eqy=f"not planted: {e}")
            nl = cost_dir / "u" / "synth_funcsim.v"
            if nl.exists():
                try:
                    txt, desc = eqy_gate.plant(nl.read_text(), kind, which)
                    p = td / f"p_core_{kind}{which}.v"
                    p.write_text(txt)
                    ok, t, why = netsim(p, 1, td / f"simp_{kind}{which}")
                    row.update(core_what=desc, bench_caught=not ok, bench_s=round(t, 1), bench_why=why)
                except Exception as e:      # noqa: BLE001
                    row.update(bench_caught=f"not planted: {e}")
            planted.append(row)
            print("planted", row, flush=True)
        res["planted"] = planted
        # timing simulation of the plain design, after routing
        tn = cost_dir / "u" / "route_timesim.v"
        if tn.exists():
            ok, t, why = netsim(tn, 1, td / "timesim", timesim=True, sdf=cost_dir / "u" / "route.sdf", bursts=10)
            res["timesim_u"] = {"pass": ok, "s": round(t, 1), "why": why, "bursts": 10}
    return res


def profile_times() -> dict:
    """results/b194/profile_times.json: each profile's checks and their summed wall time, from the measurement records. A method that no record
    measured is left out of the sum and listed under ``not_measured`` for the profile."""
    R = ROOT / "results" / "b194"
    rtl = json.loads((R / "methods_rtl.json").read_text())
    nl = json.loads((R / "methods_netlist.json").read_text()) if (R / "methods_netlist.json").exists() else {}
    cost = json.loads((R / "costs.json").read_text()) if (R / "costs.json").exists() else {}
    fl = json.loads((R / "faults.json").read_text()) if (R / "faults.json").exists() else {}
    m = rtl["methods"]
    per_seed = m["seed_sweep_s"] / rtl["seeds"]
    u = (cost.get("variants") or {}).get("u", {})
    n_u = (nl.get("netlists") or {}).get("u", {})
    eqy = ((nl.get("netlists") or {}).get("ctrl_u") or {}).get("eqy", {})
    methods = {
        "lint": (m["lint_s"], "methods_rtl.json: Verilator lint of the RTL"),
        "directed tests, 1 seed": (m["directed_one_seed_s"], "methods_rtl.json: tb_func, 40 bursts, Icarus"),
        "random tests, 3 seeds": (3 * per_seed, "methods_rtl.json: 3 x the per-seed time"),
        "random tests, 8 seeds": (8 * per_seed, "methods_rtl.json: 8 seeds"),
        "bounded formal, design's own depth": (m["formal_1x_s"], "methods_rtl.json: SymbiYosys, depth 20, z3"),
        "bounded formal, depth x4": (m["formal_4x_s"], "methods_rtl.json: depth 80"),
        "mutation sweep (7 mutants, 1 seed each)": (rtl.get("mutation_sweep_s") or round(sum(r["directed_seed1"]["s"] for r in rtl["mutants"].values()), 2), "methods_rtl.json: stand-in for the agent's mutation run"),
    }
    if u and n_u:
        methods["post-synthesis netlist: synthesis"] = (float(u["synth_s"]), "costs.json: Vivado out-of-context synthesis, u")
        methods["post-synthesis netlist: simulation"] = (n_u["funcsim_s"], "methods_netlist.json: tb_func on the funcsim netlist, xsim")
    if eqy:
        methods["equivalence (eqy, control module)"] = (eqy["s"], "methods_netlist.json: eqy_gate auto, " + eqy["status"])
    if fl:
        tot = sum(t["wall_s"] for t in fl["variants"]["all"]["targets"].values())
        methods["fault injection (variant all, 6 targets x %d trials)" % fl["trials"]] = (tot, "faults.json: xsim")
    if nl.get("timesim_u") and u:
        methods["timing simulation (opt-in)"] = (float(u["impl_s"]) + nl["timesim_u"]["s"], "costs.json impl_s + methods_netlist.json timesim_u (10 bursts)")
    def prof(names):
        got = [n for n in names if n in methods]
        return {"checks": got, "not_measured": [n for n in names if n not in methods], "seconds": round(sum(methods[n][0] for n in got), 1)}
    net = ["post-synthesis netlist: synthesis", "post-synthesis netlist: simulation", "equivalence (eqy, control module)"]
    std = ["lint", "directed tests, 1 seed", "random tests, 3 seeds", "bounded formal, design's own depth", "mutation sweep (7 mutants, 1 seed each)"]
    thorough = ["lint", "directed tests, 1 seed", "random tests, 8 seeds", "bounded formal, depth x4", "mutation sweep (7 mutants, 1 seed each)", *net]
    fi = [k for k in methods if k.startswith("fault injection")]
    profiles = {"prototype": prof(["lint", "directed tests, 1 seed"]), "standard": prof(std), "thorough": prof(thorough), "ip_release": prof(thorough),
                "high_dependability": prof([*thorough, *fi]), "low_latency": prof(std)}
    profiles["ip_release"]["note"] = "the independent spec bench, k-induction, PDR and the pyuvm bench are not measured on this design (model time or no tool), so ip_release shows the thorough figure"
    profiles["low_latency"]["note"] = "the latency budget checks are not run by the flow yet, so low_latency shows the standard figure"
    return {"methods": {k: {"s": round(v[0], 2), "source": v[1]} for k, v in methods.items()}, "profiles": profiles}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rtl")
    r.add_argument("--seeds", type=int, default=8)
    r.add_argument("--depth", type=int, default=20)
    r.add_argument("--out", type=Path, default=ROOT / "results" / "b194" / "methods_rtl.json")
    n = sub.add_parser("netlist")
    n.add_argument("--cost-dir", type=Path, default=ROOT / "build" / "b194" / "cost")
    n.add_argument("--seeds", type=int, default=8)
    n.add_argument("--out", type=Path, default=ROOT / "results" / "b194" / "methods_netlist.json")
    sub.add_parser("times", help="write results/b194/profile_times.json from the measurement records")
    a = ap.parse_args(argv)
    if a.cmd == "times":
        (ROOT / "results" / "b194" / "profile_times.json").write_text(json.dumps(profile_times(), indent=1) + "\n")
        return 0
    if a.cmd == "netlist":
        res = netlist_methods(a.cost_dir, a.seeds)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1) + "\n")
        return 0
    if a.cmd == "rtl":
        res = rtl_methods(a.seeds, a.depth)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps(res["methods"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
