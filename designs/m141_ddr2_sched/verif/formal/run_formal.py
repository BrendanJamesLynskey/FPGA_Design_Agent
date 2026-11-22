#!/usr/bin/env python3
"""run_formal.py (brief 141): runs the SymbiYosys jobs of ddr2.sby for ddr2_sched.sv, and the mutants (a seeded bug in a throw-away copy of the RTL that a named assertion must catch).

    python3 designs/m141_ddr2_sched/verif/formal/run_formal.py --set ci --json results/b141/formal_ci.json
    python3 designs/m141_ddr2_sched/verif/formal/run_formal.py --set full --json results/b141/formal_full.json
    python3 designs/m141_ddr2_sched/verif/formal/run_formal.py --only mut_tras

Needs sby and yosys with the slang plugin: the OSS CAD Suite release the repo's CI pins (2026-11-12), found through FDA_OSS_CAD, then ~/.local/opt/oss-cad-suite, then PATH.
The RTL is never edited: a mutant is a regex substitution applied to a copy in a temporary directory; the substitution must change the text (checked), or the job fails.
A job is a configuration (the parameters of ddr2_sched), a task (bmc, prove, cover) and, for a mutant, the assertions of which at least one must fail.
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

HERE = Path(__file__).resolve().parent
RTL = HERE.parents[1] / "rtl"
SRC = ["ddr2_props.sv", "ddr2_bind.sv", "ddr2_fv_top.sv"]

# the two configurations. REAL: the MT47H64M16-25 timings at tCK 2.5 ns, eight banks, a small queue and address space (the address bits do not change what a timing rule says).
# TINY: the same logic at small timing values and two banks, so that the bounded-response property, which needs many clocks, is within reach of a bounded check.
REAL = dict(POLICY=0, QD=3, BW=3, RW=2, CB=2, TW=2, AGE_LIM=64, WR_HI=3, WR_LO=1, RUN_MAX=4, REF_POST=4)
TINY = dict(POLICY=0, QD=3, BW=1, RW=2, CB=2, TW=2, T_RCD=2, T_RP=2, T_RPA=3, T_RAS=4, T_RC=6, T_RRD=2, T_FAW=5, T_WR=2, T_WTR=2, T_RTP=2, T_RFC=6, T_REFI=60,
            RL=3, WL=2, BL2=2, AGE_LIM=8, WR_HI=2, WR_LO=1, RUN_MAX=3, REF_POST=1)


def oss_bin() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    w = shutil.which("sby")
    return str(Path(w).parent) if w else ""


def bound(cfg: dict) -> int:
    """The proved response bound, in clocks, from a request entering the queue to its column command (docs/memory_controller_plan.md section 6)."""
    g = lambda k, d: cfg.get(k, d)
    qd, age = g("QD", 8), g("AGE_LIM", 64)
    bl2, rl, wl = g("BL2", 4), g("RL", 6), g("WL", 5)
    rtw = rl + bl2 + 1 - wl
    w2r = wl + bl2 + g("T_WTR", 3)
    w2p = wl + bl2 + g("T_WR", 6)
    pre_wait = max(g("T_RAS", 16), w2p, bl2 - 2 + max(g("T_RTP", 3), 2))
    act_wait = max(g("T_RC", 22), g("T_FAW", 20), g("T_RPA", 7))
    r_max = pre_wait + g("T_RP", 6) + act_wait + g("T_RCD", 6) + max(w2r, rtw, bl2)
    ref_cost = pre_wait + g("T_RPA", 7) + g("T_RFC", 51) + g("T_RPA", 7)
    return age + qd * r_max + ref_cost


TINYR = {**TINY, "REF_POST": 0, "T_RAS": 2, "T_RPA": 2, "T_RP": 2, "T_RC": 4, "T_RFC": 3, "T_WR": 1, "T_REFI": 28}     # a refresh falls due and is forced after 28 clocks (the smallest the elaboration guard allows for these constants), so the refresh mutants are within reach of a bounded check
TINY4 = {**TINY, "BW": 2, "T_FAW": 10}     # four banks and a window long enough that a fifth ACTIVATE can be early

# a mutant: (name, file, regex, replacement, config, task, depth, assertions of which at least one must fail (prefix match), why)
MUTANTS = [
    ("mut_trcd", "ddr2_sched.sv", r"c_col\[d_bank\] <= ld\(c_col\[d_bank\], T_RCD\);", "c_col[d_bank] <= ld(c_col[d_bank], T_RCD - 1);", TINY, "bmc", 25, ["r_col_trcd"], "a column command one clock early after ACTIVATE"),
    ("mut_tras", "ddr2_sched.sv", r"c_pre\[d_bank\] <= ld\(c_pre\[d_bank\], T_RAS\);", "c_pre[d_bank] <= ld(c_pre[d_bank], T_RAS - 1);", TINY, "bmc", 25, ["r_pre_tras", "r_prea_tras"], "PRECHARGE one clock before tRAS"),
    ("mut_trp", "ddr2_sched.sv", r"c_rp\[d_bank\] <= ld\(c_rp\[d_bank\], T_RP\);", "c_rp[d_bank] <= ld(c_rp[d_bank], T_RP - 1);", TINY, "bmc", 25, ["r_act_trp", "r_ref_trp"], "ACTIVATE one clock before tRP after a PRECHARGE"),
    ("mut_trrd", "ddr2_sched.sv", r"c_rrd <= ld\(c_rrd, T_RRD\);", "c_rrd <= ld(c_rrd, T_RRD - 1);", TINY, "bmc", 25, ["r_act_trrd"], "ACTIVATE to another bank one clock before tRRD"),
    ("mut_tfaw", "ddr2_sched.sv", r"c_faw\[faw_z\] <= CNW'\(T_FAW - 1\);", "c_faw[faw_z] <= CNW'(T_FAW - 4);", TINY4, "bmc", 30, ["r_act_tfaw"], "a fifth ACTIVATE inside the four-activate window"),
    ("mut_twr", "ddr2_sched.sv", r"c_pre\[d_bank\] <= ld\(c_pre\[d_bank\], W2P\);", "c_pre[d_bank] <= ld(c_pre[d_bank], W2P - 1);", TINY, "bmc", 30, ["r_pre_twr", "r_prea_twr"], "PRECHARGE before write recovery ends"),
    ("mut_trtp", "ddr2_sched.sv", r"c_pre\[d_bank\] <= ld\(c_pre\[d_bank\], R2P\);", "c_pre[d_bank] <= ld(c_pre[d_bank], R2P - 1);", TINY, "bmc", 30, ["r_pre_trtp", "r_prea_trtp"], "PRECHARGE before the read-to-precharge time"),
    ("mut_twtr", "ddr2_sched.sv", r"c_rd <= ld\(c_rd, W2R\);", "c_rd <= ld(c_rd, W2R - 1);", TINY, "bmc", 30, ["r_rd_twtr"], "a READ one clock before the write-to-read time"),
    ("mut_rtw", "ddr2_sched.sv", r"c_wr <= ld\(c_wr, RTW\);", "c_wr <= ld(c_wr, RTW - 1);", TINY, "bmc", 30, ["r_wr_rtw"], "a WRITE one clock before the read-to-write time"),
    ("mut_trfc", "ddr2_sched.sv", r"c_rfc <= CNW'\(T_RFC - 1\);", "c_rfc <= CNW'(T_RFC - 3);", TINYR, "bmc", 50, ["r_ref_trfc", "r_act_trfc", "r_any_trfc", "r_col_trfc"], "a command before tRFC after REFRESH"),
    ("mut_ref_open", "ddr2_sched.sv", r"end else if \(!any_open && all_rp_ok && \(c_rfc == '0\)\) begin", "end else if (all_rp_ok && (c_rfc == '0)) begin", TINYR, "bmc", 50, ["r_ref_closed"], "REFRESH with a bank still open"),
    ("mut_no_refresh", "ddr2_sched.sv", r"ref_want = \(debt != '0\) && \(\(debt > 4'\(REF_POST\)\) \|\| \(!ref_defer && idle_ok\)\);", "ref_want = 1'b0;", TINYR, "bmc", 95, ["l_debt_bound"], "refresh never requested: the debt grows past the allowance"),
    ("mut_no_dep", "ddr2_sched.sv", r"dep\[free_i\] <= conf;", "dep[free_i] <= '0;", TINY, "bmc", 40, ["o_no_overtake"], "a request does not wait for an older request to the same address"),
    ("mut_no_age", "ddr2_sched.sv", r"\(waitc\[i\] >= WWID'\(AGE_LIM\)\)", "1'b0", TINY, "bmc", 104, ["l_bounded"], "no aging: a request can wait without bound"),
]


def sby_text(cfg: dict, task: str, depth: int, bnd: int, engine: str, skip: str) -> str:
    t = (HERE / "ddr2.sby").read_text()
    gs = " ".join(f"-G {k}={v}" for k, v in cfg.items())
    t = re.sub(r"read_slang --top ddr2_fv_top -G POLICY=0", f"read_slang --top ddr2_fv_top -D FV_BOUND={bnd} " + "".join(f"-D FV_NO_{g} " for g in skip) + gs, t)
    t = re.sub(r"(?m)^bmc: depth \d+", f"bmc: depth {depth}", t)
    t = re.sub(r"(?m)^cover: depth \d+", f"cover: depth {depth}", t)
    if task == "bmc" and engine:
        t = re.sub(r"(?m)^bmc: smtbmc boolector", f"bmc: {engine}", t)
    if task == "prove":
        t = re.sub(r"(?m)^prove: abc pdr", f"prove: {engine}", t)
        if engine.startswith("smtbmc"):
            t = t.replace("prove: mode prove", f"prove: mode prove\nprove: depth {depth}")
    t = t.replace("../../rtl/", "")
    return t


def only_property(text: str, keep: str) -> str:
    """A copy of ddr2_props.sv in which every assertion macro line except the one named `keep` is removed: one proof per rule, each with the smallest cone of influence."""
    out = []
    for line in text.split("\n"):
        m = re.match(r"\s*`FV[RDOB]\((\w+),", line)
        if m and m.group(1) != keep:
            continue
        out.append(line)
    return "\n".join(out)


def run_job(name: str, cfg: dict, task: str, depth: int, engine: str, mutate: tuple[str, str, str] | None, expect_fail_any: list[str] | None, outroot: Path, bindir: str, skip: str = "", timeout: int = 3600,
            only: str | None = None) -> dict:
    work = outroot / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in SRC:
        shutil.copy(HERE / f, work / f)
    if only:
        (work / "ddr2_props.sv").write_text(only_property((HERE / "ddr2_props.sv").read_text(), only))
    for f in ("ddr2_addrmap.sv", "ddr2_sched.sv"):
        shutil.copy(RTL / f, work / f)
    if mutate:
        fn, pat, rep = mutate
        txt = (work / fn).read_text()
        new, n = re.subn(pat, rep, txt)
        if n < 1 or new == txt:
            return {"name": name, "task": task, "status": "BAD_MUTANT", "verdict": "BAD_MUTANT", "detail": f"pattern {pat!r} matched {n} times"}
        (work / fn).write_text(new)
    (work / "ddr2.sby").write_text(sby_text(cfg, task, depth, bound(cfg), engine, skip))
    env = dict(os.environ, PATH=bindir + ":" + os.environ["PATH"])
    t0 = time.time()
    cmd = ["sby", "-f", "-d", "out", "ddr2.sby", task]
    if shutil.which("systemd-run"):
        cmd = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice", "-n", "10"] + cmd
    try:
        r = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"name": name, "task": task, "status": "TIMEOUT", "verdict": "TIMEOUT", "seconds": timeout}
    dt = time.time() - t0
    log = (work / "out" / "logfile.txt").read_text() if (work / "out" / "logfile.txt").exists() else r.stdout + r.stderr
    status = (work / "out" / "status").read_text().split()[0] if (work / "out" / "status").exists() else "ABSENT"
    failed = sorted(set(re.findall(r"Assert failed in ddr2_fv_top: dut\.u_props\.(?:g_\w+(?:\[\d+\])?\.)?(\w+)", log)) | set(re.findall(r"failed assertion ddr2_fv_top\.\\?dut\.u_props\.(?:g_\w+(?:\[\d+\])?\.)?(\w+)", log)))
    res = {"name": name, "only": only, "task": task, "engine": engine if (task == "prove" or (task == "bmc" and engine)) else "smtbmc boolector", "depth": depth, "status": status, "seconds": round(dt, 1), "failed_assertions": failed}
    if task == "cover":
        res["unreached_covers"] = sorted(set(re.findall(r"Unreached cover statement at ddr2_fv_top: dut\.u_props\.(\w+)", log)))
    if expect_fail_any is not None:
        caught = status == "FAIL" and any(f.startswith(p) for f in failed for p in expect_fail_any)
        res["caught"] = caught
        res["verdict"] = "CAUGHT" if caught else "MISSED"
    else:
        res["verdict"] = "PASS" if status == "PASS" else "FAIL"
    return res


RULES = ["r_act_closed", "r_act_trp", "r_act_trc", "r_act_trrd", "r_act_tfaw", "r_act_trfc", "r_col_open", "r_col_trcd", "r_col_trfc", "r_rd_ccd", "r_rd_twtr", "r_wr_ccd", "r_wr_rtw", "r_pre_open",
         "r_pre_tras", "r_pre_trtp", "r_pre_twr", "r_prea_tras", "r_prea_trtp", "r_prea_twr", "r_ref_closed", "r_ref_trp", "r_ref_trfc", "r_any_trfc", "r_op_legal"]


def plan(which: str) -> list[dict]:
    jobs = []
    # the rules, the helper invariants and request order, by k-induction (unbounded: the invariants make the step inductive at depth 3), at the real timing constants and at the small ones, both policies
    for pol in (0, 1):
        jobs.append(dict(name=f"rules_order_real_p{pol}", cfg={**REAL, "POLICY": pol}, task="prove", depth=3, engine="smtbmc boolector", skip="BD"))
        jobs.append(dict(name=f"rules_order_tiny_p{pol}", cfg={**TINY, "POLICY": pol}, task="prove", depth=3, engine="smtbmc boolector", skip="BD"))
        # refresh debt by property-directed reachability: at the small constants, and at the real constants with tREFI at the elaboration guard's minimum (the worst case for the property)
        jobs.append(dict(name=f"debt_tiny_p{pol}", cfg={**TINY, "POLICY": pol}, task="prove", depth=0, engine="abc pdr", skip="RIOB"))
        if which == "full" or pol == 0:
            jobs.append(dict(name=f"debt_real_p{pol}", cfg={**REAL, "POLICY": pol, "T_REFI": 4 * (16 + 7 + 51)}, task="prove", depth=0, engine="abc pdr", skip="RIOB"))
        # bounded response: bounded model check to the bound + 6 clocks, small constants (a bounded check from reset, not a proof for all time)
        if which == "full" or pol == 0:
            jobs.append(dict(name=f"live_bmc_tiny_p{pol}", cfg={**TINY, "POLICY": pol}, task="bmc", depth=bound(TINY) + 6, engine="abc bmc3", skip="RDOI"))
    jobs.append(dict(name="cover_tiny", cfg={**TINY, "POLICY": 0}, task="cover", depth=220, engine="", skip="RIDOB"))
    for m in MUTANTS:
        name, fn, pat, rep, cfg, task, depth, expect, why = m
        jobs.append(dict(name=name, cfg=cfg, task=task, depth=depth, engine="abc bmc3", mutate=(fn, pat, rep), expect_fail_any=expect, why=why, skip="BI" if "l_bounded" not in expect else "RDOI"))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["ci", "full"], default="ci")
    ap.add_argument("--only", help="run only the jobs whose name contains this text")
    ap.add_argument("--json", help="write the results here")
    ap.add_argument("--work", help="directory for the runs (default: a temporary one)")
    a = ap.parse_args()
    bindir = oss_bin()
    if not bindir:
        print("sby not found (set FDA_OSS_CAD to the OSS CAD Suite folder)", file=sys.stderr)
        return 2
    outroot = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="ddr2_formal_"))
    results, bad = [], 0
    for j in plan(a.set):
        if a.only and a.only not in j["name"]:
            continue
        why = j.pop("why", None)
        res = run_job(j["name"], j["cfg"], j["task"], j["depth"], j["engine"], j.get("mutate"), j.get("expect_fail_any"), outroot, bindir, j.get("skip", ""), only=j.get("only"))
        if why:
            res["why"] = why
        results.append(res)
        print(f"{res['name']:28s} {res['task']:6s} {res.get('verdict', res['status']):8s} {res.get('seconds', '')}s {res.get('failed_assertions', '')}", flush=True)
        if res.get("verdict") not in ("PASS", "CAUGHT"):
            bad += 1
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"tool": subprocess.run([bindir + "/yosys", "-V"], capture_output=True, text=True).stdout.strip(), "bounds": {"real": bound(REAL), "tiny": bound(TINY)}, "results": results, "by_name": {r["name"]: r for r in results}}, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
