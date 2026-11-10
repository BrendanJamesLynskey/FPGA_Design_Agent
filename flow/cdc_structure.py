#!/usr/bin/env python3
"""Structural clock-domain-crossing check from the synthesised netlist (brief 16, V-level CDC gate, part 1).

``report_cdc`` looks at one crossing at a time and says "synchronised" for anything shaped like a synchroniser. It does
not see a bus crossed bit by bit through valid 1-bit synchronisers (M3, M6a), two synchronisers whose outputs are
combined (M7), or a bit sampled by two flops (M2). This check lists EVERY register-to-register path whose launch and
capture clocks are asynchronous (flow/cdc_paths.tcl, from the netlist; the ``report_cdc -details`` rows of every
severity supply each crossing's timing exception) and classifies each crossing:

  synchroniser       a chain of >= 2 ASYNC_REG flops, one source flop with no logic in front, the first stage driving only
                     the second, not combined with another synchroniser's output
  xpm                an XPM CDC macro's own flops (xpm_cdc_single / array_single / pulse / sync_rst / async_rst)
  gray/handshake/fifo  a multi-bit crossing: an XPM Gray, handshake or FIFO instance, or a hand-built structure, safe only
                     with its ``Max Delay Datapath Only`` exception (a CDC-6 row is not safe by itself: the Warning is
                     the tool saying "multi-bit, check the skew")
  reset bridge       an asynchronous reset that crosses into ASYNC_REG flops (asserted asynchronously, released by a chain)
  unsafe             everything else; the ``why`` says which rule

Rules, in the order they apply (the first that matches gives the verdict):
  U1 asynchronous reset into a flop that is not an ASYNC_REG bridge flop
  U2 no synchroniser: the capture flop is not the first of an ASYNC_REG chain (missing ASYNC_REG, or a single flop)
  U3 logic or several source flops in front of the first stage (more than one startpoint)
  U4 the first stage also feeds logic (fan-out before the second stage), e.g. one bit sampled by two flops (M2)
  U5 a multi-bit bus (>= 2 bits of one register from one source register) through 1-bit synchronisers without a
     ``Max Delay Datapath Only`` exception (M3, M6a)
  U6 reconvergence: two synchronisers from one launch clock to one capture clock whose outputs reach a common flop (M7)
  U7 data captured with no synchroniser: allowed only as a hand-built handshake/FIFO data path (the exception present and a
     recognised synchroniser or constrained bus on the same clock pair) or a RAM read of a FIFO (same condition)
A crossing the design's ``cdc_waivers`` (architecture.yaml, each with a reason) names is "waived" and listed.

What it cannot see: a pulse into a level synchroniser (M5), a reset applied to one side only (M9, M11), a binary bus with
the right exception (the exception, not the coding, is what it checks). Those are for the injected simulation
(flow/cdc_inject.py). Two clocks are asynchronous when their primary clocks differ.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROW = re.compile(r"^\s*(\d+)\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+(.*?)\s{2,}(\d+)\s{2,}(.*?)\s{2,}(\S+)\s+(\S+)\s*$")


def parse_paths(text: str) -> dict[str, Any]:
    """flow/cdc_paths.tcl output: the clocks and one dict per capture pin."""
    if "# cdc_paths v1" not in text:
        raise ValueError("not a cdc_paths report (no '# cdc_paths v1' header)")
    if "# end" not in text:
        raise ValueError("cdc_paths report is incomplete (no '# end' line: flow/cdc_paths.tcl stopped before the end)")
    clocks, paths, errors = {}, [], []
    for line in text.splitlines():
        if line.startswith("ERROR|"):
            errors.append(line[6:])
        elif line.startswith("CLOCK|"):
            _, n, per, root = line.split("|")[:4]
            clocks[n] = {"period": float(per or 0), "root": root}
        elif line.startswith("PATH|"):
            f = line.split("|")
            f += [""] * (13 - len(f))
            paths.append({"cell": f[1], "ref": f[2], "pin": f[3], "clk": f[4], "async_reg": f[5] in ("1", "TRUE"),
                          "src": f[6], "src_ref": f[7], "src_clk": f[8], "nstart": int(f[9] or 0), "chain": int(f[10] or 0),
                          "nloads": int(f[11] or 0), "sinks": [s for s in f[12].split(",") if s]})
    return {"clocks": clocks, "paths": paths, "errors": errors}


def parse_cdc_rows(text: str) -> list[dict[str, Any]]:
    """report_cdc -details rows of every severity: clocks, rule, severity, exception, source and destination objects."""
    rows, src_clk, dst_clk, typ = [], "", "", ""
    for line in text.splitlines():
        if line.startswith("Source Clock:"):
            src_clk = line.split(":", 1)[1].strip()
        elif line.startswith("Destination Clock:"):
            dst_clk = line.split(":", 1)[1].strip()
        elif line.startswith("CDC Type:"):
            typ = line.split(":", 1)[1].strip()
        else:
            m = ROW.match(line)
            if m:
                rows.append({"row": int(m.group(1)), "rule": m.group(2), "severity": m.group(3), "description": m.group(4),
                             "depth": int(m.group(5)), "exception": m.group(6), "from": m.group(7), "to": m.group(8),
                             "src_clk": src_clk, "dst_clk": dst_clk, "type": typ})
    return rows


def base(name: str) -> str:
    """A register's name without its last bit index or range: ``s1_reg[3]`` and ``s1_reg[7:0]`` -> ``s1_reg``;
    a trailing pin (``/D``, ``/C``) is dropped first."""
    name = re.sub(r"/(?:D|C|CE|R|S|CLR|PRE|Q)$", "", name)
    return re.sub(r"\[[\d:]+\]$", "", name)


def xpm_kind(cell: str) -> str | None:
    """The XPM macro a cell belongs to, from the names AMD's macros give their flops."""
    for pat, kind in (("xpm_fifo", "xpm_fifo"), ("dest_graysync_ff", "xpm_gray"), ("src_gray_ff", "xpm_gray"),
                      ("dest_hsdata_ff", "xpm_handshake"), ("src_hsdata_ff", "xpm_handshake"),
                      ("arststages_ff", "xpm_async_rst"), ("syncstages_ff", "xpm_single"),
                      ("xpm_cdc_", "xpm")):
        if pat in cell:
            return kind
    return None


def classify(paths: dict[str, Any], rows: list[dict[str, Any]], waivers: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Classify every crossing. Returns ``{"crossings": [...], "summary": {...}, "unsafe": [...], "pass": bool}``."""
    waivers = waivers or []
    exc: dict[tuple[str, str, str], str] = {}          # (capture clock, capture register, launch register) -> exception text
    ruleids: dict[tuple[str, str, str], list[str]] = {}
    for r in rows:
        key = (r["dst_clk"], base(r["to"]), base(r["from"]))
        exc[key] = r["exception"]
        ruleids.setdefault(key, []).append(r["rule"])
    P = paths["paths"]
    for p in P:
        p["base"] = base(p["cell"])
        p["src_base"] = base(p["src"])
        k = (p["clk"], p["base"], p["src_base"])
        p["exception"] = exc.get(k, "")
        p["rules"] = ruleids.get(k, [])
        p["xpm"] = xpm_kind(p["cell"]) or xpm_kind(p["src"])
    groups: dict[tuple, list[dict]] = {}
    for p in P:
        if p["pin"] in ("D", "CE", "R", "S"):
            groups.setdefault((p["clk"], p["src_clk"], p["base"], p["src_base"]), []).append(p)
    for g in groups.values():
        for p in g:
            p["bits"] = len(g)
    # recognised single-bit synchroniser groups and constrained buses, per clock pair (evidence for U7)
    def is_chain(p): return p["ref"] in ("FDRE", "FDSE", "FDCE", "FDPE") and p["async_reg"] and p["chain"] >= 2
    pairs_ok = {(p["src_clk"], p["clk"]) for p in P if p["pin"] in ("D", "CE", "R", "S") and
                ((is_chain(p) and p.get("bits", 1) == 1) or (p["xpm"] and p["xpm"] != "xpm_async_rst") or
                 (is_chain(p) and "Max Delay Datapath Only" in p["exception"]))}
    verdict: dict[int, tuple[str, str, str]] = {}      # id(path) -> (class, rule, why)
    for p in P:
        i = id(p)
        if p["pin"] in ("CLR", "PRE"):
            if p["async_reg"] or p["xpm"] == "xpm_async_rst":
                verdict[i] = ("reset bridge", "", "asynchronous reset into an ASYNC_REG bridge flop")
            else:
                verdict[i] = ("unsafe", "U1", "an asynchronous reset from another clock domain clears a flop that is not an "
                              "ASYNC_REG reset-bridge flop (release is not synchronised to this clock)")
            continue
        if p["xpm"]:
            multi = p["xpm"] in ("xpm_gray", "xpm_handshake") or (p["xpm"] == "xpm_fifo" and p.get("bits", 1) > 1)
            if multi and "Max Delay Datapath Only" not in p["exception"]:
                verdict[i] = ("unsafe", "U5", f"{p['xpm']} bus without its Max Delay Datapath Only exception "
                              f"(exception: '{p['exception'] or 'none'}'): the macro's constraints did not reach the netlist")
            else:
                verdict[i] = ({"xpm_gray": "gray", "xpm_handshake": "handshake", "xpm_fifo": "fifo"}.get(p["xpm"], "xpm")
                              if multi else "xpm", "", f"{p['xpm']} instance"
                              + (f", exception '{p['exception']}'" if p["exception"] and p["exception"] != "None" else ""))
            continue
        if p["src_ref"].startswith("RAM") and not is_chain(p):
            ok = (p["src_clk"], p["clk"]) in pairs_ok
            verdict[i] = ("fifo", "", "RAM read of a FIFO, pointers cross on this clock pair") if ok else \
                ("unsafe", "U7", "data read from a RAM written in another clock domain, with no recognised pointer crossing")
            continue
        if not is_chain(p):
            hand = "Max Delay Datapath Only" in p["exception"] and (p["src_clk"], p["clk"]) in pairs_ok
            if hand and p["ref"] in ("FDRE", "FDSE", "FDCE", "FDPE"):
                verdict[i] = ("handshake", "", "hand-built handshake data path: max-delay exception, control crosses through a synchroniser")
            elif p["ref"] in ("FDRE", "FDSE", "FDCE", "FDPE") and not p["async_reg"]:
                verdict[i] = ("unsafe", "U2", "no synchroniser: the capture flop is not the first of an ASYNC_REG chain "
                              "(add (* ASYNC_REG = \"TRUE\" *) and a second flop, or use an XPM macro)")
            else:
                verdict[i] = ("unsafe", "U2", "no synchroniser: the ASYNC_REG chain behind this capture flop is shorter than 2")
            continue
        # a chain of >= 2 ASYNC_REG flops from here
        if p["nstart"] > 1:
            verdict[i] = ("unsafe", "U3", f"logic or {p['nstart']} source flops in front of the synchroniser (combine in the "
                          "source domain, register, then cross)")
        elif p["nloads"] > 1:
            verdict[i] = ("unsafe", "U4", f"the first stage drives {p['nloads']} loads: it must drive only the second stage "
                          "(one bit sampled by two flops can be seen as two values)")
        elif p.get("bits", 1) > 1:
            if "Max Delay Datapath Only" in p["exception"]:
                verdict[i] = ("gray", "", f"{p['bits']}-bit hand-built bus with a Max Delay Datapath Only exception "
                              "(coding unchecked: the simulation decides)")
            else:
                verdict[i] = ("unsafe", "U5", f"{p['bits']}-bit bus ({p['base']}) crossed through 1-bit synchronisers with no "
                              "Max Delay Datapath Only exception: the bits can arrive in different destination cycles "
                              "(use xpm_cdc_gray / a handshake / an asynchronous FIFO)")
        else:
            verdict[i] = ("synchroniser", "", f"ASYNC_REG chain of {p['chain']}")
    # U6 reconvergence among single-bit synchronisers on one clock pair
    singles = [p for p in P if verdict.get(id(p), ("",))[0] == "synchroniser"]
    for a in singles:
        for b in singles:
            if a is not b and a["clk"] == b["clk"] and a["src_clk"] == b["src_clk"] and a["base"] != b["base"] \
                    and a["src_base"] != b["src_base"] and set(a["sinks"]) & set(b["sinks"]):
                common = sorted(set(a["sinks"]) & set(b["sinks"]))
                verdict[id(a)] = ("unsafe", "U6", f"reconvergence: the outputs of {a['base']} and {b['base']} both reach "
                                  f"{', '.join(common[:3])} (separate synchronisers whose outputs are combined can disagree "
                                  "for a cycle; send one word through a handshake or FIFO)")
    out, unsafe = [], []
    for p in P:
        cls, rule, why = verdict[id(p)]
        w = next((x for x in waivers if re.search(x.get("cell", "^$"), p["cell"]) and str(x.get("reason", "")).strip()), None)
        rec = {"cell": p["cell"], "pin": p["pin"], "src": p["src"], "src_clock": p["src_clk"], "dst_clock": p["clk"],
               "class": cls, "rule": rule, "why": why, "exception": p["exception"], "report_cdc_rules": p["rules"]}
        if cls == "unsafe" and w:
            rec["class"], rec["waived"] = "waived", w["reason"]
        elif cls == "unsafe":
            unsafe.append(rec)
        out.append(rec)
    summary: dict[str, int] = {}
    for r in out:
        summary[r["class"]] = summary.get(r["class"], 0) + 1
    for e in paths.get("errors", []):         # a pin the Tcl could not analyse is a crossing nobody checked
        rec = {"cell": e.split("|")[0], "pin": e.split("|")[1] if "|" in e else "", "src": "", "src_clock": "", "dst_clock": "",
               "class": "unsafe", "rule": "U0", "why": "flow/cdc_paths.tcl could not analyse this pin: " + e[:200],
               "exception": "", "report_cdc_rules": []}
        unsafe.append(rec)
        out.append(rec)
        summary["unsafe"] = summary.get("unsafe", 0) + 1
    return {"crossings": out, "summary": summary, "unsafe": unsafe, "n_crossings": len(out),
            "clocks": paths["clocks"], "pass": not unsafe}


def evaluate(paths_file: Path, cdc_file: Path | None, waivers: list[dict[str, str]] | None = None) -> dict[str, Any]:
    paths = parse_paths(paths_file.read_text(errors="replace"))
    rows = parse_cdc_rows(cdc_file.read_text(errors="replace")) if cdc_file and cdc_file.exists() else []
    return classify(paths, rows, waivers)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build_dir", help="a build directory holding cdc_paths_synth.rpt and cdc_synth.rpt")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    d = Path(a.build_dir)
    rep = evaluate(d / "cdc_paths_synth.rpt", d / "cdc_synth.rpt")
    print(f"{rep['n_crossings']} asynchronous crossing endpoints: {rep['summary']}")
    for u in rep["unsafe"]:
        print(f"  UNSAFE {u['rule']} {u['src']} -> {u['cell']}: {u['why']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2) + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
