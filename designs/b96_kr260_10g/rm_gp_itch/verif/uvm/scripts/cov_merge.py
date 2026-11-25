#!/usr/bin/env python3
"""Merge the coverage counts of the ITCH/OUCH UVM bench runs and write the closure report (brief 170).

    cov_merge.py <out dir> <run.log> ...

Every run prints `COV <bin> <hits>` (the bins of env/itch_cov.sv) and `SVA_COV <name> <hits>`. The Basic tier's xcrg refuses to merge covergroup databases, so the merge is
done on these counts. Writes coverage_merged.tsv, sva_cover.tsv and coverage_report.md; prints one summary line."""
import re
import sys
from collections import OrderedDict
from pathlib import Path

out = Path(sys.argv[1])
bins: "OrderedDict[str, int]" = OrderedDict()
sva: "OrderedDict[str, int]" = OrderedDict()
for lg in sys.argv[2:]:
    for line in Path(lg).read_text(errors="replace").splitlines():
        m = re.search(r"\[COV\] COV (\S+) (\d+)\s*$", line)
        if m:
            bins[m.group(1)] = bins.get(m.group(1), 0) + int(m.group(2))
            continue
        m = re.match(r"SVA_COV (\S+) (\d+)\s*$", line)
        if m:
            sva[m.group(1)] = sva.get(m.group(1), 0) + int(m.group(2))
(out / "coverage_merged.tsv").write_text("bin\thits\n" + "".join(f"{k}\t{v}\n" for k, v in bins.items()))
(out / "sva_cover.tsv").write_text("cover\thits\n" + "".join(f"{k}\t{v}\n" for k, v in sva.items()))
holes = [k for k, v in bins.items() if v == 0]
hit = len(bins) - len(holes)
rep = [f"# Functional coverage closure (brief 170)", "", f"{hit} of {len(bins)} bins hit; {len(holes)} holes.", ""]
rep += ["| bin | hits |", "|---|---|"] + [f"| {k} | {v} |" for k, v in bins.items()]
rep += ["", "## Holes", ""] + ([f"- {h}" for h in holes] or ["none"])
rep += ["", "## SVA cover counts", "", "| cover | hits |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sva.items()]
(out / "coverage_report.md").write_text("\n".join(rep) + "\n")
print(f"coverage: {hit} of {len(bins)} bins hit, {len(holes)} holes" + (": " + " ".join(holes) if holes else ""))
