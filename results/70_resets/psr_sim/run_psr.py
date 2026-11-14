#!/usr/bin/env python3
"""Brief 70 Part 2b: run the Processor System Reset bench in Vivado 2026.1 xsim and write the record.

    python3 results/70_resets/psr_sim/run_psr.py [--work DIR] [--record results/70_resets/records/psr_sequence.json]
    python3 results/70_resets/psr_sim/run_psr.py --parse LOG      # parse an existing Vivado log only

Small behavioural simulation, no implementation; the caller holds a heavy slot while Vivado runs. The bench prints
`EV|cycle|signal|value` for every output change and `MARK|cycle|label` for every stimulus step; this script derives, for
each stimulus, which outputs asserted, how many clock cycles after the stimulus began, and how many cycles after it ended
each output released. Cycle = rising clock edges since time zero (the bench's own counter), so the figures are exact to
one cycle.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIVADO = os.environ.get("FDA_VIVADO", "/opt/Xilinx/2026.1/Vivado/bin/vivado")
OUTS = ("bus_struct_reset", "peripheral_reset", "interconnect_aresetn", "peripheral_aresetn", "mb_reset")
ACTIVE = {"bus_struct_reset": "1", "peripheral_reset": "1", "mb_reset": "1", "interconnect_aresetn": "0", "peripheral_aresetn": "0"}


def parse(text: str) -> dict:
    marks, evs, t0, vivado, vlnv, cfg = [], [], None, None, None, None
    for ln in text.splitlines():
        if ln.startswith("EV|"):
            _, c, s, v = ln.split("|")[:4]
            evs.append((int(c), s, v.strip()))
        elif ln.startswith("MARK|"):
            _, c, lab = ln.split("|")[:3]
            marks.append((int(c), lab.strip()))
        elif ln.startswith("T0|"):
            t0 = dict(kv.split("=") for kv in ln[3:].split())
        m = re.match(r"FDA-IP VIVADO (\S+)", ln)
        if m:
            vivado = m.group(1)
        m = re.match(r"FDA-IP C_EXT_RESET_HIGH (\S+) C_AUX_RESET_HIGH (\S+) C_EXT_RST_WIDTH (\S+)", ln)
        if m:
            cfg = {"C_EXT_RESET_HIGH": m.group(1), "C_AUX_RESET_HIGH": m.group(2), "C_EXT_RST_WIDTH": m.group(3)}
        m = re.match(r"FDA-IP VLNV (\S+) REQUIRES_LICENSE (\S+)", ln)
        if m:
            vlnv = {"vlnv": m.group(1), "requires_license": m.group(2)}
    tests = {}
    labels = [m[1] for m in marks]
    for lab in labels:
        if lab.endswith("_begin"):
            name = lab[:-6]
            b = next(c for c, l in marks if l == lab)
            e = next(c for c, l in marks if l == name + "_end")
            nxt = [c for c, l in marks if c > e]
            horizon = min(nxt) if nxt else 10 ** 9
            r = {"begin": b, "end": e, "width_cycles": e - b}
            for o in OUTS:
                ch = [(c, v) for c, s, v in evs if s == o and b <= c <= horizon]
                asserted = [c for c, v in ch if v == ACTIVE[o] and c > b]
                released = [c for c, v in ch if v != ACTIVE[o] and c >= e]
                r[o] = {"asserted_after": (asserted[0] - b) if asserted else None,     # None: it did not (re)assert
                        "released_after_end": (released[0] - e) if released else None}  # None: not released before the next step
            tests[name] = r
    start = next((c for c, l in marks if l == "power_up"), 0)
    first = next((c for c, l in marks if l.endswith("_begin")), 10 ** 9)
    power_up = {}
    for o in OUTS:
        rel = [c for c, s, v in evs if s == o and v != ACTIVE[o] and start <= c < first]
        power_up[o] = (rel[0] - start) if rel else None
    return {"vivado": vivado, "ip": vlnv, "ip_config": cfg, "t0_values": t0, "power_up_release_cycle": power_up, "stimuli": tests,
            "events": len(evs)}


def run(work: Path, config: str) -> str:
    """One simulation. config: "default" (the generated IP's own settings) or "0" (external reset active low)."""
    work = work / ("cfg_" + config)
    work.mkdir(parents=True, exist_ok=True)
    tb = work / "tb_psr.sv"
    ext_high = {"default": "1", "0": "0"}[config]       # the IP's default is active high: see the record's `ip_config`
    tb.write_text((HERE / "tb_psr.sv").read_text().replace("localparam bit EXT_HIGH = 1'b1;", f"localparam bit EXT_HIGH = 1'b{ext_high};"))
    cmd = ["systemd-run", "--user", "--scope", "-p", "MemoryMax=4G", "nice", "-n", "15", VIVADO, "-mode", "batch", "-notrace",
           "-log", str(work / "psr.log"), "-journal", str(work / "psr.jou"),
           "-source", str(HERE / "run_psr.tcl"), "-tclargs", str(work), str(tb), config]
    subprocess.run(cmd, cwd=work, check=False, capture_output=True, text=True)
    return (work / "psr.log").read_text(errors="replace")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/tmp/psr_work")
    ap.add_argument("--record", default=str(HERE.parent / "records" / "psr_sequence.json"))
    ap.add_argument("--parse")
    ap.add_argument("--reparse", help="a work directory of an earlier run: parse its two logs again")
    a = ap.parse_args()
    if a.reparse:
        w = Path(a.reparse)
        rec = {c: parse((w / f"cfg_{c}" / "psr.log").read_text(errors="replace")) for c in ("default", "0")}
        rec = {"vivado": rec["default"]["vivado"], "default": rec["default"], "ext_reset_active_low": rec["0"]}
    elif a.parse:
        rec = parse(Path(a.parse).read_text(errors="replace"))
    else:
        rec = {c: parse(run(Path(a.work), c)) for c in ("default", "0")}
        rec = {"vivado": rec["default"]["vivado"], "default": rec["default"], "ext_reset_active_low": rec["0"]}
    Path(a.record).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v.get("power_up_release_cycle") for k, v in rec.items() if isinstance(v, dict)}))
