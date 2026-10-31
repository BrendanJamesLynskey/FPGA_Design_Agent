#### Paired effect against the base (`L`)

Effect = mean over common problems of (arm pass rate − base pass rate), in points of pass rate. 97.5% interval: paired bootstrap over problems. Sign test: exact, two-sided, on the problems that changed. Arms whose interval includes 0 come first.

| Arm | Finding | Effect [97.5%] | Better / worse / same | Sign test p | Problems | Dropped |
|---|---|---|---|---|---|---|
| G123 | no detectable effect | -8.1 [-17.4, +1.6] | 11 / 26 / 49 | 0.0201 | 86 | 0 |

Problems left out of the paired effect (in only one of the arm and the base; the Arms table below still pools over them): none.

#### Arms

| Arm | Runs: pass rate each | Pooled pass@1 [95% problem bootstrap] | Cost | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|---|---|
| L (base) | 1: 61.6% | 53/86 = 61.6% [51.2, 72.1] | ≥$0.5307 (1 unreported) | ≥$0.0062 | ≥$0.0100 | 57 s | 2,466,028 |
| G123 | 3: 59.3%, 55.8%, 45.3% | 138/258 = 53.5% [44.6, 62.0] | ≥$1.6914 (55 unreported) | ≥$0.0066 | ≥$0.0123 | 192 s | 14,810,179 |

#### Pareto: pass rate against $ per problem

| Arm | $/problem | Pass rate | Frontier |
|---|---|---|---|
| L | ≥$0.0062 | 61.6% | n/a (cost a lower bound) |
| G123 | ≥$0.0066 | 53.5% | n/a (cost a lower bound) |

≥: some of the arm's cost was not reported, so its $/problem is a lower bound. It is drawn hollow and kept off the frontier.

