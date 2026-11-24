#!/usr/bin/env python3
"""measure.py (brief 141): runs tb/tb_ddr2.sv (Icarus Verilog) for ddr2_sched at a policy, an address map, a traffic pattern and a timing profile, and reduces the output to numbers:
read latency distribution (clocks from the request accepted to the first data beat, and nanoseconds at the profile's clock), data-bus utilisation and bandwidth, row-hit rate, the longest wait of any request,
and the violation counts of the DDR2 model. Every run uses a fixed seed and is repeatable.

    python3 designs/m141_ddr2_sched/tests/m141_measure.py --json results/b141/sim_summary.json [--quick]

Data-bus utilisation = column commands x (BL/2) / elapsed clocks: 1.0 means a data burst on every clock of the bus; bandwidth = utilisation x peak (2 data bytes per beat, 2 beats per clock).
Row-hit rate = 1 - ACTIVATEs / column commands (negative when rows were opened and closed again before use). The saturated bandwidth runs use REF_POST 0 for both policies so a refresh postponed past the end of a short run does not flatter one of them.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE.parent
sys.path.insert(0, str(HERE))
import m141_timing as timing  # noqa: E402

_BUILT: dict[tuple, Path] = {}


def build(out: Path, profile: str, policy: int, mp: int, refpost: int, extra: dict | None = None, rtl_dir: Path | None = None) -> Path:
    key = (profile, policy, mp, refpost, tuple(sorted((extra or {}).items())), str(rtl_dir))
    if key in _BUILT and _BUILT[key].exists():
        return _BUILT[key]
    rd = rtl_dir or (D / "rtl")
    binp = out / f"sim_{len(_BUILT)}"
    cmd = ["iverilog", "-g2012", *timing.plusP(profile), f"-Ptb_ddr2.POLICY={policy}", f"-Ptb_ddr2.MAP={mp}", f"-Ptb_ddr2.REF_POST={refpost}"]
    for k, v in (extra or {}).items():
        cmd.append(f"-Ptb_ddr2.{k}={v}")
    cmd += ["-o", str(binp), str(D / "tb" / "tb_ddr2.sv"), str(rd / "ddr2_sched.sv"), str(rd / "ddr2_addrmap.sv")]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    _BUILT[key] = binp
    return binp


def pct(xs: list[int], p: float) -> int:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))] if s else 0


def run(out: Path, profile: str, policy: int, pat: int, gap: int, n: int, mp: int = 0, refpost: int | None = None, defer: int = 0, seed: int | None = None, extra: dict | None = None,
        rtl_dir: Path | None = None, defer_p: int = 0, defer_w: int = 0) -> dict:
    if refpost is None:
        refpost = 4 if policy == 0 else 0
    binp = build(out, profile, policy, mp, refpost, extra, rtl_dir)
    args = ["vvp", "-n", str(binp), f"+PAT={pat}", f"+GAP={gap}", f"+N={n}", f"+DEFER={defer}", f"+DEFERP={defer_p}", f"+DEFERW={defer_w}"]
    if seed is not None:
        args.append(f"+SEED={seed}")
    r = subprocess.run(args, capture_output=True, text=True, timeout=3 * 3600)
    text = r.stdout
    m = re.search(r"RESULT (.*)", text)
    res: dict = {"profile": profile, "pass": "PASS" in text.split("RESULT")[-1], "viol_lines": re.findall(r"VIOL .*", text)[:5]}
    if not m:
        res["error"] = (text + r.stderr)[-400:]
        res["pass"] = False
        return res
    kv = {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", m.group(1))}
    pairs = [(int(a), int(b)) for a, b in re.findall(r"^LAT (\d+) (\d+)", text, re.M)]
    lat = [a for a, _ in pairs]
    p = timing.params(profile)
    tck_ns = p["TCK_PS"] / 1000.0
    col = kv["reads"] + kv["writes"]
    peak = 4.0 / tck_ns            # bytes per ns = GB/s: 2 bytes x 2 beats per clock
    util = col * p["BL2"] / kv["clocks"]
    res.update(dict(policy=policy, map=mp, pat=pat, gap=gap, n=n, refpost=refpost, defer=defer, clocks=kv["clocks"], reads=kv["reads"], writes=kv["writes"], act=kv["act"], pre=kv["pre"], prea=kv["prea"], ref=kv["ref"],
                    violations=kv["violations"], hazards=kv["hazards"], badreq=kv["badreq"], wait_max=kv["wait_max"], max_ref_gap=kv["max_ref_gap"], turnarounds=kv.get("turn", 0), util=round(util, 4), gbps=round(util * peak, 3),
                    peak_gbps=round(peak, 3), row_hit=round(1 - kv["act"] / col, 4) if col else 0.0))
    if defer_p:
        for tag, sel in (("win", [a for a, b in pairs if b]), ("out", [a for a, b in pairs if not b])):
            if sel:
                res[f"lat_clk_{tag}"] = dict(n=len(sel), mean=round(sum(sel) / len(sel), 2), p50=pct(sel, 50), p90=pct(sel, 90), p99=pct(sel, 99), p999=pct(sel, 99.9), max=max(sel))
                res[f"lat_ns_{tag}"] = {k: round(v * tck_ns, 1) for k, v in res[f"lat_clk_{tag}"].items() if k != "n"}
    if lat:
        res["lat_clk"] = dict(n=len(lat), mean=round(sum(lat) / len(lat), 2), p50=pct(lat, 50), p90=pct(lat, 90), p99=pct(lat, 99), p999=pct(lat, 99.9), max=max(lat))
        res["lat_ns"] = {k: round(v * tck_ns, 1) for k, v in res["lat_clk"].items() if k != "n"}
    return res


def experiments(quick: bool) -> list[tuple[str, dict]]:
    n_lat = 400 if quick else 3000
    n_bw = 600 if quick else 4000
    nb = "nexys_650"
    ex: list[tuple[str, dict]] = []
    for pol in (0, 1):
        ex.append((f"lat_rand_read_p{pol}", dict(profile=nb, policy=pol, pat=0, gap=40, n=n_lat)))
        ex.append((f"lat_rand_mix_p{pol}", dict(profile=nb, policy=pol, pat=1, gap=40, n=n_lat)))
        ex.append((f"lat_bursts_p{pol}", dict(profile=nb, policy=pol, pat=4, gap=40, n=n_lat)))
        ex.append((f"lat_rand_loaded_p{pol}", dict(profile=nb, policy=pol, pat=0, gap=8, n=n_lat)))
        for mp in (0, 1, 2):
            ex.append((f"bw_seq_read_map{mp}_p{pol}", dict(profile=nb, policy=pol, pat=2, gap=0, n=n_bw, mp=mp, refpost=0)))
            ex.append((f"bw_copy_map{mp}_p{pol}", dict(profile=nb, policy=pol, pat=3, gap=0, n=n_bw, mp=mp, refpost=0)))
        ex.append((f"bw_rand_read_sat_p{pol}", dict(profile=nb, policy=pol, pat=0, gap=0, n=n_bw, refpost=0)))
        ex.append((f"bw_rand_mix_sat_p{pol}", dict(profile=nb, policy=pol, pat=1, gap=0, n=n_bw, refpost=0)))
        ex.append((f"hazard_stress_p{pol}", dict(profile=nb, policy=pol, pat=5, gap=0, n=n_bw, refpost=0)))
        ex.append((f"xcheck_ddr2_800_p{pol}", dict(profile="ddr2_800", policy=pol, pat=1, gap=20, n=n_lat)))
    if not quick:
        for pol in (0, 1):
            for qd in (8, 16, 32):
                ex.append((f"qd_sweep_copy_p{pol}_qd{qd}", dict(profile=nb, policy=pol, pat=3, gap=0, n=2500, extra=dict(QD=qd), refpost=0)))
        for age in (64, 256, 1024):
            ex.append((f"age_sweep_copy_p1_age{age}", dict(profile=nb, policy=1, pat=3, gap=0, n=2500, extra=dict(AGE_LIM=age), refpost=0)))
    for rp, df in ((0, 0), (4, 0), (4, 1)):
        ex.append((f"refresh_rand_read_p0_post{rp}_defer{df}", dict(profile=nb, policy=0, pat=0, gap=40, n=n_lat * 2, refpost=rp, defer=df)))
    # a latency-critical window: ref_defer high for 5000 clocks of every 12000 (about two refresh intervals in every five)
    for rp in (0, 4):
        ex.append((f"refresh_window_p0_post{rp}", dict(profile=nb, policy=0, pat=0, gap=40, n=n_lat * 2, refpost=rp, defer_p=12000, defer_w=5000)))
    return ex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--merge", action="store_true", help="add or replace the runs selected by --only in an existing results file")
    a = ap.parse_args()
    out = Path(tempfile.mkdtemp(prefix="m141_sim_"))
    res = {}
    old = {}
    if a.merge and Path(a.json).exists():
        old = json.loads(Path(a.json).read_text())
        res = dict(old.get("runs", {}))
    for name, kw in experiments(a.quick):
        if a.only and a.only not in name:
            continue
        res[name] = run(out, **kw)
        r = res[name]
        print(name, "PASS" if r.get("pass") else "FAIL", r.get("lat_clk", {}).get("p50"), r.get("util"), flush=True)
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps({"profile_params": {k: timing.params(k) for k in timing.PROFILES}, "clock_mhz": {k: round(1.0e6 / timing.PROFILES[k]["TCK_PS"]) for k in timing.PROFILES}, "seed": "tb default (xorshift32 2545F491)", "runs": res}, indent=1) + "\n")
    return 0 if all(r.get("pass") for r in res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
