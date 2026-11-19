#!/usr/bin/env python3
"""Placed-and-routed components of a managed project (brief 102, stage 2): the import check and the placement evidence.

    python3 flow/managed_placed.py check   designs/<d> [--component C] [--facts FILE] [--funcsim FILE] [--sim]
    python3 flow/managed_placed.py compare designs/<d> <work dir> [--component C] [--out FILE]

``check`` runs the import checks on a ``level: placed_routed`` component, whose file is a routed checkpoint made outside the project and
locked with ``lock_design -level routing``:

1. **interface**: the checkpoint's ports against the contract (``flow/managed_placed_check.tcl`` reads them in Vivado);
2. **licence and provenance**: origin, version, licence, and the file's SHA-256 recorded and matching;
3. **lock**: every placeable leaf cell has a fixed location and a fixed BEL, every routed signal net has fixed routing, no net is unrouted;
4. **footprint**: every slice the block occupies is inside the manifest's keep-out region (``placement.region``);
5. **simulation** (``--sim``): the checkpoint's functional netlist (``write_verilog -mode funcsim``) against the supplier's RTL, cycle by cycle
   on the same random stimulus (Icarus, with Yosys' public models of the Xilinx primitives).

``compare`` reads the runs of ``flow/managed_placement_run.tcl`` for each placement tried (the block at its delivered site and relocated by
RapidWright to others, the rest of the design placed and routed by Vivado around it) and writes the **placement evidence**: for each placement
whether Vivado left the block alone (cells on their sites, every internal net's route string unchanged), whether the relocated routing has the
same shape as the delivered one, how far each block-internal path delay is from the delivered placement's (Vivado's ``report_timing``, in
picoseconds, endpoint by endpoint), the boundary budgets, and, when funcsim netlists are given, whether eqy proves the relocated netlist equal to
the delivered one. ``passed`` needs every placement to satisfy all of these within the manifest's ``placement.timing_tolerance_ps``. The label
``built`` of the component needs this evidence (``agent.core.managed.trust``).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.core import managed as M  # noqa: E402
from flow import managed_import as MI  # noqa: E402


# --- the import check ---------------------------------------------------------------------------------------------------

def parse_facts(text: str) -> dict[str, Any]:
    """The lines of ``managed_placed_check.tcl`` as a dictionary."""
    f: dict[str, Any] = {"ports": [], "sites": {}}
    for line in text.splitlines():
        t = line.strip().split("|")
        if t[0] in ("VIVADO", "PART", "TOP") and len(t) == 2:
            f[t[0].lower()] = t[1]
        elif t[0] == "PORT" and len(t) == 4:
            f["ports"].append({"name": t[1], "dir": {"in": "input", "out": "output", "inout": "inout"}.get(t[2], t[2]), "width": int(t[3])})
        elif t[0] == "CELLS" and len(t) == 5:
            f["cells"] = dict(zip(("leaf", "loc_fixed", "bel_fixed", "unplaced"), map(int, t[1:])))
        elif t[0] == "NETS" and len(t) == 5:
            f["nets"] = dict(zip(("signal", "routed", "route_fixed", "unrouted"), map(int, t[1:])))
        elif t[0] == "SITE" and len(t) == 3:
            f["sites"][t[1]] = int(t[2])
        elif t[0] == "RECT" and len(t) == 5:
            f["rect"] = tuple(int(v) for v in t[1:])
    return f


def lock_problems(facts: dict[str, Any]) -> list[str]:
    """What is not locked in a checkpoint's facts (empty: placement and routing are locked and complete)."""
    out = []
    c, n = facts.get("cells"), facts.get("nets")
    if not c or not n:
        return ["the checkpoint's cell and net facts were not read"]
    if c["unplaced"]:
        out.append(f"{c['unplaced']} cells are unplaced")
    if c["loc_fixed"] != c["leaf"]:
        out.append(f"{c['leaf'] - c['loc_fixed']} of {c['leaf']} cells have no fixed location (lock_design -level routing was not applied)")
    if c["bel_fixed"] != c["leaf"]:
        out.append(f"{c['leaf'] - c['bel_fixed']} of {c['leaf']} cells have no fixed BEL")
    if n["unrouted"]:
        out.append(f"{n['unrouted']} signal nets are unrouted")
    if n["route_fixed"] != n["routed"]:
        out.append(f"{n['routed'] - n['route_fixed']} of {n['routed']} routed nets have routing that is not fixed")
    return out


def footprint_problems(comp: M.Component, facts: dict[str, Any]) -> list[str]:
    rect = facts.get("rect")
    if rect is None:
        return ["no slice sites were read from the checkpoint"]
    region = M.slice_rect(comp.placement["region"])
    if not (region[0] <= rect[0] and region[1] <= rect[1] and rect[2] <= region[2] and rect[3] <= region[3]):
        return [f"the block occupies SLICE_X{rect[0]}Y{rect[1]}:SLICE_X{rect[2]}Y{rect[3]}, outside the declared keep-out region {comp.placement['region']}"]
    return []


def simulate_vs_reference(funcsim_v: Path, reference: list[Path], top: str, work: Path, n: int = 600, seed: int = 1) -> dict[str, Any]:
    """The block's functional netlist against the supplier's RTL, cycle by cycle on the same random stimulus (ports clk, rst, din, dout).
    Both are simulated in one Icarus run: the netlist's top is renamed ``<top>_net`` after Yosys flattens it with the Xilinx primitive models."""
    import random
    import subprocess
    work.mkdir(parents=True, exist_ok=True)
    flat = MI.flatten_netlist(funcsim_v, top, work / "flat.v")
    text = re.sub(rf"\bmodule\s+{re.escape(top)}\b", f"module {top}_net", flat.read_text())
    (work / "flat_net.v").write_text(text)
    rng = random.Random(seed)
    vec = [(1 if i < 4 or i % 211 == 0 else 0, rng.getrandbits(1)) for i in range(n)]
    tb = ["`timescale 1ns/1ps", "module tb;", "  reg clk = 0, rst = 0, din = 0; wire a, b; integer bad = 0, ones = 0;",
          f"  {top} ref_m (.clk(clk), .rst(rst), .din(din), .dout(a));", f"  {top}_net net_m (.clk(clk), .rst(rst), .din(din), .dout(b));",
          "  always #5 clk = ~clk;", "  task step(input r, input d); begin rst = r; din = d; @(posedge clk); #1; if (a !== b) bad = bad + 1; if (a === 1'b1) ones = ones + 1; end endtask",
          "  initial begin @(negedge clk);"]
    tb += [f"    step({r}, {d});" for r, d in vec]
    tb += [f'    $display("RESULT bad=%0d ones=%0d of {n}", bad, ones); $finish;', "  end", "endmodule"]
    (work / "tb.sv").write_text("\n".join(tb) + "\n")
    cmd = ["iverilog", "-g2012", "-o", str(work / "sim.vvp"), str(work / "tb.sv"), str(work / "flat_net.v"), *map(str, reference)]
    c = subprocess.run(cmd, capture_output=True, text=True)
    if c.returncode:
        return {"passed": False, "error": c.stderr[-400:]}
    r = subprocess.run(["vvp", str(work / "sim.vvp")], capture_output=True, text=True, timeout=600)
    m = re.search(r"RESULT bad=(\d+) ones=(\d+) of (\d+)", r.stdout)
    return {"passed": bool(m and m.group(1) == "0" and int(m.group(2)) > 0), "mismatches": int(m.group(1)) if m else None, "cycles": n,
            "cycles_with_dout_high": int(m.group(2)) if m else None,
            "model": "the supplier's RTL (reference_rtl) on the same stimulus; a run where dout never goes high does not pass"}


def check_placed(design: Path, only: str | None = None, facts_file: Path | None = None, funcsim: Path | None = None, run_sim: bool = False,
                 work: Path | None = None) -> dict[str, Any]:
    """The import check of every placed_routed component (see the module docstring). A passing run that executed the simulation writes the
    component's ``verified`` evidence."""
    project = M.load(design)
    if project is None:
        raise SystemExit(f"{design}: no project.yaml")
    work = work or design / "build" / "managed" / "import"
    rep: dict[str, Any] = {"design": design.name, "components": {}}
    for c in project.components:
        if c.level != "placed_routed" or (only and c.name != only):
            continue
        ck = project.design / c.netlist["file"]
        w = work / c.name
        w.mkdir(parents=True, exist_ok=True)
        facts_path = facts_file or w / "facts.txt"
        fs = funcsim or w / "funcsim.v"
        if facts_file is None:
            run_vivado_check(ck, facts_path, fs if run_sim else None)
        facts = parse_facts(facts_path.read_text())
        got = [p for p in facts["ports"]]
        r: dict[str, Any] = {"interface": M.interface_diff(c.interface["ports"], got) if c.interface.get("ports") else ["no interface contract"],
                             "licence": MI.licence_problems(c), "sha256_matches": c.provenance.get("sha256") == M.sha256_file(ck),
                             "lock": lock_problems(facts), "footprint": footprint_problems(c, facts), "facts": {k: v for k, v in facts.items() if k != "ports"}}
        if run_sim:
            r["simulation"] = simulate_vs_reference(fs, [project.design / p for p in c.reference_rtl], c.module or "", w / "sim")
        ok = (not r["interface"] and not r["licence"] and r["sha256_matches"] and not r["lock"] and not r["footprint"]
              and (not run_sim or r["simulation"].get("passed") is True))
        r["passed"] = ok
        rep["components"][c.name] = r
        if ok and run_sim:
            M.write_evidence(project, c, "verified", {"passed": True, "tests": ["interface", "licence", "sha256", "lock", "footprint", "simulation"]})
    rep["passed"] = all(v["passed"] for v in rep["components"].values())
    return rep


def run_vivado_check(dcp: Path, out_txt: Path, funcsim: Path | None) -> None:
    import os
    import subprocess
    from flow import version_pin
    env = {**os.environ, "FDA_PR_DCP": str(dcp), "FDA_PR_OUT": str(out_txt), "FDA_PR_FUNCSIM": str(funcsim or "")}
    r = subprocess.run([version_pin.vivado_path(), "-mode", "batch", "-nojournal", "-nolog", "-source", str(ROOT / "flow" / "managed_placed_check.tcl")],
                       cwd=out_txt.parent, env=env, capture_output=True, text=True, timeout=1800)
    if r.returncode or not out_txt.is_file():
        raise RuntimeError("Vivado could not read the checkpoint: " + (r.stdout + r.stderr)[-400:])


# --- the placement evidence ------------------------------------------------------------------------------------------------

def read_lines(path: Path) -> dict[str, tuple[str, ...]]:
    """``name|a|b...`` lines as {name: (a, b, ...)}: the cell-site files (site, BEL, fixed) and the route files (fixed, route)."""
    out = {}
    for line in path.read_text().splitlines():
        name, _, rest = line.partition("|")
        if name:
            out[name] = tuple(rest.split("|", 1)) if "|" in rest and path.name.find("routes") >= 0 else tuple(rest.split("|"))
    return out


_COORD = re.compile(r"X\d+Y\d+")


def shape(route: str) -> str:
    """A route string with every tile and site coordinate removed: two routes with the same shape use the same sequence of nodes
    relative to their start, wherever on the device they are."""
    return _COORD.sub("X#Y#", route)


def digest(items: list[str]) -> str:
    h = hashlib.sha256()
    for i in items:
        h.update(i.encode() + b"\n")
    return h.hexdigest()[:16]


def read_block_csv(path: Path) -> dict[str, float]:
    return {r["endpoint"]: float(r["data_path_delay_ns"]) for r in csv.DictReader(path.open())}


def observed_rect(sites_file: Path) -> tuple[int, int, int, int] | None:
    xs, ys = [], []
    for site in (v[0] for v in read_lines(sites_file).values()):
        m = re.match(r"SLICE_X(\d+)Y(\d+)$", site)
        if m:
            xs.append(int(m.group(1)))
            ys.append(int(m.group(2)))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def compare_placements(runs: list[dict[str, Any]], tolerance_ps: int, declared_budgets: list[dict[str, Any]] | None = None,
                       declared_region: str | None = None) -> dict[str, Any]:
    """``runs[0]`` is the delivered placement. Each run: ``tag``, ``dir`` (where the run's files are), ``prefix`` (their common name),
    optionally ``eqy`` (the equivalence result against runs[0]), ``budgets`` (the run's log, with its BUDGET lines), ``dump`` (the text of
    ``managed_block_dump.tcl`` run on the run's written checkpoint) and ``note``. ``declared_region`` is the manifest's keep-out for the
    delivered placement; a relocated run's keep-out is that region moved by the block's own shift."""
    base = None
    out: dict[str, Any] = {"tolerance_ps": tolerance_ps, "placements": {}}
    for run in runs:
        d, pre = Path(run["dir"]), run["prefix"]
        j = json.loads((d / f"{pre}_run.json").read_text())
        sb, sa = read_lines(d / f"{pre}_sites_before.txt"), read_lines(d / f"{pre}_sites_after.txt")
        rb, ra = read_lines(d / f"{pre}_routes_before.txt"), read_lines(d / f"{pre}_routes_after.txt")
        delays = read_block_csv(d / f"{pre}_block.csv")
        # a net's route string before the router ran against after: the block's own routing is locked, so it must be unchanged
        touched = sorted(n for n in set(rb) | set(ra) if rb.get(n) != ra.get(n))
        moved = sorted(c for c in set(sb) | set(sa) if sb.get(c) != sa.get(c))
        rec: dict[str, Any] = {
            "note": run.get("note", ""), "directive": j["directive"], "wns_ns": j["wns_ns"], "whs_ns": j["whs_ns"], "routing_errors": j["routing_errors"],
            "period_ns": j["period_ns"], "block_cells": j["block_cells"], "block_nets": len(rb), "region": observed_rect(d / f"{pre}_sites_after.txt"),
            "cells_not_moved_by_vivado": not moved, "routes_not_changed_by_vivado": not touched, "moved_cells": moved[:5], "changed_nets": touched[:5],
            "routes_sha": (digest([f"{n}|{rb[n][0]}|{shape(rb[n][1])}" for n in sorted(rb)]) if rb else None),
            "endpoints": len(delays), "worst_internal_delay_ns": (max(delays.values()) if delays else None)}
        if base is None:
            base_region = rec["region"]
            base = {"delays": delays, "shape": {n: shape(v[1]) for n, v in rb.items()}, "tag": run["tag"]}
            rec["role"] = "delivered placement (the reference for the others)"
        else:
            common = sorted(set(base["delays"]) & set(delays))
            diffs = [round((delays[e] - base["delays"][e]) * 1000) for e in common]
            rec.update({
                "role": f"relocated or re-placed; compared with {base['tag']}",
                "endpoints_common": len(common), "endpoints_only_here": len(set(delays) - set(base["delays"])), "endpoints_missing": len(set(base["delays"]) - set(delays)),
                "identical_endpoints": sum(1 for x in diffs if x == 0), "mean_abs_diff_ps": round(sum(abs(x) for x in diffs) / len(diffs), 1) if diffs else None,
                "max_abs_diff_ps": max((abs(x) for x in diffs), default=None), "worst_delay_diff_ps": round((rec["worst_internal_delay_ns"] - max(base["delays"].values())) * 1000),
                "route_shape_equal": {n: shape(v[1]) for n, v in rb.items()} == base["shape"]})
        if run.get("eqy") is not None:
            rec["eqy_equal_to_delivered"] = run["eqy"].get("equivalent")
            rec["eqy"] = {k: run["eqy"].get(k) for k in ("equivalent", "seconds", "strategy", "why") if run["eqy"].get(k) is not None}
        if run.get("dump") is not None:
            obs, obs0 = rec["region"], (base_region if base is not None else rec["region"])
            kept = M.slice_rect(declared_region) if declared_region else obs
            dx, dy = (obs[0] - obs0[0], obs[1] - obs0[1]) if obs and obs0 else (0, 0)
            region = (kept[0] + dx, kept[1] + dy, kept[2] + dx, kept[3] + dy)
            rec["written_checkpoint"] = dump_check(run["dump"], d / f"{pre}_sites_before.txt", d / f"{pre}_routes_before.txt", region)
        if run.get("budgets"):
            rec["budget_problems"] = MI.check_budgets(declared_budgets or [], MI.parse_budgets(run["budgets"]))
            rec["budgets"] = MI.parse_budgets(run["budgets"])
        out["placements"][run["tag"]] = rec
    ps = out["placements"]
    rest = [v for k, v in list(ps.items())[1:]]
    out["placements_tried"] = len(ps)
    problems = []
    for tag, v in ps.items():
        if not v["cells_not_moved_by_vivado"]:
            problems.append(f"{tag}: Vivado moved a cell of the locked block")
        if not v["routes_not_changed_by_vivado"]:
            problems.append(f"{tag}: Vivado changed the routing of a net inside the locked block")
        if v["routing_errors"] != 0:
            problems.append(f"{tag}: the design has routing errors")
        w = v.get("written_checkpoint")
        if w and not (w["cells_unchanged"] and w["routes_unchanged"]):
            problems.append(f"{tag}: the written checkpoint's block differs from the block as delivered")
        if w and w["other_cells_inside_region_count"]:
            problems.append(f"{tag}: {w['other_cells_inside_region_count']} cells of the rest of the design sit inside the keep-out region")
        if v.get("budget_problems"):
            problems.append(f"{tag}: boundary budgets: {'; '.join(v['budget_problems'])}")
        if v.get("eqy_equal_to_delivered") is False or ("eqy" in v and v["eqy_equal_to_delivered"] is None):
            problems.append(f"{tag}: eqy did not prove the netlist equal to the delivered one")
    for tag, v in list(ps.items())[1:]:
        if v["endpoints_only_here"] or v["endpoints_missing"]:
            problems.append(f"{tag}: the set of internal endpoints differs")
        if v["max_abs_diff_ps"] is None or v["max_abs_diff_ps"] > tolerance_ps:
            problems.append(f"{tag}: an internal path delay differs by {v['max_abs_diff_ps']} ps, tolerance {tolerance_ps} ps")
        if not v["route_shape_equal"] and v["note"].startswith("relocated"):
            problems.append(f"{tag}: the relocated routing has a different shape from the delivered one")
    out["problems"] = problems
    out["passed"] = bool(len(ps) >= 2 and not problems)
    out["summary"] = {"relocated_max_abs_diff_ps": max((v["max_abs_diff_ps"] for v in rest if v.get("max_abs_diff_ps") is not None), default=None),
                      "relocated_identical_endpoint_fraction": [f"{v['identical_endpoints']}/{v['endpoints_common']}" for v in rest]}
    return out


def dump_check(dump_text: str, sites_ref: Path, routes_ref: Path, region: tuple[int, int, int, int]) -> dict[str, Any]:
    """A written checkpoint's dump (``managed_block_dump.tcl``) against the block as delivered into that run (the run's ``_sites_before`` and
    ``_routes_before`` files): the block's cells on the same sites and BELs with fixed locations, every net's route string and fixed flag equal,
    and no cell of the rest of the design on a slice inside the keep-out region."""
    ref_s, ref_r = read_lines(sites_ref), read_lines(routes_ref)
    blk, routes, other = {}, {}, {}
    for line in dump_text.splitlines():
        t = line.split("|", 3)
        if t[0] == "BLOCK":
            blk[t[1]] = tuple(line.split("|")[2:])
        elif t[0] == "ROUTE":
            routes[t[1]] = (t[2], t[3] if len(t) > 3 else "")
        elif t[0] == "OTHER":
            other[t[1]] = t[2]
    cells_bad = sorted(c for c in set(ref_s) | set(blk) if tuple(ref_s.get(c, ())) != tuple(blk.get(c, ())))
    # the dump's BLOCK lines and the reference file both hold site|bel|fixed; ROUTE lines fixed|route string
    routes_bad = sorted(n for n in set(ref_r) | set(routes) if (tuple(ref_r.get(n, ())) != tuple(routes.get(n, ()))))
    inside = []
    for name, site in other.items():
        m = re.match(r"SLICE_X(\d+)Y(\d+)$", site)
        if m and M.rects_overlap((int(m.group(1)), int(m.group(2)), int(m.group(1)), int(m.group(2))), region):
            inside.append(f"{name}@{site}")
    return {"block_cells": len(blk), "block_nets": len(routes), "cells_unchanged": not cells_bad, "routes_unchanged": not routes_bad,
            "changed_cells": cells_bad[:5], "changed_nets": routes_bad[:5], "other_cells": len(other), "other_cells_inside_region": sorted(inside)[:10],
            "other_cells_inside_region_count": len(inside), "region": list(region)}


def record_placement_evidence(design: Path, comp_name: str, ev: dict[str, Any]) -> Path:
    project = M.load(design)
    comp = project.component(comp_name)
    return M.write_evidence(project, comp, "placement", {"passed": ev["passed"], "placements_tried": ev["placements_tried"],
                                                         "tolerance_ps": ev["tolerance_ps"], "problems": ev["problems"], "summary": ev["summary"]})


# --- command line --------------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("design", type=Path)
    c.add_argument("--component")
    c.add_argument("--facts", type=Path, help="the text managed_placed_check.tcl wrote (default: run Vivado)")
    c.add_argument("--funcsim", type=Path)
    c.add_argument("--sim", action="store_true")
    c.add_argument("--out", type=Path)
    k = sub.add_parser("compare")
    k.add_argument("design", type=Path)
    k.add_argument("workdir", type=Path, help="holds placements.json: [{tag, prefix, note, funcsim?}] and the runs' files")
    k.add_argument("--component", default=None)
    k.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    design = a.design.resolve()
    if a.cmd == "check":
        rep = check_placed(design, a.component, a.facts, a.funcsim, a.sim)
    else:
        project = M.load(design)
        comp = project.component(a.component) if a.component else next(x for x in project.components if x.level == "placed_routed")
        spec = json.loads((a.workdir / "placements.json").read_text())
        runs = []
        for s in spec:
            run = {"tag": s["tag"], "dir": str(a.workdir), "prefix": s["prefix"], "note": s.get("note", "")}
            if s.get("eqy"):
                run["eqy"] = json.loads((a.workdir / s["eqy"]).read_text())
            dumpf = a.workdir / f"{s['prefix']}_dump.txt"
            if dumpf.is_file():
                run["dump"] = dumpf.read_text()
            logf = a.workdir / f"{s['prefix']}.log"
            if logf.is_file():
                run["budgets"] = logf.read_text(errors="replace")
            runs.append(run)
        rep = compare_placements(runs, int(comp.placement.get("timing_tolerance_ps", 0)), comp.interface.get("timing_budgets"), comp.placement.get("region"))
        rep["component"] = comp.name
        if a.out:
            record_placement_evidence(design, comp.name, rep)
    text = json.dumps(rep, indent=1, default=str)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")
    print(text)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
