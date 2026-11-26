#!/usr/bin/env python3
"""Brief 207: trim the Quartus report_max_skew and report_metastability records to the summary tables summarise.py and
flow/cdc_margin.py read (the path-by-path and chain-by-chain detail is about 0.9 MB per report and is not used). Idempotent.

    python3 results/207_cdc_margin/trim_records.py
"""
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"
NOTE_SKEW = "(brief 207 record: path detail after the summary table removed by trim_records.py)\n"
NOTE_META = "(brief 207 record: per-chain detail after this point removed by trim_records.py)\n"

for p in RAW.glob("q_*/*/max_skew_*.rpt"):
    lines = p.read_text(errors="replace").splitlines(True)
    if lines and lines[-1] == NOTE_SKEW:
        continue
    out, seen, borders = [], False, 0
    for ln in lines:
        out.append(ln)
        if "Summary of Paths" in ln:
            seen = True
        if seen and ln.startswith("+-"):
            borders += 1
            if borders == 4:
                break
    p.write_text("".join(out) + NOTE_SKEW)
for p in RAW.glob("q_*/*/metastability_*.rpt"):
    s = p.read_text(errors="replace")
    i = s.find("Synchronizer Chain #1:")
    if i > 0:
        p.write_text(s[:i] + NOTE_META)
print("trimmed")
