#### Paired effect against the base (`L`)

Effect = mean over common problems of (arm pass rate − base pass rate), in points of pass rate. 97.5% interval: paired bootstrap over problems. Sign test: exact, two-sided, on the problems that changed. Arms whose interval includes 0 come first.

| Arm | Finding | Effect [97.5%] | Better / worse / same | Sign test p | Problems | Dropped |
|---|---|---|---|---|---|---|
| D12 | worse than base | -13.4 [-23.3, -4.1] | 3 / 19 / 64 | 0.000855 | 86 | 0 |

Problems left out of the paired effect (in only one of the arm and the base; the Arms table below still pools over them): none.

#### Arms

| Arm | Runs: pass rate each | Pooled pass@1 [95% problem bootstrap] | Cost | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|---|---|
| L (base) | 1: 61.6% | 53/86 = 61.6% [51.2, 72.1] | ≥$0.5307 (1 unreported) | ≥$0.0062 | ≥$0.0100 | 57 s | 2,466,028 |
| D12 | 2: 50.0%, 46.5% | 83/172 = 48.3% [39.0, 58.1] | ≥$1.4369 (1 unreported) | ≥$0.0084 | ≥$0.0173 | 21 s | 9,233,156 |

#### Pareto: pass rate against $ per problem

| Arm | $/problem | Pass rate | Frontier |
|---|---|---|---|
| L | ≥$0.0062 | 61.6% | n/a (cost a lower bound) |
| D12 | ≥$0.0084 | 48.3% | n/a (cost a lower bound) |

≥: some of the arm's cost was not reported, so its $/problem is a lower bound. It is drawn hollow and kept off the frontier.

