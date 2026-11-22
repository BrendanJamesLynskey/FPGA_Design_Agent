#!/usr/bin/env python3
"""run_formal.py (brief 115): runs the SymbiYosys jobs of rm_gp.sby for rate_match_gp.sv, and the mutants (a seeded bug in a throw-away copy of the RTL that a named assertion must catch).

    python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set ci --json results/b115/formal_ci.json      # proofs and mutants that fit CI
    python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set full --json results/b115/formal_full.json  # adds every bit of the entry and the long runs
    python3 designs/b96_kr260_10g/verif/formal/run_formal.py --only mut_overflow                              # one job

Needs sby and yosys with the slang plugin: the OSS CAD Suite release the repo's CI pins (2026-11-12), found through FDA_OSS_CAD, then PATH, then ~/.local/opt/oss-cad-suite.
The RTL is never edited: a mutant is a regex substitution applied to a copy in a temporary directory; the substitution must change the text (checked), or the run fails.
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
RTL = HERE.parents[1] / "rtl" / "rate_match_gp.sv"
SRC = ["xpm_formal.sv", "rm_gp_props.sv", "rm_gp_bind.sv", "rm_gp_fv_top.sv"]
REP_BITS = [0, 7, 39, 63, 64, 71, 72, 73]   # one per class: data lane 0 (policy bit), lane 4 start byte, a pure data bit, control mask low/high, ordered-set flag, pure-idle flag


def oss_bin() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    w = shutil.which("sby")
    return str(Path(w).parent) if w else ""


# the two deletion mutants can only fire on the one non-slot clock in 33; their copy also gets a pace period of 4 instead of 33 so that the bug is reachable within the bounded check (the proofs of the real RTL keep 33)
SHORT_PACE = [(r"6'd32", "6'd3")]
NEEDS_SHORT_PACE = {"mut_delete_in_frame", "mut_delete_any"}

# a mutant: (name, regex, replacement, extra -D defines, task, KB, AW, assertions of which at least one must fail (prefix match), why)
MUTANTS = [
    ("mut_overflow", r"f_full = \(\(wbin - rbin_w\) & \{CW\{1'b1\}\}\) >= CW'\(DEPTH\)", "f_full = ((wbin - rbin_w) & {CW{1'b1}}) > CW'(DEPTH)", [], "safety_prove", 0, 2, ["p1_no_overflow", "p1b_bound", "p2_wview"], "the writer may write one block too many: it overwrites the oldest unread block"),
    ("mut_underflow", r"assign can_read  = \(fill != '0\);", "assign can_read  = 1'b1;", [], "safety_prove", 0, 2, ["p4_no_underflow"], "the reader reads when nothing has crossed"),
    ("mut_gray_step", r"wbin <= wbin \+ CW'\(1\);", "wbin <= wbin + CW'(2);", [], "safety_prove", 0, 2, ["p5_gray_w", "p1b_bound", "p3_rview"], "the write pointer steps by two: a gray pointer changes two bits"),
    ("mut_binary_pointer", None, None, ["FV_BIN_CROSSING"], "safety_prove", 0, 2, ["p3_rview", "p2_wview", "h5a", "h5b"], "the pointers cross as plain binary: a multi-bit change can be seen torn, the reader's view runs ahead of the writer"),
    ("mut_unsynced_pointer", r"assign fill      = \(wbin_r - rbin\) & \{CW\{1'b1\}\};", "assign fill      = (wbin - rbin) & {CW{1'b1}};", [], "safety_prove", 0, 2, ["p3_rview", "h5a", "p8a_pop_is_written_bit", "h6", "p8b"], "the reader uses the write pointer straight from the write clock instead of the synchronised copy: it can read an entry whose data copy has not arrived (the classic crossing bug)"),
    ("mut_wrong_entry", r"assign head      = ent_r\[rbin\[AW-1:0\]\];", "assign head      = ent_r[rbin[AW-1:0] ^ 1];", [], "safety_prove", 0, 2, ["p8a_pop_is_written_bit", "p8b"], "the reader selects the neighbouring entry: data comes out in the wrong order"),
    ("mut_insert_in_frame", r"end else if \(!in_frame\) begin", "end else if (1'b1) begin", [], "safety_prove", 0, 2, ["p6a_insert_idle_only_between_frames"], "an idle is inserted inside a frame instead of the reader stalling"),
    ("mut_delete_in_frame", r" && !in_frame && keep_ok && head_idle;", " && keep_ok && head_idle;", [], "safety_prove", 0, 2, ["p6b_delete_only_between_frames"], "an idle is deleted inside a frame"),
    ("mut_delete_any", r" && !in_frame && keep_ok && head_idle;", " && !in_frame && keep_ok;", [], "safety_prove", 73, 2, ["p7b_delete_only_flagged"], "any block is deleted, not only a pure idle (checked on the idle flag of the tracked entry, slice 73)"),
    ("mut_no_pop", r"assign slot      = \(pace != 6'd32\);", "assign slot      = 1'b0;", [], "progress_bmc", 0, 2, ["r2_rank_decreases", "r1_rank_bounded"], "the reader never has a slot: nothing is ever popped, a written block waits for ever"),
]

# brief 168, mutants that only exist with MIN_KEEP > 0 (name, regex, replacement, MIN_KEEP, why): each must break p6d_delete_after_min_keep (the deletion rule) or p6e_idle_run_is_the_specs_count (the register that rule reads)
MUTANTS_KEEP = [
    ("mut_keep_ignored", r"assign keep_ok = \(idle_run >= 2'\(MIN_KEEP\)\);", "assign keep_ok = 1'b1;", 2, "the idle-run condition is ignored: a block is deleted straight after a frame"),
    ("mut_keep_off_by_one", r"assign keep_ok = \(idle_run >= 2'\(MIN_KEEP\)\);", "assign keep_ok = (idle_run >= 2'(MIN_KEEP - 1));", 2, "one idle block too few is required before a deletion"),
    ("mut_idle_run_kept", r"idle_run <= head_idle \? \(\(idle_run == 2'd3\) \? 2'd3 : idle_run \+ 2'd1\) : 2'd0;", "idle_run <= head_idle ? ((idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1) : idle_run;", 1, "a block that is not a pure idle does not restart the idle run: the run of the stream before a frame counts again after it"),
    ("mut_idle_run_not_counting_inserted", r"idle_run <= \(idle_run == 2'd3\) \? 2'd3 : idle_run \+ 2'd1;", "idle_run <= idle_run;", 2, "an inserted idle block is not counted as an output idle"),
]


def sby_text(aw: int, kb: int, defines: list[str], depth_bmc: int, depth_prove: int, depth_cover: int, min_keep: int = 0) -> str:
    t = (HERE / "rm_gp.sby").read_text()
    t = re.sub(r"-G AW=\d+", f"-G AW={aw}" + (f" -G MIN_KEEP={min_keep}" if min_keep else ""), t)
    t = re.sub(r"-D FV_KB=\d+", f"-D FV_KB={kb}" + "".join(f" -D {d}" for d in defines), t)
    t = re.sub(r"(?m)^bmc: depth \d+", f"bmc: depth {depth_bmc}", t)
    t = re.sub(r"(?m)^prove: depth \d+", f"prove: depth {depth_prove}", t)
    t = re.sub(r"(?m)^cover: depth \d+", f"cover: depth {depth_cover}", t)
    t = t.replace("../../rtl/rate_match_gp.sv", "rate_match_gp.sv")
    return t


def run_job(name: str, task: str, aw: int, kb: int, defines: list[str], mutate: tuple[str, str] | None, bmc: int, prove: int, cover: int, expect_fail_any: list[str] | None, outroot: Path, bindir: str, min_keep: int = 0) -> dict:
    work = outroot / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in SRC:
        shutil.copy(HERE / f, work / f)
    rtl = RTL.read_text()
    for pat, rep in (mutate or []):
        new, n = re.subn(pat, rep, rtl)
        if n < 1 or new == rtl:
            return {"name": name, "task": task, "status": "BAD_MUTANT", "verdict": "BAD_MUTANT", "detail": f"pattern {pat!r} matched {n} times"}
        rtl = new
    (work / "rate_match_gp.sv").write_text(rtl)
    (work / "rm_gp.sby").write_text(sby_text(aw, kb, defines, bmc, prove, cover, min_keep))
    env = dict(os.environ, PATH=bindir + ":" + os.environ["PATH"])
    t0 = time.time()
    cmd = ["sby", "-f", "-d", "out", "rm_gp.sby", task]
    if shutil.which("systemd-run"):
        cmd = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice", "-n", "10"] + cmd
    r = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=3 * 3600)
    dt = time.time() - t0
    log = (work / "out" / "logfile.txt").read_text() if (work / "out" / "logfile.txt").exists() else r.stdout + r.stderr
    status = (work / "out" / "status").read_text().split()[0] if (work / "out" / "status").exists() else "ABSENT"
    failed = sorted(set(re.findall(r"Assert failed in rm_gp_fv_top: dut\.u_props\.(?:g_\w+\.)?(\w+)", log)))
    res = {"name": name, "task": task, "AW": aw, "MIN_KEEP": min_keep, "KB": kb, "defines": defines, "status": status, "seconds": round(dt, 1), "failed_assertions": failed}
    unreached = sorted(set(re.findall(r"Unreached cover statement at rm_gp_fv_top: dut\.u_props\.(\w+)", log)))
    if task == "cover":
        res["unreached_covers"] = unreached
    if expect_fail_any is not None:
        caught = status == "FAIL" and any(f.startswith(p) for f in failed for p in expect_fail_any)
        res["caught"] = caught
        res["verdict"] = "CAUGHT" if caught else "MISSED"
    else:
        res["verdict"] = "PASS" if status == "PASS" else "FAIL"
    return res


def plan(which: str):
    jobs = []
    # proofs
    for kb in (REP_BITS if which in ("ci", "full") else [0]):
        jobs.append(dict(name=f"safety_prove_aw4_kb{kb}", task="safety_prove", aw=4, kb=kb, bmc=40, prove=8, cover=60))
    jobs.append(dict(name="safety_prove_aw2_kb0", task="safety_prove", aw=2, kb=0, bmc=40, prove=24, cover=60))
    jobs.append(dict(name="safety_prove_aw1_kb0", task="safety_prove", aw=1, kb=0, bmc=40, prove=24, cover=60))
    jobs.append(dict(name="safety_bmc_aw2_kb0", task="safety_bmc", aw=2, kb=0, bmc=40, prove=24, cover=60))
    jobs.append(dict(name="progress_bmc_aw2", task="progress_bmc", aw=2, kb=0, bmc=40, prove=24, cover=60))
    jobs.append(dict(name="cover_aw2", task="cover", aw=2, kb=0, bmc=40, prove=24, cover=60))
    for mk in (1, 2, 3):                                                      # brief 168: the documented MIN_KEEP 1 to 3, which no earlier job instantiated
        jobs.append(dict(name=f"safety_prove_aw2_kb0_mk{mk}", task="safety_prove", aw=2, kb=0, bmc=40, prove=24, cover=60, min_keep=mk))
    jobs.append(dict(name="safety_prove_aw4_kb0_mk2", task="safety_prove", aw=4, kb=0, bmc=40, prove=8, cover=60, min_keep=2))
    if which == "full":
        for kb in range(74):
            if kb not in REP_BITS:
                jobs.append(dict(name=f"safety_prove_aw2_kb{kb}", task="safety_prove", aw=2, kb=kb, bmc=24, prove=12, cover=60))
        jobs.append(dict(name="progress_bmc_aw2_deep", task="progress_bmc", aw=2, kb=0, bmc=70, prove=24, cover=60))
        jobs.append(dict(name="cover_del_aw2", task="cover", aw=2, kb=0, defines=["FV_COVER_DEL"], bmc=40, prove=24, cover=110))
        for mk in (1, 2, 3):
            jobs.append(dict(name=f"cover_del_aw2_mk{mk}", task="cover", aw=2, kb=0, defines=["FV_COVER_DEL"], bmc=40, prove=24, cover=130, min_keep=mk))
    for m in MUTANTS:
        name, pat, rep, defs, task, kb, aw, expect, why = m
        jobs.append(dict(name=name, task=task, aw=aw, kb=kb, defines=defs, mutate=([(pat, rep)] + SHORT_PACE * (name in NEEDS_SHORT_PACE)) if pat else None, bmc=40, prove=32, cover=60, expect_fail_any=expect, why=why))
    for name, pat, rep, mk, why in MUTANTS_KEEP:
        jobs.append(dict(name=name, task="safety_prove", aw=2, kb=0, defines=[], mutate=[(pat, rep)] + SHORT_PACE, bmc=40, prove=32, cover=60, expect_fail_any=["p6d_delete_after_min_keep", "p6e_idle_run_is_the_specs_count"], min_keep=mk, why=why))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["ci", "full"], default="ci")
    ap.add_argument("--only", help="run only the jobs whose name contains this text")
    ap.add_argument("--json", help="write the results here")
    ap.add_argument("--work", help="directory for the runs (default: a temporary one)")
    ap.add_argument("--md", help="also write the results as a markdown table here")
    a = ap.parse_args()
    bindir = oss_bin()
    if not bindir:
        print("sby not found (set FDA_OSS_CAD to the OSS CAD Suite folder)", file=sys.stderr)
        return 2
    outroot = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="rm_gp_formal_"))
    results = []
    bad = 0
    for j in plan(a.set):
        if a.only and a.only not in j["name"]:
            continue
        j.setdefault("defines", [])
        j.setdefault("mutate", None)
        j.setdefault("expect_fail_any", None)
        why = j.pop("why", None)
        res = run_job(j["name"], j["task"], j["aw"], j["kb"], j["defines"], j["mutate"], j["bmc"], j["prove"], j["cover"], j["expect_fail_any"], outroot, bindir, j.get("min_keep", 0))
        if why:
            res["why"] = why
        results.append(res)
        print(f"{res['name']:36s} {res['task']:14s} {res['verdict'] if 'verdict' in res else res['status']:8s} {res.get('seconds', '')}s {res.get('failed_assertions', '')}", flush=True)
        if res.get("verdict") not in ("PASS", "CAUGHT"):
            bad += 1
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"tool": subprocess.run([bindir + "/yosys", "-V"], capture_output=True, text=True).stdout.strip(), "results": results}, indent=1) + "\n")
    if a.md:
        rows = ["| job | task | AW | bit | verdict | seconds | failing assertions |", "|---|---|---|---|---|---|---|"]
        for r in results:
            rows.append(f"| {r['name']} | {r['task']} | {r.get('AW', '')} | {r.get('KB', '')} | {r.get('verdict', r.get('status'))} | {r.get('seconds', '')} | {', '.join(r.get('failed_assertions', []))} |")
        Path(a.md).write_text("\n".join(rows) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
