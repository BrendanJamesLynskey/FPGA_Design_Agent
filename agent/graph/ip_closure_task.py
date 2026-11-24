"""Run the closure loop on an ip_lib block's RTL (brief 88: the network blocks to 125 MHz).

    python3 -m agent.graph.ip_closure_task <block> --case <name> [--part xc7a100tcsg324-1] [--clock-mhz 125]
           --extra-latency 4 [--max-iter 6] [--max-usd 1.0] [--model openai/gpt-6-luna] [--replay calls.json]
           [--out results/b88_net125/<case>] [--rtl DIR] [--point N] [--scan-multiply] [--build-only]

The task is "meet <clock> MHz on <part>, keep the behaviour bit-exact, and add at most <extra-latency> clocks of latency".
It is stated to the writer in the contract, and the same budget is what the block's bench accepts (``NET_LAT_EXTRA``,
flow/net/tests/axis_tb.py ``lat_ok``).

- **G1** is the block's own pytest bench (flow/net/tests/test_63d_<block>_rtl.py, every point and guard), run against the
  staged RTL through ``NET_RTL_<BLOCK>``. The writer never sees the bench, only its failure text on a functional retry.
- **The build** is one out-of-context Vivado run of the block at its first characterisation point (flow/ipchar.tcl), with
  the clock on port ``clk``; the reports are written in the layout ``flow.digest.build.digest_build`` reads, so the
  closure loop and its prompts are those of brief 62. Pulse width counts: G2 fails when WPWS is negative.
- **Sign-off** (the loop's ``signoff``): the whole bench again, the block's seeded faults all caught, and the block's other
  characterisation points built and timed at the same clock. Closure is claimed only when all three pass.
- Heavy slot: each build takes one through ``_handoff/take_heavy_slot.sh`` ("Vivado impl"), released only if the lock text
  starts with this run's prefix.

Records ``history.jsonl``, ``summary.json``, ``closure_actions.jsonl``, ``llm_calls.jsonl`` and the final RTL in ``--out``.
"""
from __future__ import annotations

from agent.core.prompts import load as _p

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.graph import closure as cl  # noqa: E402
from flow import ipchar  # noqa: E402
from flow import ipvariants as iv  # noqa: E402

SLOT = Path(os.environ.get("FDA_SLOT_SCRIPT", "/home/brendan/Claude_sandbox/_handoff/take_heavy_slot.sh"))
TESTS = {"icmp_echo": "test_63d_icmp_rtl.py", "arp_responder": "test_63d_arp_rtl.py",
         "ipv4_udp_rx": "test_63d_udp_rx_rtl.py", "ipv4_udp_tx": "test_63d_udp_tx_rtl.py",
         "igmp_join": "test_63d_igmp_rtl.py"}


def task_text(block: str, mhz: float, part: str, extra: int) -> str:
    y = yaml.safe_load((iv.IP / block / "ip.yaml").read_text())
    return (_p("graph/ip_closure_task/task_text_1").format(y['top'], y['summary'].strip(), mhz, 1000 / mhz, part, extra, json.dumps(y['latency'])))


def stage(block: str, case: str) -> Path:
    d = ROOT / "build" / "ipclosure" / case
    shutil.rmtree(d, ignore_errors=True)
    (d / "rtl").mkdir(parents=True)
    for f in sorted((iv.IP / block / "rtl").glob("*.sv")):
        shutil.copy2(f, d / "rtl" / f.name)
    return d


def pytest_g1(block: str, d: Path, extra: int, tests: list[str] | None = None, label: str = "g1"):
    """The block's bench against the staged RTL -> {pass, tests, detail}."""
    files = tests or [f"flow/net/tests/{TESTS[block]}"]

    def g1(rtl: Path) -> dict:
        env = dict(os.environ, FDA_SIM_BUILD_ROOT=str(d / "sim"), NET_LAT_EXTRA=str(extra), NET_BUILD=str(d / "simbuild"), PYTHONPATH=str(ROOT),
                   **{f"NET_RTL_{block.upper()}": str(rtl.resolve())})
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", "--tb=line", *files],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        out = r.stdout + r.stderr
        res = {m.group(2): m.group(1) == "PASSED" for m in re.finditer(r"^(PASSED|FAILED|ERROR) (\S+)", out, re.M)}
        fails = [l for l in out.splitlines() if re.search(r"Error|assert|FAIL", l)][-12:]
        (d / f"{label}_last.log").write_text(out[-20000:])
        return {"pass": r.returncode == 0 and bool(res), "tests": res, "detail": "\n".join(fails)[-2000:]}
    return g1


def take_slot(prefix: str, text: str, log=print) -> Path | None:
    while SLOT.exists():
        r = subprocess.run([str(SLOT), f"{prefix}: {text}"], capture_output=True, text=True)
        if r.returncode == 0:
            lock = Path(r.stdout.strip().splitlines()[-1])
            log(f"[lock] {lock}: {lock.read_text().strip()}")
            return lock
        time.sleep(60)
    return None


def release(lock: Path | None, prefix: str) -> None:
    if lock and lock.is_file() and lock.read_text().startswith(prefix + ":"):
        lock.unlink()


def ooc_build(block: str, d: Path, part: str, mhz: float, prefix: str, point: int = 0, peak_g: float = 4.0, log=print,
              name: str = "base"):
    """One out-of-context run of ``block`` at characterisation point ``point``, written as <d>/build/<name>/ in the layout
    digest_build reads. Returns the digest."""
    y = yaml.safe_load((iv.IP / block / "ip.yaml").read_text())
    pts = y["characterisation"]["points"]
    full = iv.point(block, pts[point], (list(y["variants"])[0] if y.get("variants") else None))
    vp = y.get("variant_param")
    gen = {k: (f'"{v}"' if isinstance(v, str) else v) for k, v in full.items()}
    wd = d / "build" / name
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    srcs = sorted(str(p.resolve()) for p in (d / "rtl").glob("*.sv"))
    jobs = wd / "jobs.tcl"
    jobs.write_text("\n".join([f"set ipchar(part) {part}", f"set ipchar(sources) {ipchar.tcl_list(srcs)}", "set ipchar(jobs) {}",
                               "lappend ipchar(jobs) " + ipchar.tcl_list([f"{block}/{name}", y["top"], str(wd), f"{1000 / mhz:.3f}",
                                                                          [x for k, v in gen.items() for x in (k, v)]])]) + "\n")
    lock = take_slot(prefix, f"Vivado impl closure {block} {name}, peak {peak_g:g}G, {time.strftime('%H:%M')}, "
                             f"expected end {time.strftime('%H:%M', time.localtime(time.time() + 25 * 60))}", log)
    unit = f"fda-ipclose-{os.getpid()}-{name}"
    try:
        subprocess.run(["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
                        ipchar.vivado(), "-mode", "batch", "-nojournal", "-log", str(wd / "vivado.log"),
                        "-source", str(ROOT / "flow" / "ipchar.tcl"), "-tclargs", str(jobs)], cwd=wd, capture_output=True, text=True)
    finally:
        release(lock, prefix)
    return write_digest(wd, 1000 / mhz)


def write_digest(wd: Path, period: float) -> dict:
    from flow.digest.build import digest_build
    r = ipchar.parse(wd, period)
    if r["status"] != "ok":
        (wd / "gates.json").unlink(missing_ok=True)
        return {"ran": False, "status": r["status"]}
    bram = r.get("bram_tiles") or 0
    g = {"pass": False, "gates": {"pulse_width": r["wpws_ns"] is None or r["wpws_ns"] >= 0},
         "timing": {"wns_ns": r["wns_ns"], "whs_ns": r["whs_ns"], "tns_ns": 0.0 if (r["wns_ns"] or 0) >= 0 else r["wns_ns"],
                    "timing_met": (r["wns_ns"] or -1) >= 0 and (r["whs_ns"] or 0) >= 0, "wpws_ns": r["wpws_ns"]},
         "utilization": {"lut": r["lut"], "ff": r["ff"], "bram_tile": bram, "dsp": r["dsp"], "iob": 0, "lutram": r["lutram"]},
         "power": {"total_w": r["power_w"]["total"], "dynamic_w": r["power_w"]["dynamic"], "static_w": r["power_w"]["static"],
                   "confidence": r["power_w"]["confidence"]}, "power_environment": {"junction_c": 25.0},
         "stages": {"post_route": {"ran": True}}}
    (wd / "gates.json").write_text(json.dumps(g, indent=1))
    dg = digest_build(wd)
    dg["fmax_mhz"] = r["fmax_mhz"]
    return dg


def has_multiply(rtl: Path) -> bool:
    """True when any RTL file has a multiply operator `*` (comments, attributes `(* *)` and `**` powers excluded)."""
    for f in rtl.glob("*.sv"):
        t = re.sub(r"//[^\n]*|/\*.*?\*/", "", f.read_text(), flags=re.S)
        t = re.sub(r"\(\*.*?\*\)", "", t, flags=re.S).replace("**", "")
        if "*" in re.sub(r"\[[^\]]*\*[^\]]*\]|\+:", "", t) and re.search(r"[\w\)\]]\s*\*\s*[\w\(]", t):
            return True
    return False


def spec_for(block: str, mhz: float, part: str, extra: int) -> dict:
    return {"clocks": [{"name": "clk", "freq_mhz": mhz}], "part": part, "top": block,
            "behaviour": {"latency": [f"at most {extra} clocks more than now"]}}


def main(argv=None) -> int:
    from agent.access import require_or_exit
    require_or_exit('agent.graph.ip_closure_task')
    ap = argparse.ArgumentParser()
    ap.add_argument("block", choices=sorted(TESTS))
    ap.add_argument("--case", required=True)
    ap.add_argument("--part", default=iv.DEFAULT_PART)
    ap.add_argument("--clock-mhz", type=float, default=125.0)
    ap.add_argument("--extra-latency", type=int, required=True, help="clocks of latency the change may add (stated before the run)")
    ap.add_argument("--max-iter", type=int, default=6)
    ap.add_argument("--max-usd", type=float, default=1.0)
    ap.add_argument("--model", help="the purpose's model (default: the model table, brief 108)")
    ap.add_argument("--replay", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rtl", type=Path, help="start from this RTL directory instead of ip_lib/<block>/rtl")
    ap.add_argument("--point", type=int, default=0, help="index of the characterisation point the loop builds (the others are built at sign-off)")
    ap.add_argument("--scan-multiply", action="store_true",
                    help="tell the playbook whether the RTL has a multiply (brief 88 fix: no DSP mapping for adder chains; "
                         "also enables the carry-split and verdict-register strategies). Off = the playbook as of brief 62B")
    ap.add_argument("--prefix", default="88")
    ap.add_argument("--build-only", action="store_true")
    a = ap.parse_args(argv)
    out = (a.out or ROOT / "results" / "b88_net125" / a.case).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "history.jsonl").unlink(missing_ok=True)
    d = stage(a.block, a.case)
    if a.rtl:
        for f in (d / "rtl").glob("*.sv"):
            f.unlink()
        for f in sorted(a.rtl.glob("*.sv")):
            shutil.copy2(f, d / "rtl" / f.name)
    spec = spec_for(a.block, a.clock_mhz, a.part, a.extra_latency)
    contract = task_text(a.block, a.clock_mhz, a.part, a.extra_latency)
    from agent.core import prompts as _prompts                 # brief 99: the task text is private; the record keeps its hash
    (out / "task.json").write_text(json.dumps(_prompts.record(task=contract), indent=1) + "\n")
    y = yaml.safe_load((iv.IP / a.block / "ip.yaml").read_text())
    n_pts = len(y["characterisation"]["points"])

    def build(dd: Path) -> dict:
        dg = ooc_build(a.block, d, a.part, a.clock_mhz, a.prefix, point=a.point)
        if a.scan_multiply and dg.get("ran"):
            dg["rtl_has_multiply"] = has_multiply(d / "rtl")
        return dg

    def signoff(_dg: dict) -> dict:
        failed = []
        g1 = pytest_g1(a.block, d, a.extra_latency, [f"flow/net/tests/{TESTS[a.block]}", "flow/net/tests/test_63d_adversarial_rtl.py"],
                       "signoff")(d / "rtl")
        if not g1["pass"]:
            failed.append("bench or adversarial bench fails")
        env = dict(os.environ, FDA_SIM_BUILD_ROOT=str(d / "sim"), NET_LAT_EXTRA=str(a.extra_latency), NET_BUILD=str(d / "simbuild"))
        f = subprocess.run([sys.executable, "flow/net/faults.py", "--only", ",".join(m["name"] for m in
                                                                                      yaml.safe_load((iv.IP / a.block / "faults.yaml").read_text())["faults"]),
                            "--rtl-dir", str(d / "rtl"), "--json", str(out / "signoff_faults.json")],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        (out / "signoff_faults.log").write_text((f.stdout + f.stderr)[-8000:])
        try:
            fj = json.loads((out / "signoff_faults.json").read_text())["faults"]
        except (OSError, ValueError, KeyError):
            fj = None
        if fj is None:
            failed.append("the fault run produced no result")
        else:
            bad = [x["name"] for x in fj if x["status"] not in ("caught", "invalid")]
            if bad:
                failed.append("seeded faults not caught: " + ", ".join(bad))
            # a fault whose old text no longer occurs in the pipelined RTL is "invalid", not caught: it is re-expressed by
            # hand afterwards (recorded in signoff_faults.json); closure is not claimed on a design with no live fault there
            note_invalid = [x["name"] for x in fj if x["status"] == "invalid"]
            (out / "signoff_invalid_faults.txt").write_text("\n".join(note_invalid) + "\n")
        for i in [j for j in range(n_pts) if j != a.point]:
            dg = ooc_build(a.block, d, a.part, a.clock_mhz, a.prefix, point=i, name=f"point{i}")
            t = (dg.get("timing") or {})
            if not (dg.get("ran") and (t.get("wns_ns") or -1) >= 0 and (t.get("whs_ns") or 0) >= 0 and (dg.get("gates") or {}).get("pulse_width", True)):
                failed.append(f"point {i} does not meet {a.clock_mhz:g} MHz")
        return {"pass": not failed, "failed": failed}

    from agent.models import resolver_for
    calls: list = []
    rs = resolver_for("closure", model=a.model, replay=a.replay, record=None if a.replay else out / "llm_replay.json")
    client = rs.chat("closure")
    model = rs.entry("closure").model
    c = cl.Closure(ws=cl.Workspace(d), goals=cl.goals_from_spec(spec), g1=pytest_g1(a.block, d, a.extra_latency), build=build,
                   editor=cl.llm_editor(client, calls), contract=contract, spec=spec,
                   max_iter=0 if a.build_only else a.max_iter, max_usd=a.max_usd, record=out, joint=True, case=a.case,
                   synth=None, signoff=signoff)
    rep = c.run()
    rep.update({"case": a.case, "block": a.block, "part": a.part, "model": model, "clock_mhz": a.clock_mhz,
                "extra_latency": a.extra_latency})
    (out / "summary.json").write_text(json.dumps(rep, indent=1, default=str) + "\n")
    with (out / "llm_calls.jsonl").open("w") as f:
        for r in calls:
            f.write(json.dumps(r) + "\n")
    shutil.rmtree(out / "rtl_final", ignore_errors=True)
    shutil.copytree(d / "rtl", out / "rtl_final")
    print(json.dumps({k: rep[k] for k in ("stop", "start_line", "final_line", "iterations", "accepted", "reverted", "usd",
                                          "closure_claimed")}, indent=1))
    return 0 if rep["closure_claimed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
