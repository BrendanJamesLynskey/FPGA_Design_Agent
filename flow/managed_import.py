#!/usr/bin/env python3
"""Importing an externally produced module into a managed project (brief 102, stage 1).

    python3 flow/managed_import.py check  designs/<name> [--component C] [--eqy] [--sim] [--out FILE]
    python3 flow/managed_import.py boundary designs/<name> <build dir> [--out FILE]
    python3 flow/managed_import.py record-build designs/<name> <build dir>      (gates.json clean -> 'built' evidence)

``check`` runs the import checks on every ``level: netlist`` component of the design's ``project.yaml`` (or one):

1. **interface**: the netlist's port list (read from the EDIF, or the Verilog netlist) against the contract's ``interface.ports``;
2. **licence and provenance**: origin, version, licence, and the SHA-256 of the delivered file recorded and matching;
3. **simulation** (``--sim``): the functional netlist is simulated (Icarus) against the component's ``tests`` vectors model, for a
   netlist from Yosys with the public behavioural Xilinx cell models of the Yosys distribution (``cells_sim.v``), for one from
   Vivado with the ``write_verilog -mode funcsim`` text (:func:`funcsim_tcl`);
4. **equivalence** (``--eqy``): where the component has ``reference_rtl``, ``eqy`` proves the RTL against the netlist (registers
   matched by name). A planted fault must fail it (the tests plant one).

A passing run writes ``build/managed/evidence/<component>.json`` (``verified``), which the trust label is computed from.

``boundary`` reads a finished build's reports: the ``report_cdc`` rows of ``cdc_synth.rpt`` that touch a component's instance
(a crossing at the boundary the contract does not allow), and the boundary timing budgets (:func:`budget_tcl` run on the
post-route checkpoint: ``flow/managed_boundary.tcl``). Both write ``build/managed/boundary.json``.

The slot itself (the black box the netlist fills) is made by ``flow/prepare.py`` from build.yaml ``netlists:``;
:func:`flow.prepare.netlist_tcl` is the Tcl it emits.
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
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.core import managed as M  # noqa: E402
from flow.prepare import netlist_tcl  # noqa: E402,F401  (the Tcl for build.yaml netlists: lives with the other prepare steps)


# --- reading a netlist's interface ----------------------------------------------------------------------------------

def _balanced(text: str, start: int) -> str:
    """The parenthesised group that begins at ``text[start] == '('`` (EDIF strings with parentheses are not used by the writers we read)."""
    depth = 0
    for i in range(start, len(text)):
        depth += (text[i] == "(") - (text[i] == ")")
        if depth == 0:
            return text[start:i + 1]
    return text[start:]


def _edif_ports(text: str, module: str) -> list[dict[str, Any]]:
    """Ports of ``module``'s interface in an EDIF netlist: ``(port name (direction INPUT))`` and
    ``(port (array (rename name "name[7:0]") 8) (direction OUTPUT))``; a bus is one port named by its base name."""
    m = re.search(rf"\(cell\s+(?:\(rename\s+\S+\s+\"{re.escape(module)}\"\)|{re.escape(module)})\s", text)
    if not m:
        return []
    cell = _balanced(text, m.start())
    i = cell.find("(interface")
    if i < 0:
        return []
    body = _balanced(cell, i)
    ports = []
    for pm in re.finditer(r"\(port\s+(?:\(array\s+(?:\(rename\s+\S+\s+\"(?P<qa>[^\"]+)\"\)|(?P<na>\S+))\s+(?P<w>\d+)\)|"
                          r"\(rename\s+\S+\s+\"(?P<qn>[^\"]+)\"\)|(?P<n>[^\s()]+))\s*\(direction\s+(?P<d>INPUT|OUTPUT|INOUT)\)", body):
        raw = pm.group("qa") or pm.group("na") or pm.group("qn") or pm.group("n")
        name = re.sub(r"\[.*\]$", "", raw)
        if pm.group("n") or pm.group("qn"):                    # a scalar port 'name[3]' of a bus written bit by bit
            m3 = re.match(r".*\[(\d+)\]$", raw)
            if m3:
                prev = next((q for q in ports if q["name"] == name), None)
                if prev:
                    prev["width"] = max(prev["width"], int(m3.group(1)) + 1)
                    continue
                ports.append({"name": name, "dir": pm.group("d").lower(), "width": int(m3.group(1)) + 1})
                continue
        ports.append({"name": name, "dir": pm.group("d").lower(), "width": int(pm.group("w")) if pm.group("w") else 1})
    return ports


def netlist_ports(path: Path, module: str) -> list[dict[str, Any]]:
    """Ports of ``module`` in a delivered netlist: EDIF (``.edf``/``.edn``) or Verilog (``.v``, ANSI or the old
    ``module m(a, b); input [7:0] a;`` style Yosys writes)."""
    text = path.read_text(errors="replace")
    if path.suffix.lower() in (".edf", ".edn", ".edif"):
        return _edif_ports(text, module)
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    ansi = M.parse_module_ports(text, module)
    if ansi:
        return ansi
    m = re.search(rf"\bmodule\s+{re.escape(module)}\s*\((.*?)\)\s*;(.*?)\bendmodule", text, re.S)
    if not m:
        return []
    out, seen = [], set()
    for d, rng, names in re.findall(r"\b(input|output|inout)\b\s*(?:wire|reg|logic)?\s*(\[[^\]]+\])?\s*([\w\s,\\\[\]]+?);", m.group(2)):
        w = 1
        if rng:
            hi, lo = re.findall(r"\d+", rng)[:2]
            w = abs(int(hi) - int(lo)) + 1
        for n in (x.strip() for x in names.split(",")):
            if n and n not in seen:
                seen.add(n)
                out.append({"name": n, "dir": d, "width": w})
    return out


def check_interface(project: M.Project, comp: M.Component) -> list[str]:
    """The delivered netlist's ports against the contract (empty: they agree)."""
    f = project.design / comp.netlist["file"]
    got = netlist_ports(f, comp.module or "")
    if not got:
        return [f"no module {comp.module!r} with ports found in {comp.netlist['file']}"]
    if not comp.interface.get("ports"):
        return ["the component has no interface contract (interface.ports)"]
    return M.interface_diff(comp.interface["ports"], got)


def licence_problems(comp: M.Component) -> list[str]:
    prov = comp.provenance
    out = [f"provenance.{k} is not recorded" for k in ("origin", "version", "licence") if not prov.get(k)]
    return out


# --- the build: black-box slot and netlist --------------------------------------------------------------------------------

def funcsim_tcl(checkpoint: str, out_v: str, sdf: str | None = None) -> str:
    """Tcl that writes the functional-simulation netlist of a checkpoint (UG835 ``write_verilog -mode funcsim``): the post-synthesis
    or post-route design as UNISIM primitives, for simulation with AMD's UNISIM library. The imported block's behaviour in the
    whole design is simulated from this."""
    return "\n".join([f"open_checkpoint {{{checkpoint}}}", f"write_verilog -force -mode funcsim {{{out_v}}}",
                      *([f"write_sdf -force {{{sdf}}}"] if sdf else []), "close_design", ""])


def budget_tcl(instance: str, budgets: list[dict[str, Any]], checkpoint: str | None = None) -> str:
    """Tcl for the boundary timing budgets (``flow/managed_import.py budget-tcl``), run on a routed checkpoint. Each budget is
    ``{name, dir: out|in, max_ns}``: ``out`` is the worst path from a flip-flop inside the slot to a flip-flop outside it, ``in``
    the reverse; the result is one ``BUDGET|name|datapath delay|slack`` line per budget (parse_budgets reads them)."""
    inst = instance.strip("/")
    lines = ([f"open_checkpoint {{{checkpoint}}}"] if checkpoint else []) + [
        f"set fda_in  [get_cells -hier -quiet -filter {{IS_SEQUENTIAL && NAME =~ {inst}/*}}]",
        f"set fda_out [get_cells -hier -quiet -filter {{IS_SEQUENTIAL && NAME !~ {inst}/*}}]",
        "proc fda_budget {name from to} {",
        "    set p [get_timing_paths -max_paths 1 -nworst 1 -from $from -to $to]",
        "    if {$p eq \"\"} { puts \"BUDGET|$name|none|none\"; return }",
        "    puts \"BUDGET|$name|[get_property DATAPATH_DELAY $p]|[get_property SLACK $p]\"", "}"]
    for b in budgets:
        a, z = ("$fda_in", "$fda_out") if b["dir"] == "out" else ("$fda_out", "$fda_in")
        lines.append(f"fda_budget {{{b['name']}}} {a} {z}")
    return "\n".join(lines) + "\n"


# --- simulation ----------------------------------------------------------------------------------------------------------

def flatten_netlist(netlist_v: Path, top: str, out_v: Path, cells_sim: Path | None = None) -> Path:
    """A Yosys netlist of Xilinx primitives as plain flat Verilog (the primitives' public behavioural models from the Yosys
    distribution, ``-wb`` flatten because they are whitebox library cells). Simulation and eqy read this."""
    cad = os.environ.get("FDA_OSS_CAD")
    env = {**os.environ, "PATH": (f"{cad}/bin:" if cad else "") + os.environ["PATH"]}
    cs = cells_sim or Path(subprocess.run(["yosys-config", "--datdir"], capture_output=True, text=True, env=env).stdout.strip()) / "xilinx" / "cells_sim.v"
    script = (f"read_verilog -sv {netlist_v}; read_verilog -sv -D_EXPLICIT_CARRY {cs}; hierarchy -top {top}; proc; flatten -wb; "
              f"opt_clean -purge; write_verilog -noattr {out_v}")
    out_v.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True, env=env)
    if r.returncode or not out_v.is_file():
        raise RuntimeError("yosys could not flatten the netlist: " + (r.stderr or r.stdout)[-400:])
    return out_v


def _sim_vectors(width: int, seed: int = 1, n: int = 400) -> list[tuple[int, int, int, int]]:
    import random
    rng = random.Random(seed)
    return [((1 if i == 0 or (i % 37 == 0) else 0), rng.getrandbits(1), rng.getrandbits(1) if i % 5 else 1, rng.getrandbits(width))
            for i in range(n)]


def crc32_model(vectors: list[tuple[int, int, int, int]], width: int = 16) -> list[int]:
    """The reference model of the CRC block (rst, init, en, word): the IEEE 802.3 CRC-32 register over ``width``-bit words, the
    update of b96_pkg.crc_upd (reflected, polynomial 04C11DB7, register starts and resets at FFFFFFFF). zlib.crc32 is its complement."""
    crc, out = 0xFFFFFFFF, []
    for rst, init, en, d in vectors:
        if rst:
            crc = 0xFFFFFFFF
        elif en:
            r = 0xFFFFFFFF if init else crc
            for i in range(width):
                fb = (r ^ (d >> i)) & 1
                r >>= 1
                if fb:
                    r ^= 0xEDB88320
            crc = r
        out.append(crc)
    return out


def simulate_crc_netlist(flat_v: Path, top: str, work: Path, width: int = 16) -> dict[str, Any]:
    """Simulate a CRC32 block netlist (ports clk, rst, init, en, d[width-1:0], crc[31:0]) with Icarus against the reference model."""
    work.mkdir(parents=True, exist_ok=True)
    vec = _sim_vectors(width)
    exp = crc32_model(vec, width)
    hx = (width + 3) // 4
    tb = ["`timescale 1ns/1ps", "module tb;", f"  reg clk = 0, rst = 0, init = 0, en = 0; reg [{width - 1}:0] d = 0; wire [31:0] crc; integer bad = 0;",
          f"  {top} dut (.clk(clk), .rst(rst), .init(init), .en(en), .d(d), .crc(crc));", "  always #5 clk = ~clk;",
          f"  task step(input r, input i, input e, input [{width - 1}:0] w, input [31:0] want);",
          "    begin rst = r; init = i; en = e; d = w; @(posedge clk); #1; if (crc !== want) begin bad = bad + 1; end end",
          "  endtask", "  initial begin @(negedge clk);"]
    tb += [f"    step({r}, {i}, {e}, {width}'h{d:0{hx}x}, 32'h{x:08x});" for (r, i, e, d), x in zip(vec, exp)]
    tb += ["    $display(\"RESULT bad=%0d of %0d\", bad, " + str(len(vec)) + "); $finish;", "  end", "endmodule"]
    (work / "tb.sv").write_text("\n".join(tb) + "\n")
    c = subprocess.run(["iverilog", "-g2012", "-o", str(work / "sim.vvp"), str(work / "tb.sv"), str(flat_v)], capture_output=True, text=True)
    if c.returncode:
        return {"passed": False, "error": c.stderr[-300:]}
    r = subprocess.run(["vvp", str(work / "sim.vvp")], capture_output=True, text=True, timeout=300)
    m = re.search(r"RESULT bad=(\d+) of (\d+)", r.stdout)
    return {"passed": bool(m and m.group(1) == "0"), "mismatches": int(m.group(1)) if m else None,
            "vectors": len(vec), "model": f"IEEE 802.3 CRC-32 over {width}-bit words (flow/managed_import.crc32_model)"}


# --- equivalence ---------------------------------------------------------------------------------------------------------

EQY_STRATEGY = "[strategy sby]\nuse sby\nengine abc pdr\ndepth 5\n"


def eqy_prove(gold_files: list[Path], gate_v: Path, top: str, work: Path, strategy: str = EQY_STRATEGY, timeout: int = 900) -> dict[str, Any]:
    """Prove ``gold_files`` (the RTL) equivalent to ``gate_v`` (a flat netlist) with eqy; registers are matched by name, so a
    netlist that renames or retimes registers needs a stronger strategy. Equivalent is only a pass when eqy says it proved."""
    cad = os.environ.get("FDA_OSS_CAD")
    env = {**os.environ, "PATH": (f"{cad}/bin:" if cad else "") + os.environ["PATH"]}
    if not shutil.which("eqy", path=env["PATH"]):
        return {"ran": False, "equivalent": None, "why": "eqy not found (set FDA_OSS_CAD to the OSS CAD Suite folder)"}
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    names = []
    for i, g in enumerate(gold_files):
        shutil.copy(g, work / f"gold{i}.sv")
        names.append(f"gold{i}.sv")
    shutil.copy(gate_v, work / "gate.v")
    (work / "eq.eqy").write_text("[gold]\n" + "".join(f"read_verilog -sv {n}\n" for n in names) + f"prep -top {top}\n\n"
                                 f"[gate]\nread_verilog -sv gate.v\nprep -top {top}\n\n" + strategy)
    t0 = time.time()
    try:
        p = subprocess.run(["eqy", "-f", "eq.eqy"], cwd=work, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ran": True, "equivalent": None, "why": f"eqy did not finish in {timeout} s", "seconds": timeout}
    out = p.stdout + p.stderr
    (work / "eqy.log").write_text(out)
    eq = "Successfully proved designs equivalent" in out
    return {"ran": True, "equivalent": eq, "seconds": round(time.time() - t0, 1), "returncode": p.returncode,
            "unproven": sorted(set(re.findall(r"Failed to prove equivalence of (\S+)", out))), "strategy": strategy.replace("\n", "; "),
            "eqy_log_tail": out.strip().splitlines()[-3:]}


def plant_fault(netlist_v: Path, out_v: Path) -> str:
    """A copy of a Yosys netlist with one LUT INIT bit flipped: what eqy must reject. Returns what was changed."""
    text = netlist_v.read_text()
    m = re.search(r"(\.INIT\((\d+)'h([0-9a-fA-F]+)\))", text)
    if not m:
        raise ValueError("no LUT INIT in the netlist")
    width, val = int(m.group(2)), int(m.group(3), 16)
    new = val ^ (1 << (width // 2))
    out_v.write_text(text.replace(m.group(1), f".INIT({width}'h{new:0{(width + 3) // 4}x})", 1))
    return f"INIT {width}'h{val:x} -> {width}'h{new:x} (one bit)"


# --- boundary checks -----------------------------------------------------------------------------------------------------

def boundary_cdc(cdc_report: str, instance: str) -> dict[str, Any]:
    """The ``report_cdc -details`` rows of a build that start or end inside ``instance`` (a crossing at the slot's boundary)."""
    inst = instance.strip("/")
    rows = []
    for line in cdc_report.splitlines():
        m = re.match(r"\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+(.*?)\s{2,}(\d+)\s+.*?\s{2,}(\S+)\s+(\S+)\s*$", line)
        if m and (m.group(5).startswith(inst + "/") or m.group(6).startswith(inst + "/")):
            rows.append({"rule": m.group(1), "severity": m.group(2), "from": m.group(5), "to": m.group(6)})
    return {"instance": inst, "rows": rows, "clean": not any(r["severity"] in ("Critical", "Warning") for r in rows)}


def parse_budgets(text: str) -> list[dict[str, Any]]:
    out = []
    for name, delay, slack in re.findall(r"^BUDGET\|([^|]+)\|([^|]+)\|([^|\n]+)$", text, re.M):
        out.append({"name": name, "delay_ns": None if delay == "none" else float(delay), "slack_ns": None if slack == "none" else float(slack)})
    return out


def check_budgets(declared: list[dict[str, Any]], measured: list[dict[str, Any]]) -> list[str]:
    """Each declared budget (``name``, ``max_ns``) against the measured path delay; a budget with no measured path is a problem."""
    by = {m["name"]: m for m in measured}
    out = []
    for b in declared:
        m = by.get(b["name"])
        if m is None or m["delay_ns"] is None:
            out.append(f"budget {b['name']}: no path measured")
        elif m["delay_ns"] > b["max_ns"]:
            out.append(f"budget {b['name']}: {m['delay_ns']:.3f} ns exceeds {b['max_ns']} ns")
    return out


def boundary_check(project: M.Project, build_dir: Path, budgets_text: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {"components": {}}
    cdc = (build_dir / "cdc_synth.rpt")
    for c in project.components:
        if c.level not in ("netlist", "placed_routed") or not c.instance:
            continue
        r: dict[str, Any] = {"cdc": boundary_cdc(cdc.read_text(), c.instance) if cdc.is_file() else {"clean": None, "why": "no cdc_synth.rpt"}}
        decl = c.interface.get("timing_budgets") or []
        r["budgets"] = {"declared": decl, "measured": parse_budgets(budgets_text or ""), "problems": check_budgets(decl, parse_budgets(budgets_text or "")) if decl else []}
        res["components"][c.name] = r
    res["clean"] = all(v["cdc"]["clean"] is True and not v["budgets"]["problems"] for v in res["components"].values())
    return res


# --- the import check -----------------------------------------------------------------------------------------------------

def import_check(design: Path, only: str | None = None, run_eqy: bool = False, run_sim: bool = False,
                 work: Path | None = None) -> dict[str, Any]:
    project = M.load(design)
    if project is None:
        raise SystemExit(f"{design}: no project.yaml")
    work = work or design / "build" / "managed" / "import"
    rep: dict[str, Any] = {"design": design.name, "components": {}}
    for c in project.components:
        if c.level != "netlist" or (only and c.name != only):
            continue
        r: dict[str, Any] = {"interface": check_interface(project, c), "licence": licence_problems(c),
                             "sha256_matches": c.provenance.get("sha256") == M.sha256_file(project.design / c.netlist["file"])}
        nl = project.design / c.netlist["file"]
        flat = None
        if run_sim or run_eqy:
            net_v = project.design / c.netlist["sim_file"] if c.netlist.get("sim_file") else nl
            try:
                flat = flatten_netlist(net_v, c.module, work / c.name / "flat.v")
            except (RuntimeError, OSError) as e:
                r["flatten_error"] = str(e)
        if run_sim and flat:
            dport = next((p for p in c.interface.get("ports", []) if p["name"] == "d"), {"width": 16})
            r["simulation"] = simulate_crc_netlist(flat, c.module, work / c.name / "sim", int(dport["width"]))
        if run_eqy and flat and c.reference_rtl:
            r["eqy"] = eqy_prove([project.design / p for p in c.reference_rtl], flat, c.module, work / c.name / "eqy")
        ok = (not r["interface"] and not r["licence"] and r["sha256_matches"]
              and (not run_sim or r.get("simulation", {}).get("passed") is True)
              and (not run_eqy or (bool(c.reference_rtl) and r.get("eqy", {}).get("equivalent") is True)))
        r["passed"] = ok
        rep["components"][c.name] = r
        if ok and run_sim:                                       # only a run that executed the tests is evidence of 'verified'
            M.write_evidence(project, c, "verified", {"passed": True, "tests": ["interface", "licence", "sha256"] + ["simulation"] +
                                                      (["eqy"] if run_eqy and c.reference_rtl else [])})
    rep["passed"] = all(v["passed"] for v in rep["components"].values())
    return rep


def record_build(design: Path, build_dir: Path) -> dict[str, Any]:
    """Record a finished build as ``built`` evidence for every component: only when gates.json says every gate passed and the build's source
    stamp is the one this tree would get now (so the evidence is of this content). Written by the flow, never by the agent's tools."""
    project = M.load(design)
    g = json.loads((build_dir / "gates.json").read_text())
    failed = sorted(k for k, v in (g.get("gates") or {}).items() if v is not True)
    clean = bool(g.get("pass")) and not failed
    out = {"gates_clean": clean, "failed_gates": failed, "build_stamp": g.get("build_stamp"), "build_dir": str(build_dir.name)}
    for c in project.components:
        if c.ownership != "excluded":                       # the label of an excluded part is the owner's business, not the agent's
            M.write_evidence(project, c, "built", out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("design", type=Path)
    c.add_argument("--component")
    c.add_argument("--eqy", action="store_true")
    c.add_argument("--sim", action="store_true")
    c.add_argument("--out", type=Path)
    b = sub.add_parser("boundary")
    b.add_argument("design", type=Path)
    b.add_argument("build_dir", type=Path)
    b.add_argument("--budgets", type=Path, help="the output of flow/managed_boundary.tcl")
    b.add_argument("--out", type=Path)
    r_ = sub.add_parser("record-build", help="record a finished build's gates as 'built' evidence")
    r_.add_argument("design", type=Path)
    r_.add_argument("build_dir", type=Path)
    t = sub.add_parser("budget-tcl", help="write the Tcl that measures the boundary timing budgets of a routed checkpoint")
    t.add_argument("design", type=Path)
    t.add_argument("checkpoint", help="the routed checkpoint to open, or - for the Tcl of a session that already has the design open")
    t.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    design = a.design.resolve()
    if a.cmd == "record-build":
        rep = record_build(design, a.build_dir.resolve())
        print(json.dumps(rep, indent=1))
        return 0 if rep["gates_clean"] else 1
    if a.cmd == "budget-tcl":
        proj = M.load(design)
        c = next(c for c in proj.components if c.level in ("netlist", "placed_routed") and c.instance and c.interface.get("timing_budgets"))
        a.out.write_text(budget_tcl(c.instance, c.interface["timing_budgets"], None if a.checkpoint == "-" else a.checkpoint))
        print(f"wrote {a.out}")
        return 0
    if a.cmd == "check":
        rep = import_check(design, a.component, a.eqy, a.sim)
    else:
        rep = boundary_check(M.load(design), a.build_dir.resolve(), a.budgets.read_text() if a.budgets else None)
        (design / M.MANAGED_DIR).mkdir(parents=True, exist_ok=True)
        (design / M.MANAGED_DIR / "boundary.json").write_text(json.dumps(rep, indent=1) + "\n")
    text = json.dumps(rep, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")
    print(text)
    return 0 if rep.get("passed", rep.get("clean")) else 1


if __name__ == "__main__":
    sys.exit(main())
