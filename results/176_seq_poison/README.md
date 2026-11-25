# results/176_seq_poison: the poisoned-order-frame fix (brief 176), UVM regression with no waiver and the rebuild of rm_gp_itch

The records of brief 176: a poisoned or dropped order frame consumes no TCP sequence number (`order_seg` and `tcp_fast` give the 59 back). The UVM bench of brief 170 ran again with the sequence-number waiver removed, and `rm_gp_itch` was rebuilt in Vivado 2026.1.

## Records
- `summary.json`, `summary.txt`: the regression (runs, failures, comparisons and mismatches per scoreboard check, SVA failures, coverage closure); the testplan of brief 110 reads `summary.json`. `results.tsv`, `scoreboard_totals.tsv`: every run and the comparisons per check.
- `coverage_report.md`, `coverage_merged.tsv`: every bin of the coverage plan with its hits (`seq_after_poison` replaces `seq_consumed_by_poison`). `sva_cover.tsv`: the cover-property hits of the SVAs.
- `build_rm_gp_itch/`: the rebuild (`build_one.sh` runs it): `run.json` (build stamp, wall time, memory), `digest.json` (timing, utilisation, power, gates), `ctx_timing.txt` (in-context slack of brief 110's critical paths), `cdc_summary.txt`, `run_vivado.log`.
- `build_rm_gp_itch_attempt1_oom6G`: the first attempt, killed by the 6 GB cap in technology mapping; the design needs 8 GB declared (scope anonymous peak 6.3 GiB).

## Measured
36 regression runs, 0 failed, 0 SVA failures; TCP sequence numbers 467 comparisons, 0 mismatches, no waiver; order frames 3,128 and counters 8,938 compared, 0 mismatches; 97 of 97 coverage bins hit. Rebuild: build stamp 71baf720, worst setup slack +0.05 ns and worst hold slack +0.01 ns at 6.206 ns, 17,144 LUTs and 46,115 flip-flops, no BRAM or DSP, 1.266 W, junction 49.4 C.

## Illustrative or not measured
All messages are synthetic. The UVM bench cannot make the transmit multiplexer drop a frame; that path is covered by the unit bench and the `t_giveback` test of `tcp_fast`. Nothing was run on the board.

## Known gaps and limits
The mutation sweep of brief 170 (`results/170_itch_uvm/mutation_seed1.json`) was recorded before this fix and is not repeated here. The xsim stage dry run and the `tcp_fast` mutation list were not re-run.

## Reproduce
`designs/b96_kr260_10g/rm_gp_itch/verif/uvm/scripts/run_regress.sh --out <dir> --seeds 2 --rand 8 --rounds 40 --record results/176_seq_poison`; the rebuild: `results/176_seq_poison/build_one.sh rm_gp_itch 400` (about 80 minutes, takes a heavy slot).
