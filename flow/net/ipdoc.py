#!/usr/bin/env python3
"""Generate ip_lib/<block>/README.md from its ip.yaml and the recorded results, and check every ip.yaml against its
RTL (brief 28's rules as applied in brief 40).

    python3 flow/net/ipdoc.py            # write the READMEs and ip_lib/README.md's table
    python3 flow/net/ipdoc.py --check    # exit 1 if any README is stale or any ip.yaml disagrees with its RTL
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IP = ROOT / "ip_lib"
NET = ["eth_mac_rmii", "eth_mac_rgmii", "pkt_parser", "match_exact", "match_lpm", "match_ternary", "axil_table_ctrl", "pkt_rewrite",
       "pkt_queue_sched", "l2_switch"]
HIL = ["freq_duty_counter", "frame_crc", "dds_awg", "logic_analyser", "adc_histogram"]       # brief 30 instruments
REQUIRED = ["name", "version", "summary", "top", "rtl", "depends", "interfaces", "clocks", "resets", "parameters",
            "constraints", "latency", "throughput", "guards", "sweep_tested", "evidence", "cost_table", "boundary",
            "limits", "licence"]


def rtl_params(block: str, top: str) -> dict:
    """The top module's `parameter int NAME = value` list, read from its header."""
    for f in (IP / block / "rtl").glob("*.sv"):
        t = f.read_text()
        m = re.search(rf"module\s+{top}\s*#\s*\((.*?)\)\s*\(", t, re.S)
        if m:
            return {k: int(v.replace("_", "")) for k, v in re.findall(r"parameter\s+int\s+(\w+)\s*=\s*([\d_]+)", m.group(1))}
        if re.search(rf"module\s+{top}\s*\(", t):
            return {}
    raise ValueError(f"{block}: top {top} not found")


def check(block: str) -> list[str]:
    y = yaml.safe_load((IP / block / "ip.yaml").read_text())
    errs = [f"{block}: missing {k}" for k in REQUIRED if k not in y]
    rp = rtl_params(block, y["top"])
    yp = y.get("parameters") or {}
    if set(rp) != set(yp):
        errs.append(f"{block}: parameters differ: RTL {sorted(rp)} ip.yaml {sorted(yp)}")
    for k, spec in yp.items():
        if k in rp and spec.get("default") != rp[k]:
            errs.append(f"{block}: {k} default {spec.get('default')} != RTL {rp[k]}")
    for pt in y.get("sweep_tested", []):
        for k, v in pt.items():
            s = yp.get(k)
            if s and "range" in s and not (s["range"][0] <= v <= s["range"][1]):
                errs.append(f"{block}: sweep point {k}={v} outside {s['range']}")
            if s and "set" in s and v not in s["set"]:
                errs.append(f"{block}: sweep point {k}={v} not in {s['set']}")
    for g in y.get("guards", []):
        inside = all((("range" in yp.get(k, {}) and yp[k]["range"][0] <= v <= yp[k]["range"][1]) or
                      ("set" in yp.get(k, {}) and v in yp[k]["set"])) and not (yp.get(k, {}).get("pow2") and v & (v - 1))
                     for k, v in g.items())
        if inside and not y.get("constraints"):
            errs.append(f"{block}: guard {g} is inside the declared space")
    for f in y["rtl"]:
        if not (IP / block / f).exists():
            errs.append(f"{block}: rtl file {f} missing")
    for d in y["depends"]:
        if not (IP / d / "ip.yaml").exists():
            errs.append(f"{block}: dependency {d} has no ip.yaml")
    return errs


def readme(block: str) -> str:
    y = yaml.safe_load((IP / block / "ip.yaml").read_text())
    faults = IP / block / "faults.yaml"
    L = [f"# {block} {y['version']}", "", y["summary"], "",
         "Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.", "",
         f"Status: {y['status']}.", "", "## Parameters", "", "| Name | Default | Allowed | Note |", "|---|---|---|---|"]
    for k, s in (y["parameters"] or {}).items():
        allowed = (f"{s['range'][0]}..{s['range'][1]}" if "range" in s else ", ".join(map(str, s["set"])))
        if s.get("pow2"):
            allowed += ", power of two"
        L.append(f"| `{k}` | {s['default']} | {allowed} | {s.get('note', '')} |")
    if not y["parameters"]:
        L.append("| (none) | | | |")
    if y["constraints"]:
        L += ["", "Constraints: " + "; ".join(f"`{c}`" for c in y["constraints"]) + "."]
    L += ["", "Out-of-space values fail at elaboration with `$error` (tested: " +
          (", ".join("`" + ", ".join(f"{k}={v}" for k, v in g.items()) + "`" for g in y["guards"]) or "no parameters") + ").",
          "", "## Interfaces", ""]
    for i in y["interfaces"]:
        extra = ", ".join(f"{k} {v}" for k, v in i.items() if k not in ("name", "type", "note", "signals"))
        L.append(f"- `{i['name']}`: {i['type']}" + (f" ({extra})" if extra else "") +
                 (f"; {i['signals']}" if i.get("signals") else "") + (f". {i['note']}" if i.get("note") else ""))
    L += ["", "Clocks: " + ", ".join(f"`{c['name']}`" + (f" ({c['note']})" if c.get("note") else "") for c in y["clocks"]) +
          ". Reset: `rst`, active high, synchronous.", "", "## Latency and throughput", ""]
    L += [f"- {k}: {v}" for k, v in y["latency"].items()] + [f"- throughput: {y['throughput']}", "",
          "## Evidence", "",
          (y['evidence'].get('summary') or "Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), "
           "Icarus Verilog 12.") + f" Tests: {', '.join('`' + t + '`' for t in y['evidence']['tests'])}.",
          "Parameter points simulated: " + "; ".join("`" + (", ".join(f"{k}={v}" for k, v in p.items()) or "defaults") + "`"
                                                   for p in y["sweep_tested"]) + "."]
    if faults.exists():
        fl = yaml.safe_load(faults.read_text())["faults"]
        res = {}
        fj = (ROOT / "results" / "b58a" / "mac_rgmii_faults.json" if block == "eth_mac_rgmii" else
              ROOT / "results" / ("b30" if block in HIL else "b40") / "faults.json")
        if fj.exists():
            res = {f["name"]: f["status"] for f in json.loads(fj.read_text())["faults"]}
        L += ["", "Seeded faults (`faults.yaml`, run by `" + ("hil/ip_faults.py" if block in HIL else "flow/net/faults.py") + "`):", "", "| Fault | What it breaks | Result |", "|---|---|---|"]
        L += [f"| `{f['name']}` | {f['why']} | {res.get(f['name'], 'not run')} |" for f in fl]
    b = y["boundary"]
    L += ["", "## Boundary and reuse", "", f"- Registered outputs: {b['registered_outputs']}.", f"- Clock crossings: {b['cdc']}.",
          f"- Part, board or pin: {b['part_specific']}.", f"- Depends on: {', '.join(y['depends']) or 'nothing'}.",
          f"- Limits: {y['limits']}.", "", "## Cost table", "", y["cost_table"] + ".", "", f"Licence: {y['licence']}.", ""]
    return "\n".join(L)


def main() -> int:
    chk = "--check" in sys.argv
    errs, stale = [], []
    for b in NET + HIL:
        errs += check(b)
        text = readme(b)
        p = IP / b / "README.md"
        if chk:
            if not p.exists() or p.read_text() != text:
                stale.append(str(p))
        else:
            p.write_text(text)
    for e in errs + [f"stale: {s}" for s in stale]:
        print(e)
    return 1 if errs or stale else 0


if __name__ == "__main__":
    sys.exit(main())
