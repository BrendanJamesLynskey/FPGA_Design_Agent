# Brief 178: candidate tournaments, results so far

Status (2026-11-22): part 1 (measurement from existing data) is done; the tool, triage, tests and docs are done; **the new Vivado runs have not run**:
no heavy slot was free for about 50 minutes (176 low-latency work and the board build 175 held both, and ranked ahead). The driver
`tools/qor/run_178_eval.sh` is written and waits for slots; every number below is from `results/177_qor/dataset.csv`, no new Vivado run.

## Part 1: does the early ranking predict the routed ranking? (49 full-design rows with post-synthesis, post-place and routed WNS)

Reproduce: `python3 tools/qor/rank_existing.py` (writes `part1_existing_data.json`).

* **Pooled over all 49 rows:** Spearman rho 0.94 (post-synthesis WNS vs routed WNS), 0.98 (post-place vs routed). This is misleading for the tournament question:
  the rows are different designs, and the spread between designs (WNS from -0.2 to +80 ns) dominates.
* **Within one design (the candidate-set case), designs with at least 3 rows** (the rows are variants: boards, constraints, incremental modes, rebuilds):

| design (n) | rho syn vs routed | rho place vs routed | best by syn = best routed | best by place = best routed | routed WNS spread (ns) |
|---|---|---|---|---|---|
| d20_adc_capture_top (5) | 0.90 | 0.82 | yes | yes | 3.47 |
| fcs_top (3) | 0.87 | 0.50 | yes | yes | 0.87 |
| d20_slow_fsm_ramp_top (3) | 0.87 | 0.50 | yes | yes | 68.5 (clock changes) |
| b95_smoke_top (3, different boards) | 0.87 | 1.00 | yes | yes | 73.8 (clock changes) |
| c13_nexys_harris_vga_top (5) | -0.21 | 0.40 | **no** | yes | 0.126 |
| kr260_10g_top (5) | **-0.53** | 0.90 | **no** | yes | 0.283 |

  Where the candidates differ by a lot (a different clock or board), the early WNS ranks them correctly. Where they are close (the two designs under real timing
  pressure, routed spread 0.13 and 0.28 ns), **post-synthesis WNS does not predict the routed order** (rho -0.21 and -0.53, best-by-synthesis was not best routed),
  and post-place WNS does (best-by-place was best routed in 6 of 6 designs). Small n (3 to 5 per design): this is direction, not a statistic.
* **The arith points (brief 160/166) cannot answer this:** they carry no post-synthesis timing (the runs did not write one) and their variants are different
  architectures, not options on one design; only area is available. New runs are what answers it (driver below).

**Consequence for the tournament design (stated from these numbers, to be confirmed by the new runs):** when candidates are close, the synthesis stage cannot pick
the routed winner alone, so a synthesis tournament must carry its top k (default 2) into place and route, and the score must keep a 0.05 ns bucket
so noise-level differences are decided by area and then the default. Post-place is a better early signal than post-synthesis.

## What is built (no Vivado needed to test)

`flow/tournament.py` (plan, run, score, triage, strategies), `flow/tests/test_178_tournament.py` (11 pass), `docs/tournament.md`, specs for five arith points
near their clock limit (`specs/`, made by `tools/qor/make_tournament_specs.py`), the evaluation driver `tools/qor/run_178_eval.sh`.

## Not yet done (needs slots)

* AMD `-strategy` reference measured from Vivado (`python3 -m flow.tournament strategies`).
* Five synthesis tournaments (15 candidates each, light class), a rank study (every synthesis candidate through default place and route), an implementation tournament
  on the best candidate; gain against default and against the best AMD strategy; CPU-hours and wall time; seed/noise repeat.
* Triage measurement: missed gain on `easy`, wasted cost on `hard`; thresholds in `TRIAGE` are initial values, from the dataset's Fmax spread, not yet tuned.
* One full design (a K26 or Artix design cannot run in the 2 GiB light class; it would be an implementation-stage-only tournament).
Run: `tools/qor/run_178_eval.sh` (resumable), then `python3 -m flow.tournament score <tournament.json> --routed <id>=<wns> ...`.
