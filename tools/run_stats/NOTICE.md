# tools/run_stats: provenance

`ablate.py` and `table.py` are copied unchanged from `CVDP_RTL_Agent/tools/` (github.com/BrendanJamesLynskey/CVDP_RTL_Agent, MIT licence,
Copyright (c) 2026 Brendan Lynskey; copied 2026-11-26, brief 218, on the recommendation of `reports/226_cvdp_lessons_report.md` section 4). They are
standard library only. Do not edit them here: change them in the CVDP repository and copy again.

`graded.py` is new (brief 218): the adapter from FPGA Force run records to the CSV rows those tools read, and a paired bootstrap of any numeric
column, so a graded outcome (stage reached, holes closed per million tokens, requirements evidenced, tokens, wall time) is compared the same way a
pass rate is: paired on the item, repeats kept together, an interval from a bootstrap over items, an exact sign test, and "no detectable effect"
(never "no effect") when the interval includes zero.
