#!/usr/bin/env python3
"""Brief 156 part 4: the SystemVerilog twin's formal assertions (t1_gray_stepper ref, `ifdef FORMAL) and the same properties in PSL on the VHDL
translation, in simulation (GHDL -fpsl, NVC --psl, under the cocotb bench) and in formal (SymbiYosys; the SV twin through Yosys's own front end,
the VHDL through the GHDL plugin: Yosys 0.33 + plugin 4.1.0 and Yosys 0.70 + plugin 7.0.0-dev), each on the clean design and on one fault
(the up-count adds 2: it breaks the one-bit-step property).

    python3 results/156_vhdl_tools/psl_gray.py [--out psl_gray.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import psl_probe as P  # noqa: E402
import run_sims as R  # noqa: E402

HERE = Path(__file__).resolve().parent
PSL = HERE / "psl"
SVREF = R.ROOT / "benchmark" / "tasks" / "t1_gray_stepper" / "ref" / "rtl"
VH_FAULT = ("else bin + to_unsigned(1, 10);", "else bin + to_unsigned(2, 10);")
SV_FAULT = ("bin + 10'd1", "bin + 10'd2")


def sby_run(workdir: Path, sby: str, task: str, kind: str, limit: int = 120) -> dict:
    """One SymbiYosys job in its own scope with a memory cap and a run-time limit (the scope is stopped by systemd at the limit)."""
    env = P.toolenv(kind)
    out_dir = workdir / f"out_{Path(sby).stem}_{kind}_{task}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    t0 = time.perf_counter()
    rc, log = P.run(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=3G", "-p", f"RuntimeMaxSec={limit}", "nice", "-n", "15",
                     "sby", "-f", "-d", str(out_dir), sby, task], workdir, env, timeout=limit + 60)
    dt = time.perf_counter() - t0
    st = (out_dir / "status").read_text().split()[0] if (out_dir / "status").is_file() else None
    r = {"status": st, "seconds": round(dt, 2)}
    if st is None and dt >= limit - 1:
        r["status"] = f"TIMEOUT at {limit} s"
        r["last_log_line"] = [l for l in (out_dir / "logfile.txt").read_text().splitlines() if "engine_0:" in l][-1][-120:] if (out_dir / "logfile.txt").is_file() else None
    m = re.search(r"Assert failed in ([\w.\[\]$:/\\ ]+?):", log) or re.search(r"BMC failed!", log)
    fails = re.findall(r"Assert failed in (\S+)", log)
    steps = re.findall(r"failed assertion .* at .* step (\d+)", log)
    if fails:
        r["failed_assertions"] = sorted(set(fails))
    if steps:
        r["first_failing_step"] = min(int(x) for x in steps)
    if st is None and not str(r["status"]).startswith("TIMEOUT"):
        r["error"] = P.first_error(log)
    reached = re.findall(r"Reached cover statement at (\S+)", log)
    if reached:
        r["cover_reached"] = sorted(set(reached))
    unreached = re.findall(r"Unreached cover statement at (\S+)", log)
    if unreached:
        r["cover_unreached"] = sorted(set(unreached))
    return r


def build_formal(work: Path) -> dict:
    if work.exists():
        shutil.rmtree(work)
    (work / "sv").mkdir(parents=True)
    (work / "vhdl").mkdir()
    # SV twin: clean and fault
    for tag, fault in (("clean", None), ("fault", SV_FAULT)):
        d = work / "sv" / tag
        d.mkdir()
        t = (SVREF / "gray_stepper.sv").read_text()
        if fault:
            assert t.count(fault[0]) == 1
            t = t.replace(*fault)
        (d / "gray_stepper.sv").write_text(t)
        shutil.copy(SVREF / "bm_debounce.sv", d)
        shutil.copy(R.ROOT / "shell" / "rtl" / "sync2.sv", d)
        shutil.copy(PSL / "sv" / "gray_fv.sv", d)
        shutil.copy(PSL / "sv" / "gray.sby", d / "gray.sby")
        txt = (d / "gray.sby").read_text()
        txt = re.sub(r"(?m)^\.\./.*/(\w+\.sv)$", r"\1", txt)
        (d / "gray.sby").write_text(txt)
    # VHDL: clean and fault
    for tag, fault in (("clean", None), ("fault", VH_FAULT)):
        d = work / "vhdl" / tag
        d.mkdir()
        t = (PSL / "rtl" / "gray_stepper.vhd").read_text()
        if fault:
            assert t.count(fault[0]) == 1
            t = t.replace(*fault)
        (d / "gray_stepper.vhd").write_text(t)
        shutil.copy(PSL / "rtl" / "sync2.vhd", d)
        shutil.copy(PSL / "rtl" / "bm_debounce.vhd", d)
        base = (PSL / "vhdl" / "gray.sby").read_text()
        for kind in ("debformal", "oss"):
            plug = "plugin -i ghdl" if kind == "oss" else f"plugin -i {Path.home()}/.local/opt/formal-deb/root/usr/lib/yosys/plugins/ghdl.so"
            txt = base.replace("@PLUGIN@", plug)
            txt = re.sub(r"(?m)^\.\./rtl/(\w+\.vhd)$", r"\1", txt).replace("@GRAY@", "gray_stepper.vhd")
            (d / f"gray_{kind}.sby").write_text(txt)
    return {}


def formal(work: Path) -> dict:
    out = {}
    for lang in ("sv", "vhdl"):
        for tag in ("clean", "fault"):
            d = work / lang / tag
            kinds = [("debformal" if lang == "sv" else "debformal", "gray.sby")] if lang == "sv" else [("debformal", "gray_debformal.sby"), ("oss", "gray_oss.sby")]
            if lang == "sv":
                kinds = [("debformal", "gray.sby"), ("oss", "gray.sby")]
            for kind, sby in kinds:
                for task in ("bmc", "cover"):
                    key = f"{lang}/{tag}/{kind}/{task}"
                    out[key] = sby_run(d, sby, task, kind, limit=60 if (lang == 'vhdl' and kind == 'debformal') else 120)
                    print(key, out[key], flush=True)
    return out


class PslSim(R.Sim):
    """A Sim with the PSL switch added to analysis (GHDL -fpsl, NVC --psl)."""

    def build_cmds(self, d, wd, gen):
        c = super().build_cmds(d, wd, gen)
        if self.kind.startswith("ghdl"):
            return [x[:2] + ["-fpsl"] + x[2:] for x in c]
        c[0] = c[0][:-len(d["files"])] + ["--psl"] + c[0][-len(d["files"]):]
        return c

    def run_cmd(self, d, wd, gen):
        c = super().run_cmd(d, wd, gen)
        if self.kind.startswith("ghdl"):
            c.insert(2, "-fpsl")          # GHDL wants -fpsl on the run command too (it re-reads the analysed PSL)
        return c


def simulate(work: Path) -> dict:
    out = {}
    base = dict(R.DESIGNS["gray_stepper"])
    for tag, fault in (("clean", None), ("fault", VH_FAULT)):
        d = work / "vhdl" / tag
        dd = dict(base, files=[d / "sync2.vhd", d / "bm_debounce.vhd", d / "gray_stepper.vhd"])
        for s in (PslSim("ghdl-4.1.0-mcode", str(Path.home() / ".local/bin/ghdl"), dict(os.environ), "ghdl-mcode"),
                  PslSim("nvc-1.23.1-aot", str(Path.home() / ".local/opt/nvc-1.23.1/root/usr/bin/nvc"), R.nvc_env(), "nvc-aot")):
            r = R.one(s, "gray_stepper", dd, 300, work / "sim", tag=f"__{tag}")
            r["psl_messages"] = r.get("work_psl_failures")
            r["psl_first"] = r.get("work_psl_first")
            out[f"{tag}/{s.name}"] = {k: v for k, v in r.items() if k not in ("work_log_tail", "start_log_tail")}
            print(f"sim {tag}/{s.name}: build_ok={r.get('build_ok')} tests={r.get('work_xml')} psl_msgs={r['psl_messages']} {r.get('error', '')[:200]}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "psl_gray.json"))
    ap.add_argument("--sim-only", action="store_true", help="keep the formal results already in --out and rerun the simulations")
    ap.add_argument("--work", default=str(R.ROOT / "build" / "156_psl_gray"))
    a = ap.parse_args()
    work = Path(a.work)
    build_formal(work)
    if a.sim_only and Path(a.out).is_file():
        res = json.loads(Path(a.out).read_text())
        res["sim"] = simulate(work)
        res["sim_date"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        res = {"date": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "formal": formal(work), "sim": simulate(work)}
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
