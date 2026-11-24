#!/usr/bin/env python3
"""Write results/170_itch_uvm/summary.json from a regression's output directory (brief 170): the one file the testplan's items read.

    make_record.py <regress out dir> <record dir>

Reads results.tsv, scoreboard_totals.tsv, coverage_merged.tsv, sva_cover.tsv and the runs' logs (assertion failures are UVM errors from the SVA module)."""
import json
import re
import sys
from pathlib import Path

out, rec = Path(sys.argv[1]), Path(sys.argv[2])
rows = [l.split("\t") for l in (out / "results.tsv").read_text().splitlines()[1:]]
chk = {}
for l in (out / "scoreboard_totals.tsv").read_text().splitlines():
    n, c, m = l.split("\t")
    chk[n] = {"compared": int(c), "mismatches": int(m)}
bins = [l.split("\t") for l in (out / "coverage_merged.tsv").read_text().splitlines()[1:]]
sva = {l.split("\t")[0]: int(l.split("\t")[1]) for l in (out / "sva_cover.tsv").read_text().splitlines()[1:]}
sva_fail = 0
for lg in sorted((out / "runs").glob("*/run.log")):
    if lg.parent.name.startswith("t_seq_poison"):
        continue
    sva_fail += len(re.findall(r"^UVM_ERROR .*\[SVA\]", lg.read_text(errors="replace"), re.M))
poison = (out / "runs" / "t_seq_poison_1" / "run.log").read_text(errors="replace")
m = re.search(r"\[SEQ\] (order \d+: TCP sequence number \d+, expected \d+[^\n]*)", poison)
rec.mkdir(parents=True, exist_ok=True)
S = {
    "schema": "fpga-design-agent/uvm-regression/v1", "bench": "designs/b96_kr260_10g/rm_gp_itch/verif/uvm", "simulator": "xsim 2026.1, UVM 1.2",
    "runs": len(rows), "failed": sum(1 for r in rows if r[3] != "PASS"), "tests": sorted({r[0] for r in rows}),
    "checks": chk, "sva_failures": sva_fail,
    "coverage": {"bins": len(bins), "hit": sum(1 for b in bins if int(b[1]) > 0), "holes": [b[0] for b in bins if int(b[1]) == 0]},
    "seq_waived": chk.get("SEQ_WAIVED", {}).get("compared", 0),
    "finding_seq_poison": {"test": "t_seq_poison", "plusarg": "+SEQ_STRICT", "failed": "TCP sequence number" in poison, "message": m.group(1) if m else ""},
}
(rec / "summary.json").write_text(json.dumps(S, indent=1) + "\n")
print(json.dumps({k: S[k] for k in ("runs", "failed", "sva_failures", "seq_waived")}), S["coverage"]["hit"], "of", S["coverage"]["bins"])
