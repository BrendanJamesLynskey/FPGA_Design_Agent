# results/112_uvm_pcs_mac: the UVM 1.2 bench for the b96 PCS and MAC (brief 112), regression, coverage and seeded bugs

The records of the first UVM environment in this project: the regression of `designs/b96_kr260_10g/verif/uvm` run in Vivado 2026.1 xsim (Basic tier, UVM 1.2, no GT model), its merged functional coverage, the SVA cover counts and the seeded-bug (mutant) run. How the bench is built, what each part checks and why is in `designs/b96_kr260_10g/verif/uvm/README.md`; this folder holds only what ran.

## Records
- `results.tsv`: every run of the final regression (test, seed, PASS or FAIL, UVM error count); the seed is also xsim's `-sv_seed`, so a (test, seed) pair repeats.
- `summary.txt`, `scoreboard_totals.tsv`: the pass/fail summary and the comparisons made by each scoreboard check over all runs.
- `coverage_report.md`, `coverage_merged.tsv`: the merged functional coverage (every bin with its hits and the number of runs that hit it), the holes and the waivers (none).
- `sva_cover.tsv`: the hits of the cover properties of the bound SVAs, summed over the runs.
- `mutants.tsv`, `mutant_kills.txt`: each seeded bug, whether it was killed, by which test, which checks fired, and the first errors of the killing run.
- `xcrg_refusal.txt`: the refusal of `xcrg` (coverage report and merge) on the Basic tier, which is why the merge is done by `cov_merge.py` on mirrored bin counts.
- `timing.txt`: wall time of the full run.
- `example_run_t_smoke_seed1.log`: the log of one passing run (paths shortened).

## Measured
- **The clean RTL passes everything:** 42 runs (eleven directed tests over 2 seeds, two constrained-random tests over 10 seeds), 0 failed.
- **The scoreboard compared a lot:** 204197 receive-PCS clocks and 204197 transmit-PCS clocks clock for clock, 2449 transmitted frames word for word (2393 interframe gaps), 2498 received frames, 542 end-to-end frames, no mismatch.
- **Functional coverage:** 213 of 213 bins hit, no open holes, none waived (see the bench README for what the bins do not measure).
- **Seeded bugs:** 16 of 17 killed; the survivor, M03, is an equivalent mutant (dead RTL, see the bench README). Two of the kills (M13, M15) needed tests added after the first full mutant run showed them surviving.
- **Machine:** each run reports a peak of 225200 KB (xsim's own figure, `results.tsv`); the full regression with the mutants took 56 minutes (`timing.txt`), partly waiting for the load to fall under 6.
- **No RTL bug was found.** What the bench did show about the RTL: the lock-loss abort branch of `mac64_rx` is redundant except in its flush state, and `(n + 4 - 8 > 4)` in `mac64_tx` can never be true (both are harmless, neither is changed).

## Illustrative or not measured
The channel is a model of a link, not the GTH: bit errors, slips and header corruption are what I chose to inject; their rates mean nothing about a real link. Coverage and mutation figures describe this bench, not the design's correctness. Nothing here ran on a board.

## Known gaps and limits
Four modules only, one clock, no GT, no elastic buffer; one reading of clause 49, shared with `model/pcs.py`; functional coverage only (no code coverage, `xcrg` refused); the mutants are a hand-picked sample; CI cannot run the bench. The full list, with the reasons, is under "Known gaps and limits" in `designs/b96_kr260_10g/verif/uvm/README.md`.

## Reproduce
`designs/b96_kr260_10g/verif/uvm/scripts/run_regress.sh --out /tmp/uvm112 --mutants --record results/112_uvm_pcs_mac` (needs Vivado 2026.1 xsim; about an hour; a simulation-only job, no heavy slot while the load is under 6 and more than 12 GB is free). `--quick` runs one seed per directed test and three random seeds. One test: `scripts/uvm_build.sh /tmp/b`, then `cd /tmp/b && xsim pcs_uvm -runall -sv_seed 7 -testplusarg UVM_TESTNAME=t_rand -testplusarg SEED=7`.
