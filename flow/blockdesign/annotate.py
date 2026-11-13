"""Annotate a block design with its build: per-block utilisation and worst slack, and the synthesised hierarchy.

    python3 -m flow.blockdesign annotate designs/<name> --build designs/<name>/build/base

Runs ``annotate.tcl`` on the build's routed checkpoint (Vivado, about a minute; take a heavy slot), then writes
``results/blockdesign/<name>/build.json``: the tool, the build ID, the gates' verdict, the design's worst slack, one row
per block of the graph, the synthesised hierarchy, and the hierarchy check (``hiercheck.py``). The viewer merges it into
the graph (``merge``); every number it shows from the build comes from that committed file.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from flow.blockdesign import hiercheck, model as M

TCL = Path(__file__).with_name("annotate.tcl")


def graph_sha(g: dict) -> str:
    """The graph's identity without the build fields: an annotation applies only to the graph it was made for."""
    import hashlib
    gg = {k: v for k, v in g.items() if k not in ("build", "check")}
    return hashlib.sha256(json.dumps(gg, sort_keys=True).encode()).hexdigest()


def results_file(name: str) -> Path:
    return M.ROOT / "results" / "blockdesign" / name / "build.json"


def block_paths(g: dict) -> dict:
    """graph block id -> its RTL instance path."""
    return {b["id"]: b["rtl_path"] for lv in g["levels"].values() for b in lv["blocks"]}


def vivado_bin() -> str:
    from flow import version_pin
    for name in ("vivado_path", "vivado_bin", "VIVADO"):
        v = getattr(version_pin, name, None)
        if callable(v):
            try:
                return str(v())
            except Exception:                 # noqa: BLE001 (fall back to the documented install)
                pass
    return os.environ.get("VIVADO", "/opt/Xilinx/2026.1/Vivado/bin/vivado")


def run_tcl(dcp: Path, out: Path, paths: list[str]) -> dict:
    cmd = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice", "-n", "15", vivado_bin(), "-mode", "batch",
           "-nojournal", "-nolog", "-source", str(TCL), "-tclargs", str(dcp), str(out), *paths]
    subprocess.run(cmd, check=True, cwd=out.parent)
    return json.loads(out.read_text())


def parse_util_hier(text: str) -> dict:
    """report_utilization -hierarchical: instance path -> {lut, ff, bram, dsp, lutram, srl}. The table's first column
    is the instance name, indented two spaces a level; the top's own row is skipped."""
    out, stack = {}, []
    head = None
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c for c in line.strip().strip("|").split("|")]
        if head is None:
            if "Instance" in cells[0]:
                head = [c.strip() for c in cells]
            continue
        name = cells[0].rstrip()
        depth = (len(name) - len(name.lstrip())) // 2 - 1
        name = name.strip()
        if depth < 0 or name.startswith("("):
            continue
        stack = stack[:depth] + [name]
        v = {h: c.strip() for h, c in zip(head, cells)}
        num = lambda k: int(v.get(k) or 0)
        out["/".join(stack)] = {"lut": num("Total LUTs"), "ff": num("FFs"), "bram": num("RAMB36") + 0.5 * num("RAMB18"),
                                "dsp": num("DSP Blocks") if "DSP Blocks" in v else num("DSP48 Blocks"),
                                "lutram": num("LUTRAMs"), "srl": num("SRLs")}
    return out


def summarise(g: dict, raw: dict, build: Path, util: dict | None = None) -> dict:
    gates = json.loads((build / "gates.json").read_text()) if (build / "gates.json").is_file() else {}
    man = json.loads((build / "manifest.json").read_text()) if (build / "manifest.json").is_file() else {}
    paths = block_paths(g)
    blocks = {}
    for bid, p in paths.items():
        r = raw["blocks"].get(p)
        if r is None:
            continue
        u = (util or {}).get(p)
        if u is None:                       # absent from the hierarchical report: counted from the netlist's cells
            u = {"lut": r["lut"], "ff": r["ff"], "bram": r["ramb36"] + 0.5 * r["ramb18"], "dsp": r["dsp"], "lutram": None,
                 "srl": None, "source": "cell count"}
        else:
            u = dict(u, source="report_utilization -hierarchical")
        blocks[bid] = dict(u, wns_ns=r["wns_ns"], endpoints=r["endpoints"])
    chk = hiercheck.check(g, raw["hier"])
    wns = (gates.get("timing") or {}).get("wns_ns")                 # the routed design's worst setup slack
    return {"schema": "fpga-design-agent/blockdesign-build/v1", "design": g["design"], "graph_sha256": graph_sha(g), "tool": raw["tool"],
            "build_id": man.get("build_id") or gates.get("build_id") or "", "gates_pass": bool(gates.get("pass")),
            "first_failed_stage": gates.get("first_failed_stage"), "wns_ns": wns, "blocks": blocks, "hier": raw["hier"], "check": chk}


def merge(g: dict, ann: dict) -> dict:
    g = json.loads(json.dumps(g))
    for lv in g["levels"].values():
        for b in lv["blocks"]:
            b["build"] = ann["blocks"].get(b["id"])
    g["build"] = {k: ann[k] for k in ("tool", "build_id", "gates_pass", "wns_ns", "first_failed_stage")}
    g["check"] = {k: ann["check"][k] for k in ("pass", "matched", "expected", "mismatches")}
    return g


def main(ddir: Path, build: Path | None) -> int:
    g = json.loads((Path(ddir) / "gen" / "graph.json").read_text())
    build = Path(build or Path(ddir) / "build" / "base")
    dcp = next((p for p in (build / "post_route.dcp", build / "route.dcp") if p.is_file()), None)
    if dcp is None:
        print(f"annotate: no routed checkpoint in {build}")
        return 2
    raw = run_tcl(dcp.resolve(), (build / "blockdesign_annotation.json").resolve(), sorted(set(block_paths(g).values())))
    ut = (build / "blockdesign_annotation_util_hier.rpt")
    res = summarise(g, raw, build, parse_util_hier(ut.read_text()) if ut.is_file() else None)
    out = results_file(g["design"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(f"annotate: {out.relative_to(M.ROOT)}; hierarchy check {'passes' if res['check']['pass'] else 'FAILS'} "
          f"({res['check']['matched']} of {res['check']['expected']})")
    for m in res["check"]["mismatches"]:
        print(f"  {m}")
    return 0 if res["check"]["pass"] else 1
