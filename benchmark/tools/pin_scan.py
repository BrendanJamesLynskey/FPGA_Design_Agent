#!/usr/bin/env python3
"""Grader-validity scan (phase 08a2): which hidden benches read a pulled-up / tri-state pin, and which would fail a legal driver.

Prints only task ids and yes/no flags (never any spec, bench or reference text), so it is safe to run over held-out tasks.

  pulled:      the bench (hidden/*.sv or *.py) declares a pulled net (tri1/tri0/pullup/pulldown) or tests for a high-impedance level.
  ref_tri:     the reference RTL drives 1'bz or has an inout port (the only tasks where a legal design can leave a pin high-impedance).
  direct_out:  a pulled net is wired straight to a design port that the reference declares `output`; a legal design may declare
               that port `output logic` (a variable) and release it with 1'bz, which Icarus does not resolve with the pull.
  fragile:     direct_out and the bench is not the repaired shape (design pin -> plain wire -> continuous assign onto the pulled net).
  inout:       a pulled net goes to an `inout` port (a net by language rule, so a legal driver cannot be a variable: not fragile).

Usage: python3 benchmark/tools/pin_scan.py [--private]    (--private adds the held-out tasks in ../FPGA_Design_Agent_Knowledge/benchmark_private)

Training-pool specs have no reference RTL yet, so their port direction is unknown: direct_out shows "n/a" and a pulled pin is
flagged for the author to use the repaired shape when the task is built.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETS = [ROOT / "benchmark" / "tasks", ROOT / "benchmark" / "pool", ROOT / "benchmark" / "course" / "tasks"]
PULL_DECL = re.compile(r"\b(?:tri1|tri0)\s+(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)")
PULL_PRIM = re.compile(r"\b(?:pullup|pulldown)\s*(?:\([^)]*\))?\s*\(\s*([A-Za-z_]\w*)")
CONN = re.compile(r"\.\s*([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*\)")


def held_out_ids() -> set[str]:
    ids: set[str] = set()
    for f in [ROOT / "benchmark" / "split.yaml", ROOT / "benchmark" / "course" / "split.yaml",
              ROOT / "benchmark" / "course" / "split_c9_c12.yaml"]:
        if not f.exists():
            continue
        in_held = False
        for line in f.read_text().splitlines():
            if re.match(r"\s*held_out:", line):
                in_held = True
            elif re.match(r"\s*dev:", line):
                in_held = False
            elif in_held:
                m = re.match(r"\s*-\s*(\S+)", line)
                if m:
                    ids.add(m.group(1))
    return ids


def port_dirs(rtl_dir: Path) -> dict[str, str]:
    dirs: dict[str, str] = {}
    for f in rtl_dir.rglob("*.sv"):
        for m in re.finditer(r"\b(input|output|inout)\b\s+(?:wire|logic|reg|tri\w*)?\s*(?:signed\s+)?(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*)\s*[,)]", f.read_text()):
            dirs.setdefault(m.group(2), m.group(1))
    return dirs


def scan(task: Path) -> dict[str, bool] | None:
    hidden = task / "hidden"
    benches = list(hidden.glob("*.sv")) + list(hidden.glob("*.py")) if hidden.is_dir() else []
    if not benches:
        return None
    text = "\n".join(p.read_text() for p in benches)
    ref_tri = (task / "ref").is_dir() and any(re.search(r"1'bz|\binout\b", f.read_text()) for f in (task / "ref").rglob("*.sv"))
    pulled: set[str] = set()
    for m in PULL_DECL.finditer(text):
        pulled.update(n.strip() for n in m.group(1).split(","))
    pulled.update(m.group(1) for m in PULL_PRIM.finditer(text))
    hz = bool(re.search(r"1'bz|is_resolvable", text))
    dirs = port_dirs(task / "ref") if (task / "ref").is_dir() else {}
    direct_out = direct_inout = False
    for m in CONN.finditer(text):
        port, net = m.group(1), m.group(2)
        if net in pulled:
            if dirs.get(port) == "inout":
                direct_inout = True
            else:
                direct_out = True
    return {"pulled": bool(pulled) or hz, "ref_tri": ref_tri, "direct_out": direct_out, "inout": direct_inout, "fragile": direct_out}


def main() -> int:
    held = held_out_ids()
    sets = list(SETS)
    if "--private" in sys.argv[1:]:
        priv = ROOT.parent / "FPGA_Design_Agent_Knowledge" / "benchmark_private"
        sets += [priv / "tasks", priv / "course" / "tasks"]
    print(f"{'task':34} {'held_out':8} {'pulled':6} {'ref_tri':7} {'direct_out':10} {'inout':5} {'fragile':7}")
    yn = lambda b: "yes" if b else "no"
    for base in sets:
        if not base.is_dir():
            continue
        for task in sorted(p for p in base.iterdir() if p.is_dir()):
            r = scan(task)
            if r is None:
                continue
            if not (task / "ref").is_dir():
                print(f"{task.name:34} {yn(task.name in held):8} {yn(r['pulled']):6} {'n/a':7} {'n/a':10} {'n/a':5} {'n/a':7}")
                continue
            print(f"{task.name:34} {yn(task.name in held):8} {yn(r['pulled']):6} {yn(r['ref_tri']):7} {yn(r['direct_out']):10} {yn(r['inout']):5} {yn(r['fragile']):7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
