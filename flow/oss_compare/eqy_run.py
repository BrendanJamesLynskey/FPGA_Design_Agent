#!/usr/bin/env python3
"""eqy results for brief 101 part 2: RTL against the Yosys netlists (a), Vivado post-synthesis funcsim netlists (b), and the
planted faults (both).

    python3 -m flow.oss_compare.eqy_run --yosys                 # every block x family x script of part 1
    python3 -m flow.oss_compare.eqy_run --faults                # fault table on the abc9 UltraScale+ netlists
    python3 -m flow.oss_compare.eqy_run --vivado <dir>...       # funcsim netlists written by flow/oss_compare/netlist.tcl

Results: results/b101/eqy/*.json (one per proof; the eqy work directories stay under build/b101/eqy and are not committed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import eqy_gate  # noqa: E402
from flow.checks import elab  # noqa: E402
from flow.oss_compare import run as P  # noqa: E402

OUT = ROOT / "results" / "b101" / "eqy"
BUILD = ROOT / "build" / "b101" / "eqy"
FAMILIES = {"xcup": "xck26-sfvc784-2LV-c", "xc7": "xc7a100tcsg324-1"}
FAULTS = ("lut_init", "swap_regs", "reset_value", "reset_drop")


def _rec(kind: str, block: str, label: str, r: eqy_gate.EqyResult, extra: dict | None = None) -> dict:
    d = {"kind": kind, "block": block, "gate": label, "status": r.status, "seconds": r.seconds, "strategy": r.strategy, "depth": r.depth,
         "partitions": r.partitions, "proved": r.proved, "unmatched_gold": r.unmatched_gold[:10], "unmatched_gate": r.unmatched_gate[:10],
         "message": r.message, "eqy": r.eqy, "yosys": elab.version()}
    d.update(extra or {})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{kind}__{block}__{label}.json").write_text(json.dumps(d, indent=1))
    print(f"{kind:8s} {block:14s} {label:28s} {r.status:9s} {r.seconds:6.1f}s  {r.message[:90]}", flush=True)
    return d


def gold(block: str) -> list[str]:
    return [str(s) for s in P.BLOCKS[block]]


def yosys_all(blocks, depth: int) -> None:
    for fam, part in FAMILIES.items():
        for b in blocks:
            for arm, script in P.YS_SCRIPT.items():
                rec = P.yosys_edif(b, part, arm)
                r = eqy_gate.check(P.TOP, gold(b), rec["netlist"], BUILD / "yosys" / fam / f"{b}__{arm}", "auto", depth)
                _rec("yosys", b, f"{fam}__{script}", r, {"family": fam, "luts": rec["lut"], "ffs": rec["ff"]})


def faults(blocks, depth: int, count: int = 2) -> None:
    fam, part = "xcup", FAMILIES["xcup"]
    for b in blocks:
        rec = P.yosys_edif(b, part, "ys_abc9")
        txt = Path(rec["netlist"]).read_text()
        d = BUILD / "faults" / b
        d.mkdir(parents=True, exist_ok=True)
        r = eqy_gate.check(P.TOP, gold(b), rec["netlist"], d / "clean", "auto", depth)
        _rec("fault", b, "clean", r, {"fault": "none"})
        for kind in FAULTS:
            for w in range(count):
                try:
                    new, desc = eqy_gate.plant(txt, kind, w * 5 + 1)
                except ValueError as e:
                    _rec("fault", b, f"{kind}_{w}", eqy_gate.EqyResult("N/A", message=str(e)), {"fault": kind, "description": str(e)})
                    break
                f = d / f"{kind}_{w}.v"
                f.write_text(new)
                r = eqy_gate.check(P.TOP, gold(b), str(f), d / f"{kind}_{w}", "auto", depth)
                _rec("fault", b, f"{kind}_{w}", r, {"fault": kind, "description": desc})


def vivado_nets(dirs, depth: int, timeout: int = 1500) -> None:
    for d in dirs:
        d = Path(d)
        meta = json.loads((d / "netlist.json").read_text())
        r = eqy_gate.check(P.TOP, gold(meta["block"]), str(d / "synth_funcsim.v"), BUILD / "vivado" / f"{d.parent.name}__{d.name}", meta.get("strategy", "auto"), depth, timeout)
        _rec("vivado", meta["block"], f"{d.parent.name}__{meta['label']}", r, {"part": meta["part"], "synth": meta["synth"], "tool": meta.get("tool")})


def table() -> None:
    """results/b101/eqy/summary.md from the per-proof records (no tools needed)."""
    recs = [json.loads(f.read_text()) for f in sorted(OUT.glob("*.json"))]
    out = ["# eqy results (brief 101, part 2)", "", "Written by `python3 -m flow.oss_compare.eqy_run --table` from the per-proof records in this directory.", ""]
    for kind, title in (("yosys", "RTL against the Yosys netlists (every block x family x script)"),
                        ("vivado", "RTL against Vivado post-synthesis funcsim netlists"),
                        ("fault", "Planted faults on the Yosys abc9 UltraScale+ netlists")):
        rows = [r for r in recs if r["kind"] == kind]
        if not rows:
            continue
        out += [f"## {title}", "", "| block | netlist | status | strategy | seconds | note |", "|---|---|---|---|---|---|"]
        for r in rows:
            note = (r.get("description") or r["message"]).replace("|", "/")
            out.append(f"| {r['block']} | {r['gate']} | {r['status']} | {r['strategy']} | {r['seconds']} | {note[:150]} |")
        out.append("")
    (OUT / "summary.md").write_text("\n".join(out))
    print(f"{len(recs)} records -> {OUT / 'summary.md'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blocks", nargs="+", default=list(P.BLOCKS), choices=sorted(P.BLOCKS))
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--yosys", action="store_true")
    ap.add_argument("--faults", action="store_true")
    ap.add_argument("--vivado", nargs="+")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=1500, help="seconds per eqy run (a run that does not finish is ERROR, never a pass)")
    a = ap.parse_args(argv)
    if a.table:
        table()
        return 0
    if a.yosys:
        yosys_all(a.blocks, a.depth)
    if a.faults:
        faults(a.blocks, a.depth)
    if a.vivado:
        vivado_nets(a.vivado, a.depth, a.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
