# Brief 42 round 1: paired analysis (written by analyze.py)

Runs recorded: 51, of which 3 infrastructure failures (malformed provider response; re-run, not counted: t1_gray_stepper H2, t1_gray_stepper H9, d24_registered_outputs A0). Valid runs: 48. Complete blocks (all four arms): 12 of 12 started; blocks with a missing arm are left out of the paired rows.

Per-arm totals over complete blocks:

| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Hard-limit runs | Median tokens | Median wall s | Total cost USD | Hangs | Mean tests-passed fraction |
|---|---|---|---|---|---|---|---|---|---|
| A0 | 12 | 5 | 2 | 1 | 13286935 | 2767 | 3.201 | 1 | 0.417 |
| H1 | 12 | 5 | 5 | 0 | 6131522 | 1964 | 2.051 | 0 | 0.472 |
| H2 | 12 | 6 | 2 | 1 | 13699462 | 2373 | 2.583 | 4 | 0.5 |
| H9 | 12 | 6 | 2 | 0 | 10374696 | 2608 | 2.587 | 0 | 0.509 |

Paired differences, arm minus A0 (median for tokens, cost, wall, hangs, visits; mean for the tests-passed fraction), 95 % percentile bootstrap over blocks; n = blocks used.

| Arm | Metric | n | Median A0 | Difference | 95 % interval | Interval excludes 0 | Blocks lower / higher than A0 |
|---|---|---|---|---|---|---|---|
| H1 | tokens | 11 | 13286935 | -8714684 | [-10571173, 115681] | no | 8 / 3 |
| H1 | cost_usd | 11 | 0.302 | -0.099 | [-0.161, -0.013] | yes | 10 / 1 |
| H1 | wall_s | 12 | 2767.3 | -501.3 | [-1088.1, -291.25] | yes | 10 / 2 |
| H1 | tests_passed_fraction | 12 | 0.0 | 0.056 | [-0.083, 0.25] | no | 1 / 1 |
| H1 | sim_hangs | 12 | 0.0 | 0.0 | [0.0, 0.0] | no | 1 / 0 |
| H1 | stage2_visits | 11 | 6 | 0 | [-1, 1] | no | 4 / 4 |
| H2 | tokens | 10 | 14888796.0 | -246356.0 | [-7206670.5, 5854917.0] | no | 6 / 4 |
| H2 | cost_usd | 10 | 0.309 | -0.005 | [-0.097, 0.039] | no | 6 / 4 |
| H2 | wall_s | 12 | 2767.3 | -58.0 | [-1325.95, 748.9] | no | 7 / 5 |
| H2 | tests_passed_fraction | 12 | 0.0 | 0.083 | [0.0, 0.25] | no | 0 / 1 |
| H2 | sim_hangs | 12 | 0.0 | 0.0 | [0.0, 0.0] | no | 1 / 1 |
| H2 | stage2_visits | 10 | 6.0 | 0.5 | [-1.5, 1.0] | no | 4 / 5 |
| H9 | tokens | 11 | 13286935 | -4354750 | [-7158234, 635138] | no | 7 / 4 |
| H9 | cost_usd | 11 | 0.302 | -0.049 | [-0.17, -0.008] | yes | 9 / 2 |
| H9 | wall_s | 12 | 2767.3 | -165.0 | [-1239.45, 73.85] | no | 9 / 3 |
| H9 | tests_passed_fraction | 12 | 0.0 | 0.093 | [0.0, 0.259] | no | 0 / 2 |
| H9 | sim_hangs | 12 | 0.0 | 0.0 | [0.0, 0.0] | no | 1 / 0 |
| H9 | stage2_visits | 11 | 6 | 1 | [-1, 1] | no | 5 / 6 |

Discordant blocks for pass and for stage-2 gates (only the arm passed / only A0 passed):

| Arm | Hidden bench: arm only / A0 only | Stage-2 gates: arm only / A0 only |
|---|---|---|
| H1 | 1 / 1 | 3 / 0 |
| H2 | 1 / 0 | 1 / 1 |
| H9 | 1 / 0 | 0 / 0 |

With this few blocks only a very large effect can be told from noise; an interval that includes 0 is a null.
