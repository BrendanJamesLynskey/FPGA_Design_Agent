#!/usr/bin/env python3
"""Brief 156: markdown tables from the records (sim_compare.json, sim_compare_mutants.json, kernel_speed.json, coverage.json,
psl_constructs.json, psl_gray.json) into tables.md. Numbers in the README are copied from tables.md; nothing is typed by hand."""
from __future__ import annotations

import json
from pathlib import Path

H = Path(__file__).resolve().parent


def load(n):
    p = H / n
    return json.loads(p.read_text()) if p.is_file() else None


def f(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def sim_table(d) -> str:
    sims = list(d["versions"])
    out = ["Versions: " + "; ".join(f"`{k}` = {v.split(' | ')[0]}" + (" (" + v.split(' | ')[-1] + ")" if k.startswith("ghdl") else "") for k, v in d["versions"].items()) + "", "",
           f"Median of {d['reps']} runs, seconds, run {d['date']}. build = analysis + elaboration command; start = BENCH_OPS=0 (simulator start, "
           "elaboration for the mcode and JIT flows, cocotb start, reset); sim = workload run minus start; tests = cocotb tests passed.", "",
           "| Design | ops | " + " | ".join(f"{s} build / start / sim" for s in sims) + " | pass/fail | trace digests |", "|---|---:|" + "---|" * (len(sims) + 2)]
    for dn, dd in d["designs"].items():
        cells, pf, digs = [], [], set()
        for s in sims:
            r = dd["sims"][s]
            cells.append(f"{f(r.get('build_s_median'))} / {f(r.get('start_s_median'))} / {f(r.get('sim_s_median'))}")
            reps = r["reps"]
            pf.append("".join("P" if x.get("work_xml", {}).get("fail") == 0 and x.get("work_xml", {}).get("tests") else "F" for x in reps))
            for x in reps:
                t = x.get("work_trace")
                if t:
                    digs.add(t["sha256"][:10])
        agree = "same" if len(digs) == 1 else f"{len(digs)} distinct"
        out.append(f"| {dn} | {dd['ops']} | " + " | ".join(cells) + f" | {'/'.join(sorted(set(pf)))} | {agree} |")
    return "\n".join(out)


def mut_table(d) -> str:
    sims = list(d["versions"])
    out = ["| Design (one fault) | " + " | ".join(sims) + " |", "|---|" + "---|" * len(sims)]
    for dn, dd in d["designs"].items():
        cells = []
        for s in sims:
            reps = dd["sims"][s]["reps"]
            cells.append("caught" if all(x.get("work_xml", {}).get("fail") == 1 for x in reps) else "MISSED")
        out.append(f"| {dn} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def kernel_table(d) -> str:
    out = [f"fir16 pure-VHDL testbench, {d['cycles']} clocks, median of {d['reps']} runs ({d['date']}).", "",
           "| Simulator | build s | run s | clocks per s | result line |", "|---|---:|---:|---:|---|"]
    for s, r in d["sims"].items():
        if "error" in r:
            out.append(f"| {s} | error | | | {r['error'][:80]} |")
        else:
            out.append(f"| {s} | {f(r['build_s'])} | {f(r['run_s_median'])} | {r['clocks_per_s']:.0f} | {'; '.join(r['result'])} |")
    return "\n".join(out)


def cov_table(d) -> str:
    out = ["Lines with at least one hit / lines with coverage items. NVC counts a line when any of its statement, branch, toggle or expression bins "
           "exists; GHDL's file has statement lines only. short = a few operations per run (seed 1, seed 2), merged_short = the two short runs merged "
           "(NVC: `--cover-merge`; GHDL: our union script, because `ghdl coverage` fails on two inputs), full = the whole workload (seed 1).", "",
           "| Design | tool | short seed 1 | short seed 2 | merged short | full |", "|---|---|---:|---:|---:|---:|"]
    for dn in d["nvc"]:
        n, g = d["nvc"][dn], d["ghdl"].get(dn, {})
        if "error" in n:
            out.append(f"| {dn} | NVC | error: {n['error'][:80]} | | | |")
        else:
            c = lambda k: f"{n[k]['lines_hit']}/{n[k]['lines']}"
            out.append(f"| {dn} | NVC 1.23.1 | {c('short_seed1')} | {c('short_seed2')} | {c('merged_short')} | {c('full_seed1')} |")
        if "error" in g:
            out.append(f"| {dn} | GHDL 4.1.0 | error: {g['error'][:80]} | | | |")
        elif g:
            c = lambda k: f"{g[k]['hit']}/{g[k]['total']}"
            out.append(f"| {dn} | GHDL 4.1.0 | {c('short_seed1')} | {c('short_seed2')} | {c('merged_short')} | {c('full_seed1')} |")
    out += ["", "NVC bins per kind, full run (bins hit / bins; excluded bins are the clock and reset toggles NVC leaves out):", "",
            "| Design | statement | branch | toggle | expression | fsm-state |", "|---|---:|---:|---:|---:|---:|"]
    for dn, n in d["nvc"].items():
        if "error" in n:
            continue
        b = n["full_seed1"]["bins"]
        cell = lambda k: f"{b[k]['hit']}/{b[k]['total']}" if k in b else "-"
        out.append(f"| {dn} | {cell('statement')} | {cell('branch')} | {cell('toggle')} | {cell('expression')} | {cell('fsm-state')} |")
    return "\n".join(out)


def psl_table(d) -> str:
    cols = list(d["tools"])
    short = {"ghdl-mcode": "GHDL 4.1.0 sim", "ghdl-llvm": "GHDL 7.0.0-dev sim", "nvc": "NVC 1.23.1 sim", "formal-debgh": "Yosys 0.33 + plugin 4.1.0",
             "formal-oss": "Yosys 0.70 + plugin 7.0.0-dev"}
    out = ["| Construct | expected | " + " | ".join(short[c] for c in cols) + " |", "|---|---|" + "---|" * len(cols)]
    for name, r in d["probes"].items():
        cells = []
        for c in cols:
            x = (r["sim"] if c in r["sim"] else r["formal"])[c]
            exp = r["expected"]
            if not x["accepted"]:
                cells.append("rejected")
            elif exp.startswith("cover") and c in r["sim"]:
                cells.append("accepted (no cover report read)")      # a simulation prints nothing for a cover directive; formal reaches or not
            else:
                v = x["verdict"]
                ok = {"true": "pass", "false": "fail", "cover": "pass", "cover-unreachable": "fail"}[exp]
                cells.append(f"{v}" + ("" if v == ok else " (differs from the formal tools and the other simulators)" if c == "nvc" else " (WRONG)"))
        out.append(f"| `{name}` | {r['expected']} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def psl_notes(d) -> str:
    out = ["Why a construct was rejected (first error line of the tool, paths removed):", "", "| Construct | tool | message |", "|---|---|---|"]
    seen = set()
    for name, r in d["probes"].items():
        for c, x in {**r["sim"], **r["formal"]}.items():
            if not x["accepted"]:
                key = (name, x["note"])
                if key in seen:
                    continue
                seen.add(key)
                tools = [t for t, y in {**r["sim"], **r["formal"]}.items() if not y["accepted"] and y["note"] == x["note"]]
                out.append(f"| `{name}` | {', '.join(tools)} | {x['note'].replace('|', '/')} |")
    return "\n".join(out)


def gray_table(d) -> str:
    out = [f"Run {d['date']}. Formal: SymbiYosys `bmc` (depth 20, z3) and `cover`; sim: the cocotb bench of brief 55's gray_stepper with the PSL properties compiled in.", "",
           "| Language | design | flow | bmc | cover |", "|---|---|---|---|---|"]
    flows = {}
    for k, r in d["formal"].items():
        lang, tag, kind, task = k.split("/")
        flows.setdefault((lang, tag, kind), {})[task] = r
    lab = {"debformal": "Yosys 0.33 (Ubuntu)" , "oss": "Yosys 0.70 (OSS CAD Suite)"}
    for (lang, tag, kind), t in flows.items():
        def cell(r):
            if r is None:
                return "-"
            x = r["status"] or ("error: " + r.get("error", "")[:60])
            if r.get("first_failing_step") is not None:
                x += f" at step {r['first_failing_step']}"
            return f"{x} ({r['seconds']} s)"
        who = ("SV twin, `ifdef FORMAL`, Yosys front end" if lang == "sv" else "VHDL, PSL, GHDL plugin " + ("4.1.0" if kind == "debformal" else "7.0.0-dev"))
        out.append(f"| {'SystemVerilog' if lang == 'sv' else 'VHDL'} | {tag} | {who}; {lab[kind]} | {cell(t.get('bmc'))} | {cell(t.get('cover'))} |")
    out += ["", "| Simulation | design | cocotb bench | PSL messages | first message |", "|---|---|---|---:|---|"]
    for k, r in d["sim"].items():
        tag, sim = k.split("/")
        x = r.get("work_xml") or {}
        res = "build failed" if not r.get("build_ok") else ("pass" if x.get("fail") == 0 and x.get("tests") else "fail")
        out.append(f"| {sim} | {tag} | {res} | {r.get('psl_messages')} | {(r.get('psl_first') or r.get('error') or '')[:90]} |")
    return "\n".join(out)


def main():
    parts = []
    for title, fn, tf in (("Simulator comparison under cocotb", "sim_compare.json", sim_table), ("Faults caught", "sim_compare_mutants.json", mut_table),
                          ("Kernel speed without cocotb", "kernel_speed.json", kernel_table), ("NVC coverage", "coverage.json", cov_table),
                          ("PSL constructs", "psl_constructs.json", lambda d: psl_table(d) + "\n\n" + psl_notes(d)), ("PSL properties on the Gray stepper", "psl_gray.json", gray_table)):
        d = load(fn)
        if d:
            parts.append(f"## {title}\n\n{tf(d)}\n")
    (H / "tables.md").write_text("\n".join(parts))
    print("\n".join(parts))


if __name__ == "__main__":
    main()
