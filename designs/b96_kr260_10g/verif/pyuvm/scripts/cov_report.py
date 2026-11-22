#!/usr/bin/env python3
"""Verilator code-coverage report for the pyuvm bench (brief 146).

    cov_report.py <merged coverage.dat> <out_dir>

Reads a merged Verilator coverage.dat (`verilator_coverage --write merged.dat run*/coverage.dat`) and writes into <out_dir>:
  coverage_summary.json   per module and per kind (line, branch, expr, toggle): covered, total, percent; the totals the testplan item reads
  coverage_by_module.md   the same as a table
  uncovered.tsv           every uncovered line, branch and expression point (kind, module, file, line, source text) and the toggle bits never seen to toggle, by signal
Points in the bench top (tb_pyuvm_top) are reported apart from the design's four modules and the package."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DESIGN_MODULES = ["pcs_tx", "pcs_rx", "mac64_tx", "mac64_rx", "b96_pkg"]
KINDS = ["line", "branch", "expr", "toggle"]


def parse(path: Path):
    """Yields (fields dict, count) for each C record; the key is \\x01-separated `name \\x02 value` pairs."""
    for ln in path.read_text(errors="replace").splitlines():
        if not ln.startswith("C '"):
            continue
        body, _, cnt = ln[3:].rpartition("' ")
        fields = {}
        for part in body.split("\x01")[1:] if body.startswith("\x01") else body.split("\x01"):
            if "\x02" in part:
                k, v = part.split("\x02", 1)
                fields[k] = v
        yield fields, int(cnt)


def main(argv: list[str]) -> int:
    dat, out = Path(argv[1]), Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tot = defaultdict(lambda: [0, 0])          # (module, kind) -> [covered, total]
    unc = []                                   # (kind, module, file, line, comment)
    tog = defaultdict(list)                    # (module, signal) -> untoggled bit points
    for f, c in parse(dat):
        kind = f.get("page", "").split("/")[0].removeprefix("v_")
        mod = f.get("page", "").split("/")[-1]
        if kind not in KINDS:
            continue
        tot[(mod, kind)][1] += 1
        if c > 0:
            tot[(mod, kind)][0] += 1
        elif kind == "toggle":
            tog[(mod, f.get("o", "?"))].append(f.get("h", ""))
        else:
            unc.append((kind, mod, Path(f.get("f", "?")).name, int(f.get("l", 0)), f.get("o", "")))
    mods = [m for m in DESIGN_MODULES if any(k[0] == m for k in tot)] + sorted({k[0] for k in tot} - set(DESIGN_MODULES))
    summ = {"engine": "Verilator, cocotb 2.0.1, pyuvm 5.0.0", "modules": {}}
    rows = ["| module | line | branch | expression | toggle |", "|---|---|---|---|---|"]

    def cell(c, t):
        return "n/a" if not t else f"{100.0 * c / t:.1f} % ({c}/{t})"
    for m in mods:
        summ["modules"][m] = {k: {"covered": tot[(m, k)][0], "total": tot[(m, k)][1], "percent": round(100.0 * tot[(m, k)][0] / tot[(m, k)][1], 2) if tot[(m, k)][1] else None} for k in KINDS}
        rows.append(f"| {m} | " + " | ".join(cell(*tot[(m, k)]) for k in KINDS) + " |")
    dm = [m for m in mods if m != "tb_pyuvm_top"]
    summ["design"] = {}
    for k in KINDS:
        c = sum(tot[(m, k)][0] for m in dm); t = sum(tot[(m, k)][1] for m in dm)
        summ["design"][k] = {"covered": c, "total": t, "percent": round(100.0 * c / t, 2) if t else None}
    rows.append("| **design (all but the bench top)** | " + " | ".join(cell(summ["design"][k]["covered"], summ["design"][k]["total"]) for k in KINDS) + " |")
    (out / "coverage_summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    (out / "coverage_by_module.md").write_text("\n".join(rows) + "\n")
    src = {}
    lines = ["kind\tmodule\tfile\tline\tsource_or_signal"]
    for kind, mod, fn, ln, o in sorted(unc, key=lambda x: (x[1], x[2], x[3], x[0])):
        if fn not in src:
            cand = list(Path(argv[3]).rglob(fn)) if len(argv) > 3 else []
            src[fn] = cand[0].read_text().splitlines() if cand else []
        text = src[fn][ln - 1].strip() if 0 < ln <= len(src[fn]) else ""
        lines.append(f"{kind}\t{mod}\t{fn}\t{ln}\t{text or o}")
    for (mod, sig), hs in sorted(tog.items()):
        lines.append(f"toggle\t{mod}\t-\t-\t{sig} ({len(hs)} bit points never toggled)")
    (out / "uncovered.tsv").write_text("\n".join(lines) + "\n")
    print((out / "coverage_by_module.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
