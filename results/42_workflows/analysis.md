# Brief 42 round 1: paired analysis (written by analyze.py)

How to read this file: the unit is the block (task, repeat) with all four arms valid. Tokens and cost leave out blocks where either run was ended by the hard wall limit (no summary, so no provider-reported total), hence n = 10 or 11 there and 12 elsewhere. Primary rows: tokens and cost for H1 and H9, wall time and hangs for H2 (prereg, Analysis). Intervals with this few blocks are close to the observed range. Cost and tokens are slightly undercounted: when a malformed provider response is retried, the usage of the discarded response is not added to the run's total (`OpenRouterClient`), mostly in A0, which had the most retries.

Runs recorded: 51, of which 3 infrastructure failures (malformed provider response; re-run, not counted: t1_gray_stepper H2, t1_gray_stepper H9, d24_registered_outputs A0). Valid runs: 48. Complete blocks (all four arms): 12 of 12 started; blocks with a missing arm are left out of the paired rows.

Per-arm totals over complete blocks:

| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Hard-limit runs | Median tokens | Median wall s | Total cost USD | Sim hangs (runs with one) | Mean tests-passed fraction |
|---|---|---|---|---|---|---|---|---|---|
| A0 | 12 | 5 | 2 | 1 | 13286935 | 2767 | 3.201 | 1 (1) | 0.417 |
| H1 | 12 | 5 | 5 | 0 | 6131522 | 1964 | 2.051 | 0 (0) | 0.472 |
| H2 | 12 | 6 | 2 | 1 | 13699462 | 2373 | 2.583 | 4 (1) | 0.5 |
| H9 | 12 | 6 | 2 | 0 | 10374696 | 2608 | 2.587 | 0 (0) | 0.509 |

Paired differences, arm minus A0 (median for tokens, cost, wall and visits; mean for the tests-passed fraction), 95 % percentile bootstrap over blocks (10,000 resamples, seed 20261111; the pre-registered statistic); n = blocks used. The last two columns are POST HOC (not pre-registered) and NOT corrected for the 9 arm-by-metric tests run on tokens, cost and wall time (Bonferroni 0.05 / 9 = 0.0056): the blocks where the arm was lower / higher than A0, and the exact two-sided sign-test p on those counts.

| Arm | Metric | n | A0 (median; mean for the fraction) | Difference | Relative to A0 | 95 % interval | Interval excludes 0 | Lower / higher | Sign p (post hoc) |
|---|---|---|---|---|---|---|---|---|---|
| H1 | tokens | 11 | 13286935 | -8714684 | -65.6 % | [-10571173, 115681] | no | 8 / 3 | 0.227 |
| H1 | cost_usd | 11 | 0.302 | -0.099 | -32.8 % | [-0.161, -0.013] | yes | 10 / 1 | 0.012 |
| H1 | wall_s | 12 | 2767.3 | -501.3 | -18.1 % | [-1088.1, -291.25] | yes | 10 / 2 | 0.039 |
| H1 | tests_passed_fraction | 12 | 0.417 | 0.056 | - | [-0.083, 0.25] | no | 1 / 1 | - |
| H1 | stage2_visits | 11 | 6 | 0 | - | [-1, 1] | no | 4 / 4 | - |
| H2 | tokens | 10 | 14888796.0 | -246356.0 | -1.7 % | [-7206670.5, 5854917.0] | no | 6 / 4 | 0.754 |
| H2 | cost_usd | 10 | 0.309 | -0.005 | -1.5 % | [-0.097, 0.039] | no | 6 / 4 | 0.754 |
| H2 | wall_s | 12 | 2767.3 | -58.0 | -2.1 % | [-1325.95, 748.9] | no | 7 / 5 | 0.774 |
| H2 | tests_passed_fraction | 12 | 0.417 | 0.083 | - | [0.0, 0.25] | no | 0 / 1 | - |
| H2 | stage2_visits | 10 | 6.0 | 0.5 | - | [-1.5, 1.0] | no | 4 / 5 | - |
| H9 | tokens | 11 | 13286935 | -4354750 | -32.8 % | [-7158234, 635138] | no | 7 / 4 | 0.549 |
| H9 | cost_usd | 11 | 0.302 | -0.049 | -16.1 % | [-0.17, -0.008] | yes | 9 / 2 | 0.065 |
| H9 | wall_s | 12 | 2767.3 | -165.0 | -6.0 % | [-1239.45, 73.85] | no | 9 / 3 | 0.146 |
| H9 | tests_passed_fraction | 12 | 0.417 | 0.093 | - | [0.0, 0.259] | no | 0 / 2 | - |
| H9 | stage2_visits | 11 | 6 | 1 | - | [-1, 1] | no | 5 / 6 | - |

Sensitivity (censored blocks): wall time with the blocks that contain a run ended by the hard 5,400 s limit left out (those runs count 5,400 s in the table above, a floor on their true time):

| Arm | n | Difference s | 95 % interval s | Interval excludes 0 | Lower / higher |
|---|---|---|---|---|---|
| H1 | 10 | -396.7 | [-818.9, 104.1] | no | 8 / 2 |
| H2 | 10 | -58.0 | [-981.0, 703.6] | no | 6 / 4 |
| H9 | 10 | -165.0 | [-1040.7, 69.8] | no | 8 / 2 |

Discordant blocks for pass and for stage-2 gates (only the arm passed / only A0 passed):

| Arm | Hidden bench: arm only / A0 only | Stage-2 gates: arm only / A0 only |
|---|---|---|
| H1 | 1 / 1 | 3 / 0 |
| H2 | 1 / 0 | 1 / 1 |
| H9 | 1 / 0 | 0 / 0 |

## The pre-registered adopt rule, word for word, and its two readings

> Primary metric per arm: H1: tokens per run (and cost). H2: wall time per run and hangs. Safety metric for both: hidden-bench tests passed as a fraction of the task's tests, and pass count: an arm that lowers it is not adopted whatever it saves.
> Adopt rule (stated before the data): adopt an arm as default only if its primary metric improves by at least 30 % in the paired median with a bootstrap interval that excludes 0, and the tests-passed fraction does not fall (its mean paired difference interval does not lie below 0) and pass discordant pairs are not worse than A0's by more than one.

The wording "tokens per run (and cost)" was not fixed in advance as one reading, so the rule is ambiguous for H1 and H9. Both readings are reported; the verdict is not chosen after the fact. Reading T: tokens alone, or tokens and cost together (both must pass). Reading C: tokens or cost (either passes). A metric passes when its paired median improves by at least 30 % of A0's median and its bootstrap interval excludes 0; the safety conditions are checked separately. H2's primary metric is wall time (and hangs).

| Arm | Tokens | Cost | Wall time | Safety: fraction interval not below 0 | Safety: pass discordants not worse by more than 1 | Meets rule, reading T | Meets rule, reading C |
|---|---|---|---|---|---|---|---|
| H1 | fail (-65.6 %, interval includes 0) | pass (-32.8 %, interval excludes 0) | fail (-18.1 %, interval excludes 0) | yes | yes | no | yes |
| H2 | fail (-1.7 %, interval includes 0) | fail (-1.5 %, interval includes 0) | fail (-2.1 %, interval includes 0) | yes | yes | no | no |
| H9 | fail (-32.8 %, interval includes 0) | fail (-16.1 %, interval excludes 0) | fail (-6.0 %, interval includes 0) | yes | yes | no | no |

Sim hangs are counts (table of per-arm totals above); the median difference of a count that is 0 in almost every block carries no information. With this few blocks only a very large effect can be told from noise; an interval that includes 0 is a null.
