#!/usr/bin/env python3
"""Brief 206: read one compiled Quartus case (build/q/q_<tag>_i<INITV>_pb<ON|OFF>) into a JSON record.

Usage: parse_quartus.py <case-dir> > records/altera/<case>.json

Reads: the fitter's "Fitter Resource Utilization by Entity" table (every column, per arm entity), the synthesis
"Resource Utilization by Entity" table, the first (slow, hot) "Fmax Summary" of the Timing Analyzer, the I/O pin tables'
register and "Power Up High" columns for the Q5 pins, the synthesis and fitter messages that mention power-up, push-back,
RAM inference or DEV_CLRn, and the post-fit Verilog netlist's ``power_up`` parameter per arm (count of high / low).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ARMS = {"u_q1": "q1", "u_q2": "q2", "u_q3": "q3", "u_q4": "q4", "u_q5": "q5", "u_q6m": "q6_mult", "u_q6r": "q6_ram",
        "u_q7": "q7", "u_q8": "q8", "u_q9": "q9"}
CLK = {"clk1": "q1", "clk2": "q2", "clk3": "q3", "clk4": "q4", "clk5": "q5", "clk6": "q6_mult", "clk10": "q6_ram",
       "clk7": "q7", "clk8": "q8", "clk9": "q9"}
MSG_KEEP = re.compile(r"power|push-back|push back|uninferred|DEV_CLRn|Power-Up|18010|18061|13000|13003|276007", re.I)


def table(lines: list[str], title: str) -> tuple[list[str], list[list[str]]]:
    """The first ';'-delimited table after a line whose text starts with '; <title>'."""
    for i, l in enumerate(lines):
        if l.startswith("; " + title):
            break
    else:
        return [], []
    rows, head = [], []
    for l in lines[i + 1:]:
        if l.startswith("+") or not l.strip():
            if rows and not l.strip():
                break
            continue
        if not l.startswith(";"):
            break
        cells = [c.strip() for c in l.strip().strip(";").split(";")]
        if not head:
            head = cells
        else:
            rows.append(cells)
    return head, rows


def entity_rows(rpt: Path, title: str) -> dict[str, dict[str, str]]:
    head, rows = table(rpt.read_text(errors="replace").splitlines(), title)
    out = {}
    for r in rows:
        node = r[0]
        for inst, arm in ARMS.items():
            if re.search(r":" + re.escape(inst) + r"\|$", node):
                out[arm] = dict(zip(head[1:], r[1:]))
        if node == "|q_top":
            out["total"] = dict(zip(head[1:], r[1:]))
    return out


def main(case: Path) -> dict:
    name = case.name
    rec: dict = {"case": name}
    fit, mp, sta = case / f"{name}.fit.rpt", case / f"{name}.map.rpt", case / f"{name}.sta.rpt"
    rec["fit_entity"] = entity_rows(fit, "Fitter Resource Utilization by Entity") if fit.is_file() else {}
    rec["map_entity"] = entity_rows(mp, "Analysis & Synthesis Resource Utilization by Entity") if mp.is_file() else {}
    rec["fmax_mhz"] = {}
    if sta.is_file():
        ls = sta.read_text(errors="replace").splitlines()
        title = next((l[2:].split(";")[0].strip() for l in ls if re.match(r"; Slow .*85C Model Fmax Summary", l)), None)
        if title:
            head, rows = table(ls, title)
            rec["fmax_model"] = title
            for r in rows:
                d = dict(zip(head, r))
                if d.get("Clock Name") in CLK:
                    rec["fmax_mhz"][CLK[d["Clock Name"]]] = float(d["Fmax"].split()[0])
    if fit.is_file():
        ls = fit.read_text(errors="replace").splitlines()
        io = {}
        for t in ("Input Pins", "Output Pins"):
            head, rows = table(ls, t)
            for r in rows:
                d = dict(zip(head, r))
                if d.get("Name", "").startswith("io_d"):
                    io[d["Name"]] = {k: d.get(k) for k in ("Input Register", "Output Register", "Power Up High") if k in d}
        rec["io_pins"] = io
    msgs = []
    for rpt in (mp, fit):
        if not rpt.is_file():
            continue
        for l in rpt.read_text(errors="replace").splitlines():
            m = re.match(r"\s*(Critical Warning|Warning|Info) \((\d+)\): (.*)", l)
            if not m or m.group(2) in ("15719", "15720", "12021", "144001"):
                continue
            text = re.sub(r" File: .*", "", m.group(3))
            if MSG_KEEP.search(text) or m.group(2) in ("18010", "18061", "13000", "13003", "276007"):
                msgs.append({"report": rpt.suffixes[0][1:], "severity": m.group(1), "id": m.group(2), "text": text[:240]})
    rec["messages"] = msgs
    vo = sorted((case / "simulation").rglob("*85c_slow.vo")) or sorted((case / "simulation").rglob("*.vo"))
    rec["netlist_power_up"] = {}
    if vo:
        txt = vo[0].read_text(errors="replace")
        for inst, arm in ARMS.items():
            pu = re.findall(r"defparam \\" + re.escape(inst) + r"\|[^\n]* \.power_up = \"(\w+)\";", txt)
            rec["netlist_power_up"][arm] = {"high": pu.count("high"), "low": pu.count("low")}
        rec["netlist"] = vo[0].name
    return rec


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=1, sort_keys=True))
