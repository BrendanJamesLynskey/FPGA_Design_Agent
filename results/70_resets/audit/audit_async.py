#!/usr/bin/env python3
"""Brief 70 Part 3: list every asynchronous-reset flop in our own RTL and RTL generators (by pattern, whole repo).

    python3 results/70_resets/audit/audit_async.py [--root .] [--out results/70_resets/audit/async_resets.tsv]

Finds always/always_ff blocks whose sensitivity list holds a clock edge and a second edge (SystemVerilog/Verilog, also
across lines and inside Python generator strings), and VHDL processes whose list has two or more signals with a clocked
`rising_edge`. Skips results/ (recorded runs), benchmark*, flow/tests, flow/checks/seeded (seeded faults) and .git. The
reason column is filled by hand in the README table; this script only lists. One row per block: path, line, sensitivity.
"""
import argparse
import re
from pathlib import Path

SKIP = ("results/", "benchmark", "flow/tests/", "flow/checks/seeded", ".git/", "site/", "docs/", "node_modules", ".venv")
SV = re.compile(r"always(?:_ff)?\s*@\s*\(([^)]*)\)", re.S)
VH = re.compile(r"process\s*\(([^)]*)\)", re.I | re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="results/70_resets/audit/async_resets.tsv")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    rows = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or any(s in rel for s in SKIP) or p.suffix not in (".sv", ".v", ".svh", ".vhd", ".py"):
            continue
        t = p.read_text(errors="replace")
        pat = VH if p.suffix == ".vhd" else SV
        for m in pat.finditer(t):
            sens = " ".join(m.group(1).split())
            if p.suffix == ".vhd":
                n = [s for s in sens.split(",") if s.strip()]
                bad = len(n) >= 2 and re.search(r"rst|reset|clr|clear", sens, re.I)
            else:
                edges = re.findall(r"\b(posedge|negedge)\s+(\w+)", sens)
                bad = len(edges) >= 2
            if bad:
                rows.append((rel, t.count("\n", 0, m.start()) + 1, sens))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("path\tline\tsensitivity\n" + "".join(f"{r[0]}\t{r[1]}\t{r[2]}\n" for r in rows))
    from collections import Counter
    c = Counter(r[0].rsplit("/", 1)[0] for r in rows)
    for k, v in sorted(c.items()):
        print(f"{v:4d}  {k}")
    print(len(rows), "blocks in", len({r[0] for r in rows}), "files")


main()
