# Brief 42 round 1: paired analysis (written by analyze.py)

Runs recorded: 19, of which 3 infrastructure failures (malformed provider response; re-run, not counted: t1_gray_stepper H2, t1_gray_stepper H9, d24_registered_outputs A0). Valid runs: 16. Complete blocks (all four arms): 4 of 4 started; blocks with a missing arm are left out of the paired rows.

Per-arm totals over complete blocks:

| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Hard-limit runs | Median tokens | Median wall s | Total cost USD | Hangs | Mean tests-passed fraction |
|---|---|---|---|---|---|---|---|---|---|
| A0 | 4 | 1 | 1 | 1 | 16490657 | 3165 | 1.146 | 1 | 0.25 |
| H1 | 4 | 2 | 3 | 0 | 6690392 | 2176 | 0.703 | 0 | 0.5 |
| H2 | 4 | 2 | 1 | 0 | 8361084 | 1727 | 0.724 | 0 | 0.5 |
| H9 | 4 | 2 | 1 | 0 | 6977820 | 2265 | 0.747 | 0 | 0.5 |

Paired differences, arm minus A0 (median for tokens, cost, wall, hangs, visits; mean for the tests-passed fraction), 95 % percentile bootstrap over blocks; n = blocks used.

| Arm | Metric | n | Median A0 | Difference | 95 % interval | Interval excludes 0 |
|---|---|---|---|---|---|---|
| H1 | tokens | 3 | 16490657 | -8734788 | [-13099419, 445426] | no |
| H1 | cost_usd | 3 | 0.319 | -0.095 | [-0.183, -0.013] | yes |
| H1 | wall_s | 4 | 3164.7 | -942.75 | [-4322.4, -283.2] | yes |
| H1 | tests_passed_fraction | 4 | 0.0 | 0.25 | [0.0, 0.75] | no |
| H1 | sim_hangs | 4 | 0.0 | 0.0 | [-1.0, 0.0] | no |
| H1 | stage2_visits | 3 | 6 | 0 | [-1, 1] | no |
| H2 | tokens | 3 | 16490657 | -2491902 | [-15701629, 5854917] | no |
| H2 | cost_usd | 3 | 0.319 | -0.022 | [-0.249, 0.039] | no |
| H2 | wall_s | 4 | 3164.7 | -1325.95 | [-4784.3, 131.5] | no |
| H2 | tests_passed_fraction | 4 | 0.0 | 0.25 | [0.0, 0.75] | no |
| H2 | sim_hangs | 4 | 0.0 | 0.0 | [-1.0, 0.0] | no |
| H2 | stage2_visits | 3 | 6 | 1 | [1, 1] | yes |
| H9 | tokens | 3 | 16490657 | -7158234 | [-14101119, -5569547] | yes |
| H9 | cost_usd | 3 | 0.319 | -0.17 | [-0.23, -0.077] | yes |
| H9 | wall_s | 4 | 3164.7 | -1532.85 | [-2199.3, -79.3] | yes |
| H9 | tests_passed_fraction | 4 | 0.0 | 0.25 | [0.0, 0.75] | no |
| H9 | sim_hangs | 4 | 0.0 | 0.0 | [-1.0, 0.0] | no |
| H9 | stage2_visits | 3 | 6 | 1 | [-4, 2] | no |

Discordant blocks for pass and for stage-2 gates (only the arm passed / only A0 passed):

| Arm | Hidden bench: arm only / A0 only | Stage-2 gates: arm only / A0 only |
|---|---|---|
| H1 | 1 / 0 | 2 / 0 |
| H2 | 1 / 0 | 1 / 1 |
| H9 | 1 / 0 | 0 / 0 |

With this few blocks only a very large effect can be told from noise; an interval that includes 0 is a null.
