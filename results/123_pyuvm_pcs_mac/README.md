# results/123_pyuvm_pcs_mac: the pyuvm bench for the b96 PCS and MAC (brief 123), regression, coverage, seeded bugs and the comparison with brief 112's SystemVerilog UVM bench

The records of `designs/b96_kr260_10g/verif/pyuvm` (pyuvm 5.0.0 on cocotb 2.0.1 and Icarus 12) and of the measurements that compare it with `designs/b96_kr260_10g/verif/uvm` (brief 112, xsim 2026.1). How the bench is built is in `verif/pyuvm/README.md`; the comparison table and the recommendation are in `verif/pyuvm/COMPARISON.md`; this folder holds only what ran.

## Records
- `results.tsv`: every run of the final regression (test, seed, PASS or FAIL, error count, wall seconds, simulated ns); the seed seeds the bench's `random.Random` and cocotb's own generator, so a (test, seed) pair repeats.
- `summary.txt`, `scoreboard_totals.tsv`, `protocol_cover.tsv`: the summary, the comparisons made by each scoreboard check over all runs, and the hits of the protocol checker's cover counts.
- `coverage_report.md`, `coverage_merged.tsv`: merged functional coverage (cocotb-coverage `merge_coverage` over the 42 YAML exports); `first_run/`: the same report and summary from the first 42-run merge, before two frames were added to `t_gaps` (215 of 217 bins, 2 holes).
- `mutants.tsv`: the 17 seeded bugs run with every test; `mutants_blind.tsv`, `summary_mutants_blind.txt`: the same without the two patterns 112 added after seeing M13 and M15 survive.
- `xsim_timing.tsv`: brief 112's bench timed in xsim over the same 42-run shape (`scripts/time_xsim.sh`); `timing_compare.txt`: the wall-time comparison, the linear fit, the mutant-run estimate and the mutant-by-mutant comparison with 112's `mutants.tsv` (`scripts/compare_timing.py`).
- `loc.tsv`: code lines per component, both benches (`scripts/loc_count.py`). `crv_probe.txt`: cocotb-coverage's constraint solver on a frame item (`scripts/crv_probe.py`).
- `example_run_t_smoke_seed1.log`: one passing run; `example_kill_M01_t_smoke_seed1.log`: the same test on mutant M01 (paths shortened).

## Measured
- **The clean RTL passes everything:** 42 runs (eleven directed tests over 2 seeds, two constrained-random tests over 10 seeds), 0 failed, 0 protocol-checker failures.
- **The scoreboard compared:** 198223 receive-PCS and 198223 transmit-PCS clocks clock for clock, 2368 transmitted frames word for word (2312 interframe gaps), 2400 received frames, 546 end-to-end frames, no mismatch.
- **Coverage:** 217 of 217 bins hit (112's 213 plus 4 helper bins), no holes. The first merge had 2 holes (`frame.len x gap`), closed by two frames added to `t_gaps`.
- **Seeded bugs:** 16 of 17 killed with every test, 14 of 17 without the two hindsight patterns (M13 and M15 survive); M03 is the equivalent mutant of 112. Same killing test and seed as 112 for all 17, same checks for 16 of 17.
- **Time:** the 42 runs took 495 s of simulator time (112's bench in xsim: 328.6 s over the same runs, plus a 57.9 s build against 0.1 s); marginal cost 2.73 ms a clock against 0.29 ms; the mutants took 427 s (53 runs) and the blind set 707 s (76 runs).
- **Code:** 1680 code lines against 1940 (13 % fewer), not counting `model/pcs.py` (333 lines) which the Python bench reuses.

## Illustrative or not measured
The channel's error rates, slips and header bursts are stimulus I chose, not a link model; coverage and mutation figures describe this bench, not the design. The mutant results are not blind: I wrote the tests with 112's mutant list and results in hand. The xsim time for the mutant run is **computed** from measured builds and runs, not run. Whether an agent could write either bench first try was **not measured**. Nothing here ran on a board.

## Known gaps and limits
See `verif/pyuvm/README.md`: same reading of clause 49 as 112, same scope, Icarus only (Verilator not installed), no code coverage, no bound SVAs, the pyuvm 5.0.0 features that were present but not exercised.

## Reproduce
`PYTHONPATH=. python designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/pyuvm123 --mutants --record results/123_pyuvm_pcs_mac`, then `--mutants-only --blind`, in a venv with `pip install pyuvm==5.0.0 cocotb-coverage` (see the bench README). `scripts/time_xsim.sh <dir>` (needs Vivado 2026.1) for `xsim_timing.tsv`, then `scripts/compare_timing.py results/123_pyuvm_pcs_mac`.
