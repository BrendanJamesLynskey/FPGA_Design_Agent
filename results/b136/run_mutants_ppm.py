#!/usr/bin/env python3
"""Brief 136, scenario 1: seeded bugs of rate_match_gp.sv (brief 115's mutants plus three added here) against the ppm points.

For every mutant: a throw-away copy of rtl/rate_match_gp.sv with one regex substitution (as verif/formal/run_formal.py does; the RTL in the tree is never edited), built with the
cocotb bench of brief 96E, run at 0, +100, -100, +300 and -300 ppm. Writes results/b136/mutants_ppm.json.

    python3 results/b136/run_mutants_ppm.py [--frames N] [--only NAME ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DESIGN = ROOT / "designs" / "b96_kr260_10g"
RTL = DESIGN / "rtl"
HERE = DESIGN / "tests"
sys.path.insert(0, str(ROOT / "designs" / "b96_kr260_10g" / "verif" / "formal"))
import run_formal as rf  # noqa: E402  (brief 115's mutant table)
from flow import cocotb_run  # noqa: E402

# mutants brief 115 defined, that a simulation can run (mut_binary_pointer needs the FV_BIN_CROSSING define of the formal harness: not simulated)
FROM_115 = ["mut_overflow", "mut_underflow", "mut_gray_step", "mut_unsynced_pointer", "mut_wrong_entry", "mut_insert_in_frame", "mut_delete_in_frame", "mut_delete_any", "mut_no_pop"]
# added in brief 136: bugs whose effect depends on how fast the buffer fills or drains, so on the ppm
ADDED = [
    ("mut_no_delete", r"assign do_del = !rrst && can_read && lock_s && !slot && \(fill > CW'\(HI\)\) && !in_frame && keep_ok && head_idle;",
     "assign do_del = 1'b0;", "idles are never deleted: a faster partner fills the buffer until it overflows"),
    ("mut_delete_late", r"\(fill > CW'\(HI\)\) && !in_frame", "(fill > CW'(14)) && !in_frame",
     "idles are deleted only when 14 blocks are waiting (a wrong threshold): little margin before the 16-block buffer is full"),
    ("mut_no_stall", r"end else n_stall <= n_stall \+ 32'd1;", "end else begin r_v <= 1'b1; r_d <= 64'h0707070707070707; r_c <= 8'hFF; n_stall <= n_stall + 32'd1; end",
     "when the buffer is empty inside a frame the reader outputs an idle block instead of waiting (a slower partner then cuts frames)"),
]


def mutants() -> list[tuple[str, str, str, str]]:
    out = []
    by = {m[0]: m for m in rf.MUTANTS}
    for n in FROM_115:
        m = by[n]
        out.append((n, m[1], m[2], "brief 115: " + m[8]))
    for n, pat, rep, why in ADDED:
        out.append((n, pat, rep, "brief 136 (added): " + why))
    return out


def run_one(name: str, pat: str | None, rep: str | None, frames: int, workdir: Path) -> dict:
    src = (RTL / "rate_match_gp.sv").read_text()
    if pat:
        new, n = re.subn(pat, rep, src)
        if n != 1:
            return {"name": name, "status": "BAD_MUTANT", "detail": f"pattern matched {n} times"}
    else:
        new = src
    d = workdir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "rate_match_gp.sv").write_text(new)
    out = d / "out.json"
    out.unlink(missing_ok=True)
    srcs = [RTL / "rate_match.sv", d / "rate_match_gp.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "results" / "b136")]), "B96_RM_IMPL": "gp", "B96_RM_HI": "1",
           "B136_OUT": str(out), "B136_FRAMES": str(frames)}
    t0 = time.time()
    try:
        cocotb_run.run(f"b136_{name}", "tb_rate_match", srcs, "ratematch_whatif_cocotb", HERE, parameters={"IMPL": 1, "HI": 1}, extra_env=env)
        status = "ran"
    except Exception as e:  # a failed cocotb test or a build error: the JSON written so far still counts
        status = f"exception: {type(e).__name__}: {str(e)[:200]}"
    pts = json.loads(out.read_text()) if out.exists() else {}
    log = ROOT / "build" / "sim" / f"b136_{name}" / "sim.log"
    if not pts and log.exists() and log.read_text(errors="replace").count("non-0/1 values") >= 5:
        # every test died on an X or Z at the buffer's output (cocotb cannot read it): the bug corrupts the output at every point, 0 ppm included
        pts = {f"ppm{p:+g}": dict(ppm=p, x_on_output=True, functional_fail=True, twin_mismatch=True) for p in (0, 100, -100, 300, -300)}
        status = "x on output in every test (read from sim.log)"
    return {"name": name, "status": status, "seconds": round(time.time() - t0, 1), "points": pts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=2500)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", default=str(ROOT / "results" / "b136" / "mutants_ppm.json"))
    a = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="b136_mut_"))
    res = []
    for name, pat, rep, why in [("unmutated", None, None, "the RTL as it is (control)")] + mutants():
        if a.only and name not in a.only:
            continue
        r = run_one(name, pat, rep, a.frames, work)
        r["why"] = why
        res.append(r)
        print(name, r["status"], r.get("seconds"), {k: v["functional_fail"] for k, v in r.get("points", {}).items()}, flush=True)
    Path(a.out).write_text(json.dumps({"frames_per_point": a.frames, "points_ppm": [0, 100, -100, 300, -300], "mutants": res}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
