# results/170_itch_uvm: the independent UVM bench for the ITCH/OUCH path (brief 170), regression, coverage and mutation records

The records of the UVM 1.2 bench in `designs/b96_kr260_10g/rm_gp_itch/verif/uvm` run in Vivado 2026.1 xsim (Basic tier): the regression, its merged functional coverage, the finding's failing run and the blind mutation sweeps.

## Records
- `summary.json`: the one file the testplan (`designs/b110_itch_ouch/verif/testplan.yaml`) reads: runs, failures, comparisons and mismatches per scoreboard check, SVA failures, coverage closure, the waived TCP sequence numbers and the finding's failing test.
- `results.tsv`: every run of the regression (test, snapshot, seed, PASS or FAIL, UVM error count); the seed is also xsim's `-sv_seed`, so a (test, seed) pair repeats. `summary.txt`, `scoreboard_totals.tsv`: the summary and the comparisons per check.
- `coverage_report.md`, `coverage_merged.tsv`: every bin of the coverage plan with its hits, and the holes (none). `sva_cover.tsv`: the cover-property hits of the SVAs.
- `t_seq_poison_expected_failure.log`: the minimal failing test of the finding (a poisoned order frame consumes a TCP sequence number), run with `+SEQ_STRICT`.
- `mutation_seed*.json`: the blind mutation sweeps (`flow/mutation_b170.py`, the fixed tool of brief 152), when present.

## Measured
34 regression runs pass; comparisons: counters 8,897, flags 1,736, udp_strip counters 2,604, order frames 3,112 (byte exact), order counters 434; 97 of 97 coverage bins hit; 0 SVA failures. The finding fails as designed.

## Illustrative or not measured
All messages are synthetic. The order frame is the stand-in's (TCP checksum 0). Timing-dependent counters are not compared. Code coverage is not measured (`xcrg` is refused by the Basic tier).

## Known gaps and limits
See the bench README (`designs/b96_kr260_10g/rm_gp_itch/verif/uvm/README.md`, "Known gaps"). The regression was run while other jobs shared the machine; its simulation results do not depend on timing of the host.

## Reproduce
`designs/b96_kr260_10g/rm_gp_itch/verif/uvm/scripts/run_regress.sh --out <dir> --seeds 2 --rand 8 --rounds 40 --record results/170_itch_uvm` (about 20 minutes on an idle machine; waits while the load is 6 or more).
